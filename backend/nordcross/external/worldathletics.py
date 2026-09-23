"""Track/road progression for Norway, Sweden, Denmark and Finland athletes,
via worldathletics.org's public athlete search and profile pages.

IMPORTANT: worldathletics.org is fronted by CloudFront and blocks
aggressively -- a single search plus one profile click was enough to get a
403 "request blocked" page during initial exploration (2026-09). Everything
here MUST go through lookup_runner's throttling with generous delays, never
be called in a tight loop, and stop immediately (raise BlockedError) at the
first sign of a block rather than retrying.

The search UI and its results table (Name / Discipline / Sex / Federation /
Date of birth, profile links shaped /athletes/{country-slug}/{name-slug}-
{waId}) were confirmed live. The profile page's progression/PB section was
NOT reached before the block hit, so `fetch_progression` below is a
best-effort DOM search that raises clearly if it can't find something
recognizable -- treat the first real run as the verification pass and fix
the selectors against an actual profile page rather than trusting this
blindly.
"""

from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

from nordcross.external.common import BlockedError

BASE_PAGE = "https://worldathletics.org/athletes"
PROFILE_ID_RE = re.compile(r"-(\d+)$")

EVENT_NAME_MAP = {
    "800 Metres": "800m", "800m": "800m",
    "1500 Metres": "1500m", "1500m": "1500m",
    "3000 Metres": "3000m", "3000m": "3000m",
    "5000 Metres": "5000m", "5000m": "5000m",
    "10,000 Metres": "10000m", "10000 Metres": "10000m", "10000m": "10000m",
    "10 Kilometres": "10km_road", "10km": "10km_road",
    "15 Kilometres": "15km_road",
    "Half Marathon": "HM", "HM": "HM",
    "20 Kilometres": "20km_road",
    "25 Kilometres": "25km_road",
    "30 Kilometres": "30km_road",
    "Marathon": "Marathon",
}


def open_session(user_data_dir: str, headless: bool = True):
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(user_data_dir, headless=headless)
    page = context.new_page()
    page.goto(BASE_PAGE, wait_until="networkidle")
    _dismiss_cookie_banner(page)
    return pw, context, page


def close_session(pw, context) -> None:
    context.close()
    pw.stop()


def _dismiss_cookie_banner(page) -> None:
    try:
        page.get_by_text("Use necessary cookies only", exact=True).click(timeout=3000)
    except Exception:
        pass


def _check_not_blocked(page) -> None:
    title = page.title()
    if "error" in title.lower() or "blocked" in page.content()[:2000].lower():
        raise BlockedError(f"worldathletics.org appears to be blocking us (title={title!r})")


def search_athlete(page, name: str) -> list[dict]:
    """Returns candidate rows: [{name, discipline, sex, federation, dob, profile_url}, ...]"""
    page.goto(BASE_PAGE, wait_until="networkidle")
    _check_not_blocked(page)
    _dismiss_cookie_banner(page)

    search_box = page.locator("input[type='search']").first
    search_box.click()
    search_box.fill(name)
    search_box.press("Enter")
    page.wait_for_timeout(2000)
    _check_not_blocked(page)

    rows = page.locator("table tbody tr")
    results = []
    for i in range(rows.count()):
        row = rows.nth(i)
        link = row.locator("a").first
        href = link.get_attribute("href") or ""
        cells = row.locator("td")
        results.append(
            {
                "name": link.inner_text().strip(),
                "profile_url": href if href.startswith("http") else f"https://worldathletics.org{href}",
                "sex": cells.nth(1).inner_text().strip() if cells.count() > 1 else "",
                "federation": cells.nth(2).inner_text().strip() if cells.count() > 2 else "",
                "dob": cells.nth(3).inner_text().strip() if cells.count() > 3 else "",
            }
        )
    return results


def profile_id_from_url(profile_url: str) -> str | None:
    m = PROFILE_ID_RE.search(profile_url.rstrip("/"))
    return m.group(1) if m else None


def fetch_progression(page, profile_url: str) -> list[dict]:
    """Returns raw progression records: [{event, mark, date, venue}, ...].
    UNVERIFIED against a real profile page -- see module docstring."""
    page.goto(profile_url, wait_until="networkidle")
    _check_not_blocked(page)

    progression_link = page.get_by_text(re.compile("progression", re.IGNORECASE))
    if progression_link.count() == 0:
        raise BlockedError(
            "Could not find a 'Progression' section on the WA profile page -- "
            "page layout differs from what this scraper expects; needs a live "
            "look at the actual DOM (see worldathletics.py docstring)."
        )
    progression_link.first.click()
    page.wait_for_timeout(1500)
    _check_not_blocked(page)

    rows = page.locator("table tbody tr")
    records = []
    for i in range(rows.count()):
        cells = rows.nth(i).locator("td")
        if cells.count() < 3:
            continue
        records.append(
            {
                "event": cells.nth(0).inner_text().strip(),
                "mark": cells.nth(1).inner_text().strip(),
                "date": cells.nth(2).inner_text().strip(),
                "venue": cells.nth(3).inner_text().strip() if cells.count() > 3 else None,
            }
        )
    return records
