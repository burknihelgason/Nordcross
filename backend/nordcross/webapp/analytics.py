"""Tab 3: the points needed for the A-class and B-class thresholds, per
category, translated into equivalent times across the tracked distance
events.

Both classes are the same kind of thing -- "N places from the top/bottom of
the field" -- independently configurable via ClassConfig (see filters.py),
rather than two different hardcoded rules. Each is a PER-RACE placing,
averaged across the selected years: 'top N' reuses the ordinary
first-to-last place, 'bottom N' reuses the Graphs tab's last-to-first
re-indexing (place counted from that race's own real finisher count), see
graphs.get_left_panel_data. Averaging each year's own Nth place keeps the
threshold anchored to a normal-sized field rather than pooling every
selected year/country into one ranked list, where "2nd-to-last" would
collapse to whichever single year happened to have the worst back-of-pack
result. Results with no WA points (progression never resolved) are already
excluded upstream by qualifying_results(), so they're simply absent from
both the per-place average and its sample count.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from nordcross.db.models import Category
from nordcross.scoring import EVENT_FILES, format_seconds, time_for_points
from nordcross.webapp.filters import SelectedFilters
from nordcross.webapp.graphs import CategoryPlaceSeries, get_left_panel_data


@dataclass
class CategoryClassPoints:
    category_code: str
    category_name: str
    a_class_points: int | None
    b_class_points: int | None


def _class_points_by_category(series_list: list[CategoryPlaceSeries], n: int) -> dict[str, int | None]:
    result = {}
    for series in series_list:
        avg_by_place = dict(zip(series.places, series.avg_points))
        result[series.category_code] = round(avg_by_place[n]) if n in avg_by_place else None
    return result


def get_class_points(session: Session, selected: SelectedFilters, categories: list[Category]) -> list[CategoryClassPoints]:
    # a_class and b_class may each want a different direction (and a
    # different N even when they share one), so compute each direction's
    # place series at most once and let both classes read from it.
    series_by_direction: dict[str, list[CategoryPlaceSeries]] = {}
    for direction in {selected.a_class.direction, selected.b_class.direction}:
        placings_mode = "first_to_last" if direction == "top" else "last_to_first"
        series_by_direction[direction] = get_left_panel_data(session, replace(selected, placings_mode=placings_mode), categories)

    a_points = _class_points_by_category(series_by_direction[selected.a_class.direction], selected.a_class.n)
    b_points = _class_points_by_category(series_by_direction[selected.b_class.direction], selected.b_class.n)

    rows = []
    for category in categories:
        if category.code not in selected.category_codes:
            continue
        rows.append(
            CategoryClassPoints(
                category_code=category.code,
                category_name=category.name,
                a_class_points=a_points.get(category.code),
                b_class_points=b_points.get(category.code),
            )
        )
    return rows


@dataclass
class EventTimeRow:
    event_code: str
    times_by_category: dict[str, str | None]  # category_code -> formatted time, or None if unratable


def get_event_time_table(class_points: list[CategoryClassPoints], class_field: str) -> list[EventTimeRow]:
    """class_field is 'b_class_points' or 'a_class_points'."""
    rows = []
    for event_code in EVENT_FILES:
        times_by_category = {}
        for cp in class_points:
            points = getattr(cp, class_field)
            if points is None:
                times_by_category[cp.category_code] = None
                continue
            seconds = time_for_points(event_code, cp.category_code, points)
            times_by_category[cp.category_code] = format_seconds(seconds) if seconds is not None else None
        rows.append(EventTimeRow(event_code=event_code, times_by_category=times_by_category))
    return rows
