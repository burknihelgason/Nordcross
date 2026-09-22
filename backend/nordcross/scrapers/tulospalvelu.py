from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

from nordcross.scrapers.common import (
    ParsedRace,
    ParsedResult,
    normalize_country,
    parse_time_to_seconds,
    polite_get,
)

JSON_BASE = "https://online.tulospalvelu.fi/tulokset-new/online/online_{slug}_"

CLASS_PATTERNS = [
    (re.compile(r"^(M|MEN)$", re.IGNORECASE), "MEN"),
    (re.compile(r"^(W|WOMEN|F)$", re.IGNORECASE), "WOMEN"),
    (re.compile(r"^(MJR|U20 ?M(EN)?)$", re.IGNORECASE), "U20_MEN"),
    (re.compile(r"^(WJR|U20 ?W(OMEN)?|U20 ?F)$", re.IGNORECASE), "U20_WOMEN"),
]


def _classify(class_name_short: str) -> str | None:
    token = class_name_short.strip()
    for pattern, category in CLASS_PATTERNS:
        if pattern.match(token):
            return category
    return None


def _event_slug(page_url: str) -> str:
    parts = [p for p in urlparse(page_url).path.split("/") if p]
    idx = parts.index("en")
    return parts[idx + 1]


def _race_distance_m(race_class: dict) -> int | None:
    for race in race_class.get("Races") or []:
        for tp in race.get("TimingPoints", []):
            if tp.get("TimingMethod") == "Finish line":
                return tp.get("DistanceMeters")
    return None


def _race_no(race_class: dict) -> int:
    races = race_class.get("Races") or []
    return races[0]["RaceNo"] if races else 1


def discover_races(page_url: str, session: requests.Session | None = None) -> dict[str, tuple[ParsedRace, int, str]]:
    """Returns {category_code: (ParsedRace-without-results-yet, race_no, class_name_short)}."""
    sess = session or requests.Session()
    slug = _event_slug(page_url)
    base = JSON_BASE.format(slug=slug)
    resp = polite_get(base + "event.json", session=sess)
    event = resp.json()

    out: dict[str, tuple[ParsedRace, int, str]] = {}
    for race_class in event.get("Classes", []):
        category_code = _classify(race_class.get("ClassNameShort", ""))
        if category_code is None:
            continue
        parsed_race = ParsedRace(
            category_code=category_code,
            distance_m=_race_distance_m(race_class),
            name=race_class.get("ClassNameLong", race_class.get("ClassNameShort")),
            results_url=base + "resultlist.json",
        )
        out[category_code] = (parsed_race, _race_no(race_class), race_class["ClassNameShort"])
    return out


def _parse_results(payload: dict) -> list[ParsedResult]:
    results: list[ParsedResult] = []
    for row in payload.get("data", []):
        raw_name = (row.get("Name") or "").strip()
        if not raw_name:
            continue
        time_display = (row.get("Result") or "").strip() or None
        time_seconds = parse_time_to_seconds(time_display)
        status = "OK" if time_seconds is not None else "DNF"
        rank = row.get("Rank")
        results.append(
            ParsedResult(
                place=int(rank) if isinstance(rank, int) else None,
                status=status,
                raw_name=raw_name,
                raw_country=normalize_country(row.get("Nationality") or row.get("ClubNameLong")),
                raw_club=row.get("ClubNameLong"),
                bib=str(row.get("Bib")) if row.get("Bib") is not None else None,
                birth_year=None,
                time_seconds=time_seconds,
                time_display=time_display,
            )
        )
    return results


def scrape(page_url: str, session: requests.Session | None = None) -> dict[str, tuple[ParsedRace, list[ParsedResult]]]:
    sess = session or requests.Session()
    out: dict[str, tuple[ParsedRace, list[ParsedResult]]] = {}
    for category_code, (parsed_race, race_no, class_short) in discover_races(page_url, session=sess).items():
        params = {
            "ClassNameShort": class_short,
            "RaceNo": race_no,
            "Point": 0,
            "Language": "en",
        }
        resp = polite_get(
            parsed_race.results_url + "?" + "&".join(f"{k}={v}" for k, v in params.items()),
            session=sess,
        )
        results = _parse_results(resp.json())
        out[category_code] = (parsed_race, results)
    return out
