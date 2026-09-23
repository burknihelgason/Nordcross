"""Iceland's athlete progression, via afrekaskra.fri.is (a Tilastopaja Oy
site). The public site is a Vue SPA calling a JSON API at
www.tilastopaja.info with a client-embedded API key; that API returns empty
bodies to plain HTTP clients (bot protection), so every call here runs
in-page via a real (Playwright) browser's fetch(), exactly like the site
itself does. Verified against a live search call once (2026-09); the
per-athlete progression endpoint shape below has NOT yet been confirmed
against a real response — treat the first production run as the
verification pass and adjust EVENT_NAME_MAP / _extract_marks accordingly.

Be conservative: this API went from working to returning empty bodies after
a modest burst of exploratory calls in one session. Always go through
lookup_runner's throttling, never call these functions in a tight loop.
"""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

from nordcross.external.common import BlockedError

BASE_PAGE = "https://afrekaskra.fri.is/isl/"
API_ROOT = "https://www.tilastopaja.info/api/isl"

# Tilastopaja groups an athlete's progression under a couple of report types;
# 'sb' ~ "þróun árangurs" (progression of results) is the one we want.
PROGRESSION_TYPE = "sb"

GENDER_TOKEN_CANDIDATES_BY_CATEGORY = {
    "MEN": ["men", "M"],
    "U20_MEN": ["men", "M"],
    "WOMEN": ["women", "F"],
    "U20_WOMEN": ["women", "F"],
}

# Maps event labels as they might appear in Tilastopaja output to our own
# canonical event codes (see nordcross.scoring.EVENT_FILES). Unverified --
# extend once real responses are seen.
EVENT_NAME_MAP = {
    "800m": "800m", "800 m": "800m",
    "1500m": "1500m", "1500 m": "1500m",
    "3000m": "3000m", "3000 m": "3000m",
    "5000m": "5000m", "5000 m": "5000m",
    "10000m": "10000m", "10,000m": "10000m", "10 000m": "10000m",
    "10 km": "10km_road", "10km": "10km_road", "10 km väg": "10km_road",
    "15 km": "15km_road",
    "Half Marathon": "HM", "HM": "HM", "Halvmaraton": "HM",
    "20 km": "20km_road",
    "25 km": "25km_road",
    "30 km": "30km_road",
    "Marathon": "Marathon", "Maraþon": "Marathon",
}


def open_session(user_data_dir: str, headless: bool = True):
    """Persistent browser profile so repeated slow-drip runs look like the
    same returning visitor, not a fresh headless session each time."""
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(user_data_dir, headless=headless)
    page = context.new_page()
    page.goto(BASE_PAGE, wait_until="networkidle")
    return pw, context, page


def close_session(pw, context) -> None:
    context.close()
    pw.stop()


def _fetch_json(page, url: str) -> dict:
    result = page.evaluate(
        """async (url) => {
            const resp = await fetch(url, { headers: { 'Authorization': auth, 'x-site': site } });
            const text = await resp.text();
            return { status: resp.status, text };
        }""",
        url,
    )
    if result["status"] != 200 or not result["text"]:
        raise BlockedError(
            f"Tilastopaja returned status={result['status']} (empty body) for {url}"
        )
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as e:
        raise BlockedError(f"Tilastopaja returned non-JSON for {url}: {result['text'][:200]!r}") from e


def _find_athlete_records(node) -> list[dict]:
    """Recursively find dicts that look like athlete search hits (they carry
    an 'athleteId' key), since the exact response envelope wasn't confirmed
    before this module was written."""
    found = []
    if isinstance(node, dict):
        if "athleteId" in node and "name" in node:
            found.append(node)
        else:
            for v in node.values():
                found.extend(_find_athlete_records(v))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_athlete_records(item))
    return found


def search_athlete(page, query: str) -> list[dict]:
    """Returns candidate matches: [{athleteId, name, country, countryIso2,
    dateOfBirth|yearOfBirth, minYear, maxYear, events}, ...]"""
    data = _fetch_json(page, f"{API_ROOT}/athletes/search?query={query}")
    return _find_athlete_records(data)


def _find_mark_records(node) -> list[dict]:
    """Recursively find dicts that look like a single performance entry.
    Unverified shape -- looks for a mark/result-like key plus a date-like key."""
    mark_keys = {"mark", "result", "performance", "value"}
    date_keys = {"date", "compDate", "resultDate"}
    found = []
    if isinstance(node, dict):
        if mark_keys & node.keys() and date_keys & node.keys():
            found.append(node)
        else:
            for v in node.values():
                found.extend(_find_mark_records(v))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_mark_records(item))
    return found


def fetch_progression(page, athlete_id: str, category_code: str) -> list[dict]:
    """Returns raw progression records for one athlete. Tries a couple of
    gender-token spellings in the URL since the correct one wasn't confirmed
    live; stops at the first that returns any records."""
    last_error = None
    for gender_token in GENDER_TOKEN_CANDIDATES_BY_CATEGORY.get(category_code, ["men", "women"]):
        url = f"{API_ROOT}/athletes/{gender_token}/{athlete_id}/{PROGRESSION_TYPE}"
        try:
            data = _fetch_json(page, url)
        except BlockedError as e:
            last_error = e
            continue
        records = _find_mark_records(data)
        if records:
            return records
    if last_error:
        raise last_error
    return []
