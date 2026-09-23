"""Track/road progression for Norway, Sweden, Denmark and Finland athletes,
via worldathletics.org's public athlete search and profile pages.

IMPORTANT: worldathletics.org is fronted by CloudFront and blocks
aggressively -- a single search plus one profile click was enough to get a
403 "request blocked" page during initial exploration (2026-09). Everything
here MUST go through lookup_runner's throttling with generous delays, never
be called in a tight loop, and stop immediately (raise BlockedError) at the
first sign of a block rather than retrying.

Confirmed live (2026-09) against https://worldathletics.org/athletes/norway/
kasper-fosser-014879317:
- Search results table: rows are `<tr>` with <td> cells (the header row is
  also a plain <tr>, just with <th> instead -- filter on `:has(td)`).
  Columns: name (with a nested <a href="/athletes/{country}/{slug}-{id}">),
  discipline, sex, federation (3-letter code), date of birth.
- The profile page's "STATISTICS" tab (a client-side button, not a link) has
  an "All-time personal top 10" table whose rows have 8 <td> cells: venue,
  performance, wind (usually empty), discipline, date, place, score, trailing
  empty cell. This is what we use as progression: several dated, already-
  WA-scored marks per athlete, not just their single current best.
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


def _personal_bests_needs_expanding(page) -> bool:
    """"SEE MORE PERFORMANCES" appears once per truncated section (Personal
    Bests, Season's Bests), and only when that section actually hides
    something -- an athlete with few disciplines may have it only (or not at
    all) for Season's Bests. Only the occurrence between "Personal bests"
    and "Season" belongs to Personal Bests; confirmed live 2026-09 (Kasper
    Fosser has just one, but it's for Season's Bests, not Personal Bests)."""
    text = page.inner_text("body")
    pb_start = text.find("Personal bests")
    if pb_start == -1:
        return False
    season_start = text.find("Season", pb_start)
    see_more_idx = text.find("SEE MORE PERFORMANCES", pb_start)
    return see_more_idx != -1 and (season_start == -1 or see_more_idx < season_start)


def _parse_personal_bests_table(page) -> list[dict]:
    """After clicking "SEE MORE PERFORMANCES", Personal Bests renders as a
    real <table> with 6 <td> cells per row: discipline, performance, wind,
    date, venue, score."""
    tables = page.locator("table")
    for t in range(tables.count()):
        rows = tables.nth(t).locator("tbody tr")
        if rows.count() == 0 or cells_len(rows.nth(0)) != 6:
            continue
        records = []
        for i in range(rows.count()):
            cells = rows.nth(i).locator("td")
            discipline, mark, _wind, date, venue, score = (
                cells.nth(j).inner_text().strip() for j in range(6)
            )
            records.append(
                {
                    "event": discipline,
                    "mark": mark,
                    "date": date,
                    "venue": venue or None,
                    "place": None,
                    "wa_score": int(score) if score.isdigit() else None,
                }
            )
        return records
    return []


def _parse_personal_bests_cards(page) -> list[dict]:
    """The default (unexpanded) Personal Bests layout: stacked "Label /
    value" pairs rather than a <table>, used when there's nothing to expand
    (few enough disciplines that none are hidden)."""
    text = page.inner_text("body")
    start = text.find("Personal bests")
    if start == -1:
        return []
    end = text.find("Season", start)
    block = text[start + len("Personal bests"): end if end != -1 else None]

    labels = {"Result", "Date", "Score", "Competition & venue"}
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

    entries = []
    current: dict | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("*"):  # e.g. "* Not legal"
            i += 1
            continue
        if line in labels:
            if i + 1 < len(lines):
                current[line] = lines[i + 1]
            i += 2
            continue
        if current:
            entries.append(current)
        current = {"discipline": line}
        i += 1
    if current:
        entries.append(current)

    return [
        {
            "event": e.get("discipline"),
            "mark": e.get("Result"),
            "date": e.get("Date"),
            "venue": e.get("Competition & venue"),
            "place": None,
            "wa_score": int(e["Score"]) if e.get("Score", "").isdigit() else None,
        }
        for e in entries
        if e.get("Result") and e.get("Date")
    ]


def _parse_personal_bests(page) -> list[dict]:
    """One career-PB row per discipline -- which the "All-time top 10" table
    alone can miss for an athlete whose global top-10-across-all-disciplines
    is dominated by an event we don't track (e.g. a steeplechase specialist
    whose occasional flat-race PBs never crack their own all-disciplines top
    10), or who has simply improved enough that early-career marks in a
    *tracked* event no longer rank in their own top 10 by score."""
    if _personal_bests_needs_expanding(page):
        page.get_by_text("SEE MORE PERFORMANCES").first.click()
        page.wait_for_timeout(1000)
        _check_not_blocked(page)
        return _parse_personal_bests_table(page)
    return _parse_personal_bests_cards(page)


def fetch_progression(page, profile_url: str) -> list[dict]:
    """Returns raw progression records: [{event, mark, date, venue, place,
    wa_score}, ...], combining the overview page's "Personal bests" cards
    (one career-PB row per discipline) with the Statistics tab's "All-time
    personal top 10" table (several dated, already WA-scored marks mixed
    across all disciplines) -- together giving both full per-event PB
    coverage and cross-event historical spread. Needed so we can later ask
    "what was their best *before* this Nordics race", not just their current
    all-time best."""
    page.goto(profile_url, wait_until="networkidle")
    _check_not_blocked(page)

    records = _parse_personal_bests(page)

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

    # The top-10 table has 8 <td> cells per row; the personal-bests table
    # (usually 1 row per discipline) has 8 too but with an empty discipline
    # link cell structure -- picking by cell count alone isn't reliable
    # enough, so pick the table with the most 8-cell rows.
    best_table_rows = None
    tables = page.locator("table")
    for t in range(tables.count()):
        rows = tables.nth(t).locator("tbody tr")
        count = rows.count()
        if count == 0:
            continue
        if cells_len(rows.nth(0)) == 8 and (best_table_rows is None or count > best_table_rows.count()):
            best_table_rows = rows

    if best_table_rows is None:
        # A genuinely empty profile (e.g. their only mark was wind-aided /
        # "not legal") renders "All-time personal top 10 ... No data" with no
        # <table> at all -- confirmed live 2026-09 -- which is a real, valid
        # "no progression data" outcome, not a block. Still return whatever
        # the Personal Bests cards gave us.
        if "no data" in page.inner_text("body").lower():
            return records
        raise BlockedError(
            "Could not find the all-time top-10 results table on the WA "
            "profile page -- needs a live look at the actual DOM."
        )

    for i in range(best_table_rows.count()):
        cells = best_table_rows.nth(i).locator("td")
        venue, mark, _wind, discipline, date, place, score, _ = (
            cells.nth(j).inner_text().strip() for j in range(8)
        )
        records.append(
            {
                "event": discipline,
                "mark": mark,
                "date": date,
                "venue": venue or None,
                "place": place or None,
                "wa_score": int(score) if score.isdigit() else None,
            }
        )
    return records


def cells_len(row) -> int:
    return row.locator("td").count()
