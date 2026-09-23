from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from nordcross.db.models import Category, Championship, Race, Result
from nordcross.db.session import get_session
from nordcross.scrapers.common import ParsedRace, ParsedResult


def _get_or_create_championship(
    session: Session, year: int, name: str, source_url: str, host_country_code: str | None,
    date: datetime.date | None,
) -> Championship:
    champ = session.query(Championship).filter_by(year=year).one_or_none()
    if champ is None:
        champ = Championship(
            year=year, name=name, source_url=source_url, host_country_code=host_country_code, date=date,
        )
        session.add(champ)
        session.flush()
    else:
        champ.date = date
    return champ


def _get_or_create_race(session: Session, championship: Championship, category_code: str, parsed: ParsedRace) -> Race:
    category = session.query(Category).filter_by(code=category_code).one()
    race = (
        session.query(Race)
        .filter_by(championship_id=championship.id, category_id=category.id)
        .one_or_none()
    )
    if race is None:
        race = Race(
            championship_id=championship.id,
            category_id=category.id,
            name=parsed.name,
            distance_m=parsed.distance_m,
        )
        session.add(race)
        session.flush()
    else:
        race.name = parsed.name
        race.distance_m = parsed.distance_m
    return race


def _upsert_result(session: Session, race: Race, parsed: ParsedResult) -> None:
    existing = (
        session.query(Result)
        .filter_by(race_id=race.id, raw_name=parsed.raw_name, place=parsed.place)
        .one_or_none()
    )
    if existing is None:
        existing = Result(race_id=race.id, raw_name=parsed.raw_name, place=parsed.place)
        session.add(existing)

    existing.status = parsed.status
    existing.raw_country = parsed.raw_country
    existing.raw_club = parsed.raw_club
    existing.bib = parsed.bib
    existing.birth_year = parsed.birth_year
    existing.time_seconds = parsed.time_seconds
    existing.time_display = parsed.time_display


def store_championship_results(
    year: int,
    name: str,
    source_url: str,
    scraped: dict[str, tuple[ParsedRace, list[ParsedResult]]],
    host_country_code: str | None = None,
    date: datetime.date | None = None,
) -> None:
    session = get_session()
    try:
        championship = _get_or_create_championship(session, year, name, source_url, host_country_code, date)
        for category_code, (parsed_race, parsed_results) in scraped.items():
            race = _get_or_create_race(session, championship, category_code, parsed_race)
            for parsed_result in parsed_results:
                _upsert_result(session, race, parsed_result)
        session.commit()
    finally:
        session.close()
