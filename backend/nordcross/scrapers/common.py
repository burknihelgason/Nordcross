from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import requests

USER_AGENT = "nordcross-data-project/0.1 (research use; contact: burkni@expectus.is)"

COUNTRY_ALIASES = {
    "SWE": "SWE", "SWEDEN": "SWE", "SVERIGE": "SWE",
    "NOR": "NOR", "NORWAY": "NOR", "NORGE": "NOR",
    "DEN": "DEN", "DNK": "DEN", "DENMARK": "DEN", "DANMARK": "DEN",
    "FIN": "FIN", "FINLAND": "FIN", "SUOMI": "FIN",
    "ISL": "ISL", "ICELAND": "ISL", "ISLAND": "ISL", "ÍSLAND": "ISL",
}

# Statuses that mean "no time recorded" rather than a race result
NON_FINISH_STATUSES = {"DNS", "DNF", "DQ", "DSQ"}

TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})(?:\.(\d+))?$")
TIME_RE_SHORT = re.compile(r"^(\d{1,2}):(\d{2})(?:\.(\d+))?$")


def polite_get(url: str, session: requests.Session | None = None, delay: float = 1.0) -> requests.Response:
    """Fetch a URL with a descriptive UA and a small delay to avoid hammering small results sites."""
    sess = session or requests
    resp = sess.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    if delay:
        time.sleep(delay)
    return resp


def normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().upper()
    return COUNTRY_ALIASES.get(key)


def parse_time_to_seconds(raw: str | None) -> float | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw or raw.upper() in NON_FINISH_STATUSES:
        return None
    m = TIME_RE.match(raw)
    if m:
        h, mnt, s, frac = m.groups()
        total = int(h) * 3600 + int(mnt) * 60 + int(s)
        if frac:
            total += float("0." + frac)
        return float(total)
    m = TIME_RE_SHORT.match(raw)
    if m:
        mnt, s, frac = m.groups()
        total = int(mnt) * 60 + int(s)
        if frac:
            total += float("0." + frac)
        return float(total)
    return None


def status_from_time_cell(raw: str | None) -> str:
    if not raw:
        return "DNS"
    key = raw.strip().upper()
    if key in NON_FINISH_STATUSES:
        return key if key != "DSQ" else "DQ"
    return "OK"


@dataclass
class ParsedRace:
    category_code: str
    distance_m: int | None
    name: str
    results_url: str


@dataclass
class ParsedResult:
    place: int | None
    status: str
    raw_name: str
    raw_country: str | None
    raw_club: str | None
    bib: str | None
    birth_year: int | None
    time_seconds: float | None
    time_display: str | None


def guess_category(label: str) -> str | None:
    """Map a free-text event label (varies per site/year/language) to one of our 4 category codes."""
    text = label.upper()
    is_u20 = bool(re.search(r"\bU20\b|JUNIOR", text))
    is_women = bool(re.search(r"WOMEN|WOMAN|KONUR|KVINNOR|KVINDER|NAISET|KONUR", text))
    is_men = bool(re.search(r"\bMEN\b|MENN|KARLAR|HERRAR|HERRER|MIEHET", text))

    if is_women and not is_men:
        return "U20_WOMEN" if is_u20 else "WOMEN"
    if is_men and not is_women:
        return "U20_MEN" if is_u20 else "MEN"
    return None


def guess_distance_m(label: str) -> int | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*km", label, re.IGNORECASE)
    if m:
        return round(float(m.group(1).replace(",", ".")) * 1000)
    m = re.search(r"(\d{3,5})\s*m\b", label, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None
