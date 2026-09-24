"""Shared filter-banner logic: what's available to pick from, and parsing
the current selection out of the URL's query string. Every tab (raw data,
graphs, analytics) reads the same selection, so it lives here once."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from nordcross.db.models import Category, Championship, Country


@dataclass
class AvailableFilters:
    categories: list[Category]
    countries: list[Country]
    years: list[int]


PLACINGS_MODES = ("first_to_last", "last_to_first")

TABS = ("raw-data", "graphs", "analytics")

CLASS_DIRECTIONS = ("top", "bottom")


@dataclass
class ClassConfig:
    """One analytics class's definition: 'n places from the top/bottom of
    the field'. Both A-class and B-class share this shape -- they're the
    same kind of threshold, just independently dialed in by the user."""
    n: int
    direction: str  # 'top' or 'bottom'


@dataclass
class SelectedFilters:
    category_codes: list[str]
    country_codes: list[str]
    years: list[int]
    placings_mode: str = "first_to_last"
    a_class: ClassConfig = field(default_factory=lambda: ClassConfig(n=5, direction="bottom"))
    b_class: ClassConfig = field(default_factory=lambda: ClassConfig(n=2, direction="bottom"))


def get_available_filters(session: Session) -> AvailableFilters:
    categories = list(session.scalars(select(Category).order_by(Category.id)))
    countries = list(session.scalars(select(Country).order_by(Country.code)))
    years = [
        y for (y,) in session.execute(select(Championship.year).order_by(Championship.year))
    ]
    return AvailableFilters(categories=categories, countries=countries, years=years)


def parse_selected_filters(args, available: AvailableFilters) -> SelectedFilters:
    """Reads `cat`/`country`/`year` (each repeatable) from a query-string-like
    object (Flask's request.args). Unknown values are dropped rather than
    erroring, since a stale bookmark shouldn't break the page. Nothing
    selected defaults to everything available, so a first visit isn't blank."""
    valid_categories = {c.code for c in available.categories}
    valid_countries = {c.code for c in available.countries}
    valid_years = set(available.years)

    categories = [c for c in args.getlist("cat") if c in valid_categories] or [
        c.code for c in available.categories
    ]
    countries = [c for c in args.getlist("country") if c in valid_countries] or [
        c.code for c in available.countries
    ]
    years = [int(y) for y in args.getlist("year") if y.isdigit() and int(y) in valid_years] or list(
        available.years
    )
    placings_mode = args.get("placings", "first_to_last")
    if placings_mode not in PLACINGS_MODES:
        placings_mode = "first_to_last"

    a_class = _parse_class_config(args, "a_class_n", "a_class_dir", default_n=5, default_direction="bottom")
    b_class = _parse_class_config(args, "b_class_n", "b_class_dir", default_n=2, default_direction="bottom")

    return SelectedFilters(
        category_codes=categories, country_codes=countries, years=years,
        placings_mode=placings_mode, a_class=a_class, b_class=b_class,
    )


def _parse_class_config(args, n_key: str, dir_key: str, default_n: int, default_direction: str) -> ClassConfig:
    raw_n = args.get(n_key, "")
    n = int(raw_n) if raw_n.isdigit() and 1 <= int(raw_n) <= 10 else default_n
    direction = args.get(dir_key, default_direction)
    if direction not in CLASS_DIRECTIONS:
        direction = default_direction
    return ClassConfig(n=n, direction=direction)


def parse_active_tab(args) -> str:
    tab = args.get("tab", TABS[0])
    return tab if tab in TABS else TABS[0]
