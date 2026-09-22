from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

from nordcross.scrapers.common import (
    ParsedRace,
    ParsedResult,
    guess_category,
    guess_distance_m,
    normalize_country,
    parse_time_to_seconds,
    status_from_time_cell,
)

# Roster Athletics is an Angular SPA with no plain HTTP results API we could find
# (data appears to arrive over a websocket/blob channel), so we render it with a
# real (headless) browser instead of requests+BeautifulSoup like the other sources.

EXTRACT_ROWS_JS = """
() => {
  const table = document.querySelector('table.rs-mat-table-compat');
  if (!table) return [];
  const rows = Array.from(table.querySelectorAll('tr')).filter(r => r.querySelectorAll('td').length >= 5);
  return rows.map(row => {
    const tds = row.querySelectorAll('td');
    const placeText = tds[0].textContent.trim();
    const athleteCell = tds[1];
    const nameEl = athleteCell.querySelector('a.athlete-name');
    const name = nameEl ? nameEl.textContent.trim() : '';
    const dobDiv = athleteCell.querySelector('.dob');
    const dobText = dobDiv ? dobDiv.textContent.replace(/\\u00a0/g, ' ').trim() : '';
    const bib = tds[2].textContent.trim();
    const team = tds[3].textContent.trim();
    const resultText = tds[tds.length - 1].textContent.replace(/\\u00a0/g, ' ').trim();
    return {placeText, name, dobText, bib, team, resultText};
  });
}
"""


def _accept_cookies(page) -> None:
    try:
        page.get_by_text("Accept", exact=True).click(timeout=2000)
    except Exception:
        pass


def _parse_dob_text(dob_text: str) -> tuple[int | None, str | None]:
    parts = [p.strip() for p in dob_text.split("·") if p.strip()]
    birth_year = None
    country = None
    if parts:
        if parts[0].isdigit():
            birth_year = int(parts[0])
        country = normalize_country(parts[-1])
    return birth_year, country


def scrape(schedule_url: str, headless: bool = True) -> dict[str, tuple[ParsedRace, list[ParsedResult]]]:
    out: dict[str, tuple[ParsedRace, list[ParsedResult]]] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(schedule_url, wait_until="networkidle")
        _accept_cookies(page)
        page.wait_for_timeout(500)

        cells = page.locator("td.clickable")
        race_defs: list[tuple[str, str, int]] = []
        for i in range(cells.count()):
            label = re.sub(r"\s+", " ", cells.nth(i).inner_text()).strip()
            category_code = guess_category(label)
            if category_code:
                race_defs.append((category_code, label, i))

        for category_code, label, idx in race_defs:
            page.goto(schedule_url, wait_until="networkidle")
            _accept_cookies(page)
            page.locator("td.clickable").nth(idx).click()
            page.wait_for_url(re.compile(r"meId="), timeout=15000)
            page.wait_for_selector("table.rs-mat-table-compat tr", timeout=15000)
            page.wait_for_timeout(300)

            rows = page.evaluate(EXTRACT_ROWS_JS)
            results: list[ParsedResult] = []
            for row in rows:
                raw_name = row["name"].strip()
                if not raw_name:
                    continue
                birth_year, country = _parse_dob_text(row["dobText"])
                place_raw = row["placeText"].strip()
                result_text = row["resultText"].strip()
                results.append(
                    ParsedResult(
                        place=int(place_raw) if place_raw.isdigit() else None,
                        status=status_from_time_cell(result_text),
                        raw_name=raw_name,
                        raw_country=country,
                        raw_club=row["team"].strip() or None,
                        bib=row["bib"].strip() or None,
                        birth_year=birth_year,
                        time_seconds=parse_time_to_seconds(result_text),
                        time_display=result_text or None,
                    )
                )

            distance_m = guess_distance_m(label) or (4500 if "U20" in category_code else 7500)
            out[category_code] = (
                ParsedRace(
                    category_code=category_code,
                    distance_m=distance_m,
                    name=label,
                    results_url=page.url,
                ),
                results,
            )

        browser.close()

    return out
