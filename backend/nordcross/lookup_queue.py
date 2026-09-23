from __future__ import annotations

import datetime

from nordcross.db.models import Athlete, AthleteLookup
from nordcross.db.session import get_session

# Which external source covers which country. Iceland is small enough that
# essentially every athlete of any note has a Tilastopaja/afrekaskra record;
# for the other four countries World Athletics is the only realistic source.
SOURCE_BY_COUNTRY = {
    "ISL": "tilastopaja",
    "NOR": "worldathletics",
    "SWE": "worldathletics",
    "DEN": "worldathletics",
    "FIN": "worldathletics",
}


def seed_lookup_queue() -> int:
    """Create a 'pending' AthleteLookup row for every athlete/source pair that
    doesn't have one yet. Idempotent — safe to re-run after new athletes are
    matched. Returns the number of rows created."""
    session = get_session()
    try:
        existing = {(l.athlete_id, l.source) for l in session.query(AthleteLookup).all()}
        created = 0
        for athlete in session.query(Athlete).all():
            source = SOURCE_BY_COUNTRY.get(athlete.country_code)
            if source is None or (athlete.id, source) in existing:
                continue
            session.add(AthleteLookup(athlete_id=athlete.id, source=source, status="pending"))
            created += 1
        session.commit()
        return created
    finally:
        session.close()


def get_pending(source: str, limit: int) -> list[AthleteLookup]:
    session = get_session()
    try:
        return (
            session.query(AthleteLookup)
            .filter_by(source=source, status="pending")
            .order_by(AthleteLookup.id)
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def queue_summary() -> dict[tuple[str, str], int]:
    session = get_session()
    try:
        counts: dict[tuple[str, str], int] = {}
        for row in session.query(AthleteLookup).all():
            key = (row.source, row.status)
            counts[key] = counts.get(key, 0) + 1
        return counts
    finally:
        session.close()


def mark_result(
    lookup_id: int,
    status: str,
    external_id: str | None = None,
    match_confidence: str | None = None,
    note: str | None = None,
) -> None:
    session = get_session()
    try:
        lookup = session.get(AthleteLookup, lookup_id)
        lookup.status = status
        lookup.external_id = external_id
        lookup.match_confidence = match_confidence
        lookup.note = note
        lookup.attempts += 1
        lookup.last_attempt_at = datetime.datetime.now(datetime.timezone.utc)
        session.commit()
    finally:
        session.close()
