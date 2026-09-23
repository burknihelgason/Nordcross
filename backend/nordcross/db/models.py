from __future__ import annotations

import datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)  # NOR, SWE, DEN, FIN, ISL, ...
    name: Mapped[str] = mapped_column(String(100))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # MEN, WOMEN, U20_MEN, U20_WOMEN
    name: Mapped[str] = mapped_column(String(50))


class Championship(Base):
    __tablename__ = "championships"

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int]
    host_country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(500))

    host_country: Mapped[Country | None] = relationship()
    races: Mapped[list["Race"]] = relationship(back_populates="championship")

    __table_args__ = (UniqueConstraint("year", name="uq_championship_year"),)


class Race(Base):
    __tablename__ = "races"

    id: Mapped[int] = mapped_column(primary_key=True)
    championship_id: Mapped[int] = mapped_column(ForeignKey("championships.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    distance_m: Mapped[int | None] = mapped_column(nullable=True)

    championship: Mapped[Championship] = relationship(back_populates="races")
    category: Mapped[Category] = relationship()
    results: Mapped[list["Result"]] = relationship(back_populates="race")

    __table_args__ = (UniqueConstraint("championship_id", "category_id", name="uq_race_champ_category"),)


class Athlete(Base):
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str] = mapped_column(String(300))
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(nullable=True)
    world_athletics_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    country: Mapped[Country | None] = relationship()

    __table_args__ = (
        UniqueConstraint("country_code", "name_key", name="uq_athlete_country_namekey"),
        Index(
            "uq_athlete_world_athletics_id",
            "world_athletics_id",
            unique=True,
            mssql_where=text("world_athletics_id IS NOT NULL"),
        ),
    )


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id"))
    athlete_id: Mapped[int | None] = mapped_column(ForeignKey("athletes.id"), nullable=True)

    place: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="OK")  # OK, DNF, DNS, DQ

    raw_name: Mapped[str] = mapped_column(String(200))
    raw_country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_club: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bib: Mapped[str | None] = mapped_column(String(20), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(nullable=True)

    time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_display: Mapped[str | None] = mapped_column(String(20), nullable=True)

    wa_points: Mapped[int | None] = mapped_column(nullable=True)
    athlete_match_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'high' or 'low'

    race: Mapped[Race] = relationship(back_populates="results")
    athlete: Mapped[Athlete | None] = relationship()

    __table_args__ = (
        UniqueConstraint("race_id", "raw_name", "place", name="uq_result_race_name_place"),
    )


class AthleteProgression(Base):
    """One track/road personal-performance entry pulled from an external
    statistics source (World Athletics or Tilastopaja), used to establish the
    athlete's form at a given point in time."""

    __tablename__ = "athlete_progression"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))

    event_code: Mapped[str] = mapped_column(String(20))  # see nordcross.scoring.EVENT_FILES
    performance_seconds: Mapped[float] = mapped_column(Float)
    performance_display: Mapped[str] = mapped_column(String(20))
    date: Mapped[datetime.date] = mapped_column(Date)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    points: Mapped[int | None] = mapped_column(nullable=True)

    source: Mapped[str] = mapped_column(String(20))  # 'worldathletics' | 'tilastopaja'
    source_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)

    athlete: Mapped[Athlete] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "athlete_id", "event_code", "date", "performance_seconds",
            name="uq_progression_entry",
        ),
    )


class AthleteLookup(Base):
    """Tracks, per athlete and per external source, whether we've looked up
    their progression yet. This is the resumable queue the slow-drip runner
    works through, so a lookup is never repeated once it succeeds or
    permanently fails."""

    __tablename__ = "athlete_lookups"

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"))
    source: Mapped[str] = mapped_column(String(20))  # 'worldathletics' | 'tilastopaja'

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | done | not_found | ambiguous | failed
    external_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    match_confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 'high' | 'low'

    attempts: Mapped[int] = mapped_column(default=0)
    last_attempt_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    athlete: Mapped[Athlete] = relationship()

    __table_args__ = (UniqueConstraint("athlete_id", "source", name="uq_lookup_athlete_source"),)
