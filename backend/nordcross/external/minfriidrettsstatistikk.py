"""Track/road progression for Norwegian athletes via
minfriidrettsstatistikk.info. Plain server-rendered HTML (POST form), no JS,
no bot-protection and -- unlike friidrottsstatistik.se -- no login gate at
all. Confirmed live 2026-09 with ordinary `requests` calls.

Still no global athlete-name search, though: the only public browse paths
are by club roster (KlubbStatistikk.php) or national/district rankings
(LandsStatistikk.php / KretsStatistikk.php), each of which links to
UtoverStatistikk.php?showathlete=<ID>. So discovery is the same
human-in-the-loop pattern as friidrottsstatistik.se: someone finds the ID
(via this site directly, since no login is needed, or a web search for a
notable athlete) and feeds it back via `lookup-resolve <athlete_id>
minfriidrettsstatistikk <ID>`.

Progression view: POST {"athlete": <ID>, "type": "PRG"} to
UtoverStatistikk.php. Response has one <table> per discipline (preceded by
a <div id="eventheader"><h3>{discipline}</h3></div>), one row per year:
year "YYYY (age)", result, placing, club, date "DD.MM.YY", venue. Results
for running events use commas throughout as the time separator ("4,04,23"
means 4:04.23), not the colon+period we parse elsewhere -- see
_parse_norwegian_time.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.minfriidrettsstatistikk.info/php/UtoverStatistikk.php"
USER_AGENT = "nordcross-data-project/0.1 (research use; contact: burkni@expectus.is)"

_YEAR_RE = re.compile(r"^(\d{4})")
_WIND_RE = re.compile(r"\([^)]*\)")


def fetch_progression(athlete_id: str) -> list[dict]:
    """Returns raw progression records: [{event, mark, date, venue}, ...],
    one per year/discipline row (that year's season best)."""
    resp = requests.post(
        BASE_URL, data={"athlete": athlete_id, "type": "PRG"},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    records: list[dict] = []
    current_event: str | None = None
    for el in soup.find_all(["h3", "table"]):
        if el.name == "h3":
            # The site's HTML has a stray unclosed <h3>NAME<h3> (missing the
            # closing tag), which lxml parses as an outer h3 with the real
            # text plus a nested *empty* h3 -- don't let that empty one wipe
            # out the discipline name before its table is processed.
            text = el.get_text(strip=True)
            if text:
                current_event = text
            continue
        if current_event is None:
            continue
        rows = el.find_all("tr")
        for row in rows[1:]:  # skip header row
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            year_cell = cells[0].get_text(strip=True)
            m = _YEAR_RE.match(year_cell)
            if not m:
                continue
            mark = _WIND_RE.sub("", cells[1].get_text(strip=True)).strip()
            day_month_year = cells[4].get_text(strip=True)  # "DD.MM.YY"
            venue = cells[5].get("title") or cells[5].get_text(strip=True)
            if not mark:
                continue
            records.append({"event": current_event, "mark": mark, "date": day_month_year, "venue": venue})
    return records


def parse_norwegian_time(mark: str) -> float | None:
    """Norwegian running results use commas throughout as the separator
    ("4,04,23" = 4:04.23, "1,15,23,45" = 1:15:23.45), not the colon+period
    parse_time_to_seconds elsewhere expects. Only meaningful for running/
    walking events -- field events ("9,24" metres) never reach here since
    normalize_event_label already filtered to our tracked distance events
    before this is called.

    The final part's own string length matters: a single digit (e.g. the
    "3" in "2,30,3", a hand-timed result) means tenths, not hundredths --
    treating it as hundredths would silently read 2:30.3 as 2:30.03."""
    parts = mark.split(",")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    frac = nums[-1] / (10 if len(parts[-1]) == 1 else 100)
    whole = nums[:-1]
    if len(whole) == 2:
        minutes, seconds = whole
        return minutes * 60 + seconds + frac
    if len(whole) == 3:
        hours, minutes, seconds = whole
        return hours * 3600 + minutes * 60 + seconds + frac
    return None
