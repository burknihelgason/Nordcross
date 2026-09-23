"""Step 3: for every Nordic result, find the athlete's best (highest-points)
progression entry from strictly before the race date, and store it as
Result.wa_points.

Fully idempotent and cheap to re-run -- it always recomputes from whatever
is currently in athlete_progression, so re-running after manual review adds
more matches/PRs (see lookup_queue.py's manual_url and add_manual_progression
below) just picks up the improvements automatically. There is no reason to
run this incrementally; always recompute for every result.
"""

from __future__ import annotations

import datetime

from nordcross.db.models import Athlete, AthleteProgression, Category, Race, Result
from nordcross.db.session import get_session


def match_wa_points() -> dict[str, int]:
    session = get_session()
    try:
        results = (
            session.query(Result)
            .filter(Result.athlete_id.isnot(None))
            .all()
        )
        matched = 0
        no_race_date = 0
        no_progression = 0
        for result in results:
            race_date = result.race.championship.date
            if race_date is None:
                no_race_date += 1
                result.wa_points = None
                continue
            best = (
                session.query(AthleteProgression)
                .filter(
                    AthleteProgression.athlete_id == result.athlete_id,
                    AthleteProgression.date < race_date,
                    AthleteProgression.points.isnot(None),
                )
                .order_by(AthleteProgression.points.desc())
                .first()
            )
            if best is None:
                no_progression += 1
                result.wa_points = None
            else:
                result.wa_points = best.points
                matched += 1
        session.commit()
        return {"matched": matched, "no_race_date": no_race_date, "no_progression_before_race": no_progression}
    finally:
        session.close()


def add_manual_progression(
    athlete_id: int, event_code: str, mark: str, date: datetime.date, venue: str | None = None,
    points: int | None = None,
) -> None:
    """For PRs a human found by hand (a local record book, a federation
    site, a news article) that neither World Athletics nor Tilastopaja
    surfaced. Stored with source='manual' so it's easy to tell apart later."""
    from nordcross.scoring import points_for
    from nordcross.scrapers.common import parse_time_to_seconds

    session = get_session()
    try:
        athlete = session.get(Athlete, athlete_id)
        if athlete is None:
            raise ValueError(f"No athlete with id={athlete_id}")

        performance_seconds = parse_time_to_seconds(mark)
        if performance_seconds is None:
            raise ValueError(f"Could not parse mark {mark!r} as a time")

        category_row = (
            session.query(Category.code)
            .join(Race, Race.category_id == Category.id)
            .join(Result, Result.race_id == Race.id)
            .filter(Result.athlete_id == athlete_id)
            .first()
        )
        category_code = category_row[0] if category_row else "MEN"

        existing = (
            session.query(AthleteProgression)
            .filter_by(athlete_id=athlete_id, event_code=event_code, date=date, performance_seconds=performance_seconds)
            .one_or_none()
        )
        if existing is None:
            existing = AthleteProgression(
                athlete_id=athlete_id, event_code=event_code, date=date, performance_seconds=performance_seconds,
            )
            session.add(existing)
        existing.performance_display = mark
        existing.venue = venue
        existing.source = "manual"
        existing.source_ref = None
        existing.points = points if points is not None else points_for(event_code, category_code, performance_seconds)
        session.commit()
    finally:
        session.close()
