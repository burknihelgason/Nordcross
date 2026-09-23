"""Track/road progression for Norway, Sweden, Denmark and Finland athletes,
via worldathletics.org's public athlete search and profile pages.

IMPORTANT: worldathletics.org is fronted by CloudFront and blocks
aggressively -- a single search plus one profile click was enough to get a
403 "request blocked" page during initial exploration (2026-09). Everything
here MUST go through lookup_runner's throttling with generous delays, never
be called in a tight loop, and stop immediately (raise BlockedError) at the
first sign of a block rather than retrying.

Confirmed live (2026-09):
- Search results table (https://worldathletics.org/athletes/norway/
  kasper-fosser-014879317's search): rows are `<tr>` with <td> cells (the
  header row is also a plain <tr>, just with <th> instead -- filter on
  `:has(td)`). Columns: name (with a nested
  <a href="/athletes/{country}/{slug}-{id}">), discipline, sex, federation
  (3-letter code), date of birth.
- The profile page's "STATISTICS" tab (a client-side button, not a link) has
  a "Progression" sub-tab: one <table class="...progression..."> per
  discipline (its name in a `div[class*="athletesTitle"]` inside the table,
  oddly placed between <thead> and <tbody> but still a descendant), each row
  a year's season best with 5 <td> cells: year, performance, wind, venue
  (a competition-results link), date. This is what we use as progression --
  see fetch_progression's docstring for why (a real case, not a guess).
"""

from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

from nordcross.external.common import BlockedError
from nordcross.scoring import normalize_event_label

BASE_PAGE = "https://worldathletics.org/athletes"
PROFILE_ID_RE = re.compile(r"-(\d+)$")


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

    # The results table's header row is a plain <tr><th>...</th></tr> inside
    # the same <tbody> (confirmed live 2026-09), so filter to rows that
    # actually have <td> cells rather than assuming row 0 is a data row.
    rows = page.locator("table tbody tr:has(td)")
    results = []
    for i in range(rows.count()):
        row = rows.nth(i)
        cells = row.locator("td")
        if cells.count() < 5:
            continue
        link = cells.nth(0).locator("a").first
        href = link.get_attribute("href") or ""
        results.append(
            {
                "name": link.inner_text().strip(),
                "profile_url": href if href.startswith("http") else f"https://worldathletics.org{href}",
                "discipline": cells.nth(1).inner_text().strip(),
                "sex": cells.nth(2).inner_text().strip(),
                "federation": cells.nth(3).inner_text().strip(),
                "dob": cells.nth(4).inner_text().strip(),
            }
        )
    return results


def profile_id_from_url(profile_url: str) -> str | None:
    m = PROFILE_ID_RE.search(profile_url.rstrip("/"))
    return m.group(1) if m else None


def fetch_progression(page, profile_url: str) -> list[dict]:
    """Returns raw progression records: [{event, mark, date, venue}, ...]
    from the Statistics tab's "Progression" sub-tab: one table per
    discipline, one row per year, showing that year's season best. This is
    a direct year-by-year history (confirmed live 2026-09 against Helga
    Lilja Maack, an 18-year-old whose real history goes back to 2023) --
    exactly what "what was their best *before* this Nordics race" needs,
    unlike the "All-time personal top 10 across all disciplines" table this
    function used previously, which silently drops an athlete's older
    marks in any event that isn't their main specialty (older marks rank
    low against their own more recent bests, so they fall out of a mixed
    top-10-by-score list entirely -- discovered via a real case, Eero
    Heinonen, a steeplechase specialist whose flat-race history looked like
    it started "this year" when it didn't).

    No WA "Score" column here, unlike the top-10/personal-bests views --
    points are computed from our own scoring tables instead (see
    lookup_runner._store_progression)."""
    page.goto(profile_url, wait_until="networkidle")
    _check_not_blocked(page)

    stats_button = page.get_by_text("STATISTICS", exact=True)
    if stats_button.count() == 0:
        raise BlockedError(
            "Could not find the STATISTICS tab on the WA profile page -- "
            "page layout differs from what this scraper expects; needs a live "
            "look at the actual DOM (see worldathletics.py docstring)."
        )
    stats_button.first.click()
    page.wait_for_timeout(1500)
    _check_not_blocked(page)

    progression_tab = page.get_by_text("Progression", exact=True)
    if progression_tab.count() == 0:
        # A brand-new athlete with no results yet renders Statistics with no
        # Progression sub-tab at all -- a real "nothing to show" outcome.
        return []
    progression_tab.first.click()
    page.wait_for_timeout(1500)
    _check_not_blocked(page)

    expand_all = page.get_by_text("Expand All", exact=True)
    if expand_all.count() > 0:
        expand_all.first.click()
        page.wait_for_timeout(1000)

    records = []
    tables = page.locator("table.profileStatistics_progression__3D0tn")
    for t in range(tables.count()):
        table = tables.nth(t)
        title_el = table.locator('div[class*="athletesTitle"]').first
        discipline = title_el.inner_text().strip() if title_el.count() > 0 else None
        if not discipline:
            continue
        rows = table.locator("tbody tr")
        for i in range(rows.count()):
            cells = rows.nth(i).locator("td")
            if cells.count() < 5:
                continue
            year, mark, _wind, venue, date = (cells.nth(j).inner_text().strip() for j in range(5))
            if not mark or not date:
                continue
            records.append({"event": discipline, "mark": mark, "date": date, "venue": venue or None})
    return records
