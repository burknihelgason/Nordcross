"""Tab 2: the two graph panels.

Left panel: for each selected category, average WA points by finishing
place, averaged over the selected years (and restricted to the selected
countries). Right panel: for each selected category, the cumulative
distribution of WA points across all qualifying results.

`Result.wa_points` only stores the number -- to build the tooltip format the
design doc specifies ("2021 SWE 1500m 987pts") we need the specific event
that produced it, so we re-derive the same "best progression strictly before
the race date" lookup that progression_matching.match_wa_points() uses, this
time keeping the AthleteProgression row rather than just its points value.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from nordcross.db.models import AthleteProgression, Category, Championship, Race, Result
from nordcross.webapp.filters import SelectedFilters


@dataclass
class TooltipPoint:
    year: int
    country: str
    event_code: str
    points: int


@dataclass
class CategoryPlaceSeries:
    category_code: str
    category_name: str
    places: list[int] = field(default_factory=list)
    avg_points: list[float] = field(default_factory=list)
    tooltips: dict[int, list[TooltipPoint]] = field(default_factory=dict)


@dataclass
class CategoryCdfSeries:
    category_code: str
    category_name: str
    points: list[int] = field(default_factory=list)
    cumulative_pct: list[float] = field(default_factory=list)


def qualifying_results(session: Session, selected: SelectedFilters, category_code: str, require_place: bool):
    query = (
        select(Result)
        .join(Race)
        .join(Championship)
        .join(Category)
        .where(
            Championship.year.in_(selected.years),
            Category.code == category_code,
            Result.raw_country.in_(selected.country_codes),
            Result.athlete_id.isnot(None),
            Result.wa_points.isnot(None),
        )
        .options(joinedload(Result.race).joinedload(Race.championship))
    )
    if require_place:
        query = query.where(Result.place.isnot(None), Result.status == "OK")
    return session.scalars(query).all()


def _best_progression_event(session: Session, athlete_id: int, race_date) -> AthleteProgression | None:
    return session.scalars(
        select(AthleteProgression)
        .where(
            AthleteProgression.athlete_id == athlete_id,
            AthleteProgression.date < race_date,
            AthleteProgression.points.isnot(None),
        )
        .order_by(AthleteProgression.points.desc())
        .limit(1)
    ).first()


def _race_finisher_counts(session: Session, race_ids: set[int]) -> dict[int, int]:
    """Total OK finishers per race, counted across ALL countries regardless
    of the country filter -- "last to first" needs to anchor to the real
    size of the field, not an artificially shrunk one."""
    if not race_ids:
        return {}
    rows = session.execute(
        select(Result.race_id, func.count())
        .where(Result.race_id.in_(race_ids), Result.status == "OK", Result.place.isnot(None))
        .group_by(Result.race_id)
    ).all()
    return dict(rows)


def get_left_panel_data(session: Session, selected: SelectedFilters, categories: list[Category]) -> list[CategoryPlaceSeries]:
    series_list = []
    for category in categories:
        if category.code not in selected.category_codes:
            continue
        results = qualifying_results(session, selected, category.code, require_place=True)

        if selected.placings_mode == "last_to_first":
            finisher_counts = _race_finisher_counts(session, {r.race_id for r in results})

        by_place: dict[int, list[Result]] = {}
        for r in results:
            if selected.placings_mode == "last_to_first":
                effective_place = finisher_counts[r.race_id] - r.place + 1
            else:
                effective_place = r.place
            by_place.setdefault(effective_place, []).append(r)

        series = CategoryPlaceSeries(category_code=category.code, category_name=category.name)
        for place in sorted(by_place):
            rows = by_place[place]
            series.places.append(place)
            series.avg_points.append(sum(r.wa_points for r in rows) / len(rows))

            tooltip_points = []
            for r in rows:
                race_date = r.race.championship.date
                progression = _best_progression_event(session, r.athlete_id, race_date) if race_date else None
                tooltip_points.append(
                    TooltipPoint(
                        year=r.race.championship.year,
                        country=r.raw_country,
                        event_code=progression.event_code if progression else "?",
                        points=r.wa_points,
                    )
                )
            series.tooltips[place] = tooltip_points
        series_list.append(series)
    return series_list


def get_right_panel_data(session: Session, selected: SelectedFilters, categories: list[Category]) -> list[CategoryCdfSeries]:
    series_list = []
    for category in categories:
        if category.code not in selected.category_codes:
            continue
        results = qualifying_results(session, selected, category.code, require_place=False)
        points_sorted = sorted(r.wa_points for r in results)

        series = CategoryCdfSeries(category_code=category.code, category_name=category.name)
        n = len(points_sorted)
        for i, pts in enumerate(points_sorted, start=1):
            series.points.append(pts)
            series.cumulative_pct.append(round(100 * i / n, 2))
        series_list.append(series)
    return series_list
