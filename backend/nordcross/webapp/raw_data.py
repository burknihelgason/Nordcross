"""Tab 1: raw results grids, one per race matching the filter banner's
selected categories/years, with rows further filtered to the selected
countries."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from nordcross.db.models import Category, Championship, Race, Result
from nordcross.webapp.filters import SelectedFilters

# Non-finishers sort after finishers regardless of any stray place value the
# source recorded for them; DNS sorts after DNF/DQ.
_STATUS_SORT_RANK = {"OK": 0, "DNF": 1, "DQ": 1, "DNS": 2}


@dataclass
class RaceGrid:
    year: int
    category_name: str
    race_name: str | None
    results: list[Result]


def _sort_key(result: Result) -> tuple[int, int]:
    return (_STATUS_SORT_RANK.get(result.status, 3), result.place if result.place is not None else 9999)


def get_raw_result_grids(session: Session, selected: SelectedFilters) -> list[RaceGrid]:
    races = session.scalars(
        select(Race)
        .join(Championship)
        .join(Category)
        .where(Championship.year.in_(selected.years), Category.code.in_(selected.category_codes))
        .options(joinedload(Race.championship), joinedload(Race.category))
        .order_by(Championship.year, Category.id)
    ).all()

    grids = []
    for race in races:
        results = session.scalars(
            select(Result)
            .where(Result.race_id == race.id, Result.raw_country.in_(selected.country_codes))
            .options(joinedload(Result.athlete))
        ).all()
        if not results:
            continue
        results = sorted(results, key=_sort_key)
        grids.append(
            RaceGrid(
                year=race.championship.year,
                category_name=race.category.name,
                race_name=race.name,
                results=results,
            )
        )
    return grids
