from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment

from nordcross.scrapers.common import (
    ParsedRace,
    ParsedResult,
    guess_category,
    guess_distance_m,
    normalize_country,
    parse_time_to_seconds,
    polite_get,
    status_from_time_cell,
)

TEAM_HREF_MARKERS = ("type=teams", "type=clubs")


def _cell_text(cell) -> str:
    for comment in cell.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    return cell.get_text(separator=" ", strip=True)


def discover_races(base_url: str, session: requests.Session | None = None) -> list[ParsedRace]:
    resp = polite_get(base_url, session=session)
    soup = BeautifulSoup(resp.text, "lxml")

    races: list[ParsedRace] = []
    for heading in soup.select(".ibox-content h4"):
        label = heading.get_text(strip=True)
        category_code = guess_category(label)
        if category_code is None:
            continue  # e.g. "Jog groups" or other non-championship event

        results_href = None
        for sibling in heading.find_next_siblings():
            if sibling.name == "h4":
                break
            if sibling.name == "a":
                href = sibling.get("href", "")
                if "urslit/?race=" in href and not any(m in href for m in TEAM_HREF_MARKERS):
                    results_href = href
                    break
        if results_href is None:
            continue

        races.append(
            ParsedRace(
                category_code=category_code,
                distance_m=guess_distance_m(label),
                name=label,
                results_url=urljoin(base_url, results_href),
            )
        )
    return races


_HEADER_MAP = {
    "place": ("#", "rank", "sæti"),
    "bib": ("bib",),
    "name": ("name", "nafn"),
    "birth_year": ("year", "birthyear", "árg"),
    "country": ("country", "club", "lið", "þjóð"),
    "time": ("time", "final", "tími"),
}


def _classify_header(text: str) -> str | None:
    key = text.strip().lower()
    for field, markers in _HEADER_MAP.items():
        if any(marker in key for marker in markers):
            return field
    return None


def parse_results_table(html: str) -> list[ParsedResult]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []

    header_cells = table.find("thead").find_all("th")
    columns: dict[int, str] = {}
    for idx, th in enumerate(header_cells):
        field = _classify_header(th.get_text())
        if field:
            columns[idx] = field

    results: list[ParsedResult] = []
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values: dict[str, str] = {}
        for idx, cell in enumerate(cells):
            field = columns.get(idx)
            if field:
                values[field] = _cell_text(cell)

        raw_name = values.get("name", "").strip()
        if not raw_name:
            continue

        place_raw = values.get("place", "").strip()
        place = int(place_raw) if place_raw.isdigit() else None

        birth_year_raw = values.get("birth_year", "").strip()
        birth_year = int(birth_year_raw) if birth_year_raw.isdigit() else None

        time_raw = values.get("time", "").strip()
        results.append(
            ParsedResult(
                place=place,
                status=status_from_time_cell(time_raw),
                raw_name=raw_name,
                raw_country=normalize_country(values.get("country")),
                raw_club=values.get("country", "").strip() or None,
                bib=values.get("bib", "").strip() or None,
                birth_year=birth_year,
                time_seconds=parse_time_to_seconds(time_raw),
                time_display=time_raw or None,
            )
        )
    return results


def scrape(base_url: str, session: requests.Session | None = None) -> dict[str, tuple[ParsedRace, list[ParsedResult]]]:
    """Returns {category_code: (race, results)} for a timataka-hosted championship page."""
    sess = session or requests.Session()
    out: dict[str, tuple[ParsedRace, list[ParsedResult]]] = {}
    for race in discover_races(base_url, session=sess):
        resp = polite_get(race.results_url, session=sess)
        results = parse_results_table(resp.text)
        out[race.category_code] = (race, results)
    return out
