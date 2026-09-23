"""Tab 3: the points needed for "B-class" (better than second-to-last
place) and "A-class" (better than 5th-to-last place), per category,
translated into equivalent times across the tracked distance events.

Both classes are computed against the pooled field of qualifying results
for a category across the selected years/countries (the same population as
the Tab 2 right-panel CDF), not per individual race -- the design doc wants
one representative points figure per category for the current selection.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from nordcross.db.models import Category
from nordcross.scoring import EVENT_FILES, format_seconds, time_for_points
from nordcross.webapp.filters import SelectedFilters
from nordcross.webapp.graphs import qualifying_results


@dataclass
class CategoryClassPoints:
    category_code: str
    category_name: str
    b_class_points: int | None
    a_class_points: int | None


def _b_class_points(sorted_points: list[int]) -> int | None:
    """Second-to-last place = the second-worst performer, i.e. the second
    value from the bottom of the ascending-sorted field (index 1)."""
    if not sorted_points:
        return None
    if len(sorted_points) == 1:
        return sorted_points[0]
    return sorted_points[1]


def _a_class_points(sorted_points: list[int]) -> int | None:
    """5th-to-last place = the 5th-worst performer, i.e. the 5th value from
    the bottom of the ascending-sorted field (index 4). Falls back to the
    weakest performer available when the field has fewer than 5."""
    if not sorted_points:
        return None
    idx = min(4, len(sorted_points) - 1)
    return sorted_points[idx]


def get_class_points(session: Session, selected: SelectedFilters, categories: list[Category]) -> list[CategoryClassPoints]:
    rows = []
    for category in categories:
        if category.code not in selected.category_codes:
            continue
        results = qualifying_results(session, selected, category.code, require_place=False)
        sorted_points = sorted(r.wa_points for r in results)
        rows.append(
            CategoryClassPoints(
                category_code=category.code,
                category_name=category.name,
                b_class_points=_b_class_points(sorted_points),
                a_class_points=_a_class_points(sorted_points),
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
