from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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

NAME_COUNTRY_RE = re.compile(r"^(.*?)\s*\(([A-Za-z]{3})\)\s*$")


def _classify(label: str) -> str | None:
    if "master" in label.lower():
        return None
    return guess_category(label)


def _two_digit_year_to_full(yy: str) -> int | None:
    if not yy.isdigit():
        return None
    n = int(yy)
    return 1900 + n if n > 30 else 2000 + n


def _race_id_from_url(url: str) -> str:
    m = re.search(r"/show/(\d+)", url)
    if not m:
        raise ValueError(f"Could not find race id in URL: {url}")
    return m.group(1)


def discover_races(base_url: str, session: requests.Session | None = None) -> list[tuple[str, ParsedRace]]:
    resp = polite_get(base_url, session=session)
    soup = BeautifulSoup(resp.text, "lxml")
    select = soup.find("select", id="rc_id")
    if select is None:
        return []

    race_id = _race_id_from_url(base_url)
    parsed = urlparse(base_url)
    host = f"{parsed.scheme}://{parsed.netloc}"

    out: list[tuple[str, ParsedRace]] = []
    for option in select.find_all("option"):
        label = option.get_text(strip=True)
        category_code = _classify(label)
        if category_code is None:
            continue
        rc_id = option["value"]
        results_url = urljoin(
            host,
            f"/en/race/resultlist/{race_id}?checkpoint=9999&layout=marathon&page=1&rc_id={rc_id}",
        )
        out.append(
            (
                category_code,
                ParsedRace(
                    category_code=category_code,
                    distance_m=guess_distance_m(label),
                    name=label,
                    results_url=results_url,
                ),
            )
        )
    return out


_HEADER_MAP = {
    "place": ("pl.", "plac", "rank"),
    "name": ("name",),
    "birth_year": ("yob",),
    "club": ("club",),
    "time": ("result", "time"),
}


def _classify_header(text: str) -> str | None:
    key = text.strip().lower()
    for field, markers in _HEADER_MAP.items():
        if any(marker in key for marker in markers):
            return field
    return None


def parse_results_table(html: str) -> list[ParsedResult]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="result-list")
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    header_cells = rows[0].find_all("th")
    columns: dict[int, str] = {}
    for idx, th in enumerate(header_cells):
        field = _classify_header(th.get_text())
        if field:
            columns[idx] = field

    results: list[ParsedResult] = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if not cells:
            continue
        values: dict[str, str] = {}
        for idx, cell in enumerate(cells):
            field = columns.get(idx)
            if field:
                values[field] = cell.get_text(separator=" ", strip=True)

        name_raw = values.get("name", "").strip().lstrip("»").strip()
        if not name_raw:
            continue

        country = None
        m = NAME_COUNTRY_RE.match(name_raw)
        if m:
            name, country_code = m.groups()
            country = normalize_country(country_code)
        else:
            name = name_raw

        place_raw = values.get("place", "").strip()
        place = int(place_raw) if place_raw.isdigit() else None

        time_raw = values.get("time", "").strip()

        results.append(
            ParsedResult(
                place=place,
                status=status_from_time_cell(time_raw),
                raw_name=re.sub(r"\s+", " ", name).strip(),
                raw_country=country,
                raw_club=values.get("club", "").strip() or None,
                bib=None,
                birth_year=_two_digit_year_to_full(values.get("birth_year", "").strip()),
                time_seconds=parse_time_to_seconds(time_raw),
                time_display=time_raw or None,
            )
        )
    return results


def scrape(base_url: str, session: requests.Session | None = None) -> dict[str, tuple[ParsedRace, list[ParsedResult]]]:
    sess = session or requests.Session()
    out: dict[str, tuple[ParsedRace, list[ParsedResult]]] = {}
    for category_code, race in discover_races(base_url, session=sess):
        resp = polite_get(race.results_url, session=sess)
        results = parse_results_table(resp.text)
        out[category_code] = (race, results)
    return out
