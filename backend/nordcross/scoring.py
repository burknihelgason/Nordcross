"""World Athletics points for distance events (800m -> Marathon).

Data source: the official IAAF/World Athletics Outdoor 2017 Scoring Tables,
as faithfully reproduced (performance -> points, one row per point) by the
open-source project https://github.com/MaximMoinat/ScoringTablesIAAF
(Apache-2.0), which parsed the IAAF-published "IAAF Scoring Tables of
Athletics - Outdoor 2017.xls" workbook. We interpolate within each table
rather than using its regression-fit formula, to stay as close as possible
to the officially published values. This is the 2017 edition (not the more
recent 2022 revision, which is only distributed from worldathletics.org
directly); distance-event scoring did not change radically between editions.
"""

from __future__ import annotations

import bisect
import csv
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "scoring_tables"

# canonical event_code -> table filename stem (before "MALE_"/"FEMALE_" prefix)
EVENT_FILES = {
    "800m": "800m",
    "1500m": "1500m",
    "3000m": "3000m",
    "5000m": "5000m",
    "10000m": "10000m",
    "10km_road": "10_km",
    "15km_road": "15_km",
    "HM": "HM",
    "20km_road": "20_km",
    "25km_road": "25_km",
    "30km_road": "30_km",
    "Marathon": "Marathon",
}

GENDER_TO_TABLE = {"MEN": "MALE", "WOMEN": "FEMALE", "U20_MEN": "MALE", "U20_WOMEN": "FEMALE"}


@lru_cache(maxsize=None)
def _load_table(event_code: str, table_gender: str) -> tuple[list[float], list[int]]:
    stem = EVENT_FILES[event_code]
    path = DATA_DIR / f"{table_gender}_{stem}.csv"
    performances: list[float] = []
    points: list[int] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            performances.append(float(row["performance"]))
            points.append(int(row["points"]))
    return performances, points


def points_for(event_code: str, gender_category: str, time_seconds: float) -> int | None:
    """Points for a track/road time. `gender_category` is one of our own
    category codes (MEN/WOMEN/U20_MEN/U20_WOMEN); U20 uses the senior tables,
    consistent with how World Athletics scores junior performances."""
    if event_code not in EVENT_FILES:
        return None
    table_gender = GENDER_TO_TABLE.get(gender_category)
    if table_gender is None:
        return None

    performances, points = _load_table(event_code, table_gender)
    if time_seconds <= performances[0]:
        return points[0]
    if time_seconds >= performances[-1]:
        return points[-1] if time_seconds <= performances[-1] * 1.5 else None

    idx = bisect.bisect_left(performances, time_seconds)
    lo_perf, hi_perf = performances[idx - 1], performances[idx]
    lo_pts, hi_pts = points[idx - 1], points[idx]
    if hi_perf == lo_perf:
        return lo_pts
    fraction = (time_seconds - lo_perf) / (hi_perf - lo_perf)
    return round(lo_pts + fraction * (hi_pts - lo_pts))
