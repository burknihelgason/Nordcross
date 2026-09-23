"""Track/road progression for Swedish athletes via friidrottsstatistik.se
(the Swedish Athletics Federation's own stats site). Plain server-rendered
HTML, no JS needed, no bot-protection observed -- confirmed live 2026-09
with ordinary `requests` calls.

Unlike World Athletics and Tilastopaja, this source has no automated
discovery path: its athlete name-search (/atss.php) requires a logged-in
member account, so it's not something this scraper can drive. Profile pages
themselves (atswe.php?Sex=1&ID=...) are public once you have the numeric ID,
which in practice means a human finds the ID (the site's own search once
logged in, or a general web search when the athlete is notable enough to be
indexed elsewhere) and feeds it back via `lookup-resolve athlete_id
friidrottsstatistik <ID>` -- see lookup_runner.run_friidrottsstatistik.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.friidrottsstatistik.se/atswe.php"
USER_AGENT = "nordcross-data-project/0.1 (research use; contact: burkni@expectus.is)"


def fetch_progression(athlete_id: str, sex: int) -> list[dict]:
    """Returns raw progression records: [{event, mark, date, venue}, ...],
    one per year/discipline row (that year's season best) from the profile's
    "Progression" card. `date` is a full "D.M.YYYY" string (the row gives
    year and day.month separately). `sex` is 1 for men, 2 for women (the
    site's own convention, part of the profile URL).

    Confirmed live 2026-09 against Arvid Örn's profile: each discipline is a
    <tr class="event"> header followed by a row per year with class
    "yearall-<Indoor|Outdoor><n>" (the always-visible season-best row --
    there are also individually hidden per-competition rows we skip, class
    "d-none show<...>", since a season best per year is enough for our
    "best before this date" matching)."""
    resp = requests.get(
        BASE_URL, params={"Sex": sex, "ID": athlete_id, "lang": "eng"},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    records: list[dict] = []
    current_event: str | None = None
    for row in soup.select("div.card-body table tr"):
        classes = row.get("class") or []
        if "event" in classes:
            current_event = row.get_text(strip=True)
            continue
        if not any(c.startswith("yearall-") for c in classes):
            continue
        cells = row.find_all("td")
        if current_event is None or len(cells) < 5:
            continue
        year = cells[0].get_text(strip=True)
        if not year.isdigit():
            continue
        mark = cells[1].get_text(strip=True)
        venue_cell = cells[4]
        venue_div = venue_cell.find("div", class_="plats")
        venue = venue_div.get_text(strip=True) if venue_div else None
        day_month = None
        if venue_div is not None:
            date_div = venue_div.find_next_sibling("div")
            if date_div is not None:
                day_month = date_div.get_text(strip=True)
        date = f"{day_month}.{year}" if day_month else year
        if not mark:
            continue
        records.append({"event": current_event, "mark": mark, "date": date, "venue": venue})
    return records
