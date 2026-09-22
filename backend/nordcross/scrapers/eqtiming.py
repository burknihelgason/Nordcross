from __future__ import annotations

import re

import requests

from nordcross.scrapers.common import (
    ParsedRace,
    ParsedResult,
    guess_category,
    guess_distance_m,
    normalize_country,
    parse_time_to_seconds,
    polite_get,
)

API_BASE = "https://live.eqtiming.com/api"
LINK_RE = re.compile(r"live\.eqtiming\.com/(\d+)#result:(\d+)-\d+-(\d+)-")


def discover_races(source_page_url: str, session: requests.Session | None = None) -> dict[str, dict]:
    """Parse an article page for eqtiming result links and classify them by their link text."""
    resp = polite_get(source_page_url, session=session)
    from bs4 import BeautifulSoup  # local import keeps common.py light

    soup = BeautifulSoup(resp.text, "lxml")

    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        m = LINK_RE.search(a["href"])
        if not m:
            continue
        label = a.get_text(strip=True)
        category_code = guess_category(label)
        if category_code is None:
            continue
        event_id, class_id, station_id = m.groups()
        out[category_code] = {
            "event_id": event_id,
            "class_id": class_id,
            "station_id": station_id,
            "label": label,
        }
    return out


def _build_contestant_lookup(event_id: str, session: requests.Session) -> dict[int, dict]:
    resp = polite_get(f"{API_BASE}/Contestants/{event_id}", session=session)
    contestants = resp.json()
    lookup: dict[int, dict] = {}
    for contestant in contestants.values():
        for ed_uid in contestant.get("EtappeDeltaker", {}):
            lookup[int(ed_uid)] = contestant
    return lookup


def scrape(source_page_url: str, session: requests.Session | None = None) -> dict[str, tuple[ParsedRace, list[ParsedResult]]]:
    sess = session or requests.Session()
    races = discover_races(source_page_url, session=sess)
    if not races:
        return {}

    event_id = next(iter(races.values()))["event_id"]
    contestant_lookup = _build_contestant_lookup(event_id, session=sess)

    out: dict[str, tuple[ParsedRace, list[ParsedResult]]] = {}
    for category_code, info in races.items():
        url = (
            f"{API_BASE}/Result/Total/{info['event_id']}/{info['class_id']}"
            f"?justTimeData=true&count=500&startAt=1&station={info['station_id']}"
            "&query=&round=1&passes=false"
        )
        resp = polite_get(url, session=sess)
        items = resp.json().get("Items", [])

        results: list[ParsedResult] = []
        for item in items:
            contestant = contestant_lookup.get(item.get("EtappeDeltakerUID"))
            if contestant is None:
                continue
            athlete = contestant["Utover"]
            status_text = (item.get("StatusTekst") or "").upper()
            status = "OK" if status_text == "TIME" else (status_text or "DNF")
            time_display = item.get("Formatert") if status == "OK" else None
            time_seconds = parse_time_to_seconds(time_display)

            results.append(
                ParsedResult(
                    place=item.get("Plassering", {}).get("Total"),
                    status=status,
                    raw_name=athlete.get("NavnFormatert", "").strip(),
                    raw_country=normalize_country(athlete.get("Land", {}).get("IOC")),
                    raw_club=athlete.get("Klubbnavn") or None,
                    bib=str(contestant.get("Startnummer")) if contestant.get("Startnummer") else None,
                    birth_year=athlete.get("Aar"),
                    time_seconds=time_seconds,
                    time_display=time_display,
                )
            )

        distance_m = guess_distance_m(info["label"]) or (6000 if "U20" in category_code else 9000)
        parsed_race = ParsedRace(
            category_code=category_code,
            distance_m=distance_m,
            name=info["label"],
            results_url=url,
        )
        out[category_code] = (parsed_race, results)
    return out
