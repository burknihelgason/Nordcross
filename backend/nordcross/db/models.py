from __future__ import annotations

from sqlalchemy import (
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
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
    country_code: Mapped[str | None] = mapped_column(ForeignKey("countries.code"), nullable=True)
    birth_year: Mapped[int | None] = mapped_column(nullable=True)
    world_athletics_id: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    country: Mapped[Country | None] = relationship()


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

    time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_display: Mapped[str | None] = mapped_column(String(20), nullable=True)

    wa_points: Mapped[int | None] = mapped_column(nullable=True)

    race: Mapped[Race] = relationship(back_populates="results")
    athlete: Mapped[Athlete | None] = relationship()

    __table_args__ = (
        UniqueConstraint("race_id", "raw_name", "place", name="uq_result_race_name_place"),
    )
