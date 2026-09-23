from __future__ import annotations

import csv
import datetime

from nordcross.db.models import Athlete, AthleteLookup, Category, Race, Result
from nordcross.db.session import get_session

# Which external source(s) cover which country. World Athletics is tried for
# everyone (Icelandic athletes competing internationally often have a WA
# profile too); Iceland additionally gets Tilastopaja/afrekaskra, which has
# essentially every Icelandic athlete of any note, not just internationally
# active ones -- useful as a second pass once/if that source stops blocking us.
SOURCES_BY_COUNTRY = {
    "ISL": ["worldathletics", "tilastopaja"],
    "NOR": ["worldathletics"],
    "SWE": ["worldathletics"],
    "DEN": ["worldathletics"],
    "FIN": ["worldathletics"],
}


def seed_lookup_queue() -> int:
    """Create a 'pending' AthleteLookup row for every athlete/source pair that
    doesn't have one yet. Idempotent — safe to re-run after new athletes are
    matched or the source list changes. Returns the number of rows created."""
    session = get_session()
    try:
        existing = {(l.athlete_id, l.source) for l in session.query(AthleteLookup).all()}
        created = 0
        for athlete in session.query(Athlete).all():
            for source in SOURCES_BY_COUNTRY.get(athlete.country_code, []):
                if (athlete.id, source) in existing:
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


def export_for_review(source: str, out_path: str, statuses: tuple[str, ...] = ("ambiguous", "not_found")) -> int:
    """Writes a CSV of lookups needing a human look: name, birth year,
    country, category, current status, and a ready-to-click search URL.
    After manually finding the right profile, use `lookup-resolve` to feed
    the URL/id back in. Returns the number of rows written."""
    session = get_session()
    try:
        rows = (
            session.query(AthleteLookup, Athlete)
            .join(Athlete, Athlete.id == AthleteLookup.athlete_id)
            .filter(AthleteLookup.source == source, AthleteLookup.status.in_(statuses))
            .order_by(Athlete.full_name)
            .all()
        )
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["athlete_id", "full_name", "birth_year", "country_code", "category", "status", "note", "search_url"])
            for lookup, athlete in rows:
                category_row = (
                    session.query(Category.code)
                    .join(Race, Race.category_id == Category.id)
                    .join(Result, Result.race_id == Race.id)
                    .filter(Result.athlete_id == athlete.id)
                    .first()
                )
                category_code = category_row[0] if category_row else ""
                if source == "worldathletics":
                    search_url = f"https://worldathletics.org/athletes?query={athlete.full_name.replace(' ', '+')}"
                else:
                    search_url = f"https://afrekaskra.fri.is/isl/athletes/search?query={athlete.full_name.replace(' ', '+')}"
                writer.writerow([
                    athlete.id, athlete.full_name, athlete.birth_year or "", athlete.country_code or "",
                    category_code, lookup.status, lookup.note or "", search_url,
                ])
        return len(rows)
    finally:
        session.close()


def resolve_manually(athlete_id: int, source: str, url_or_id: str) -> None:
    """Records a human-confirmed profile for one athlete/source and puts the
    lookup back in the queue so the next `lookup-run` fetches its progression
    directly (no re-search) instead of relying on automated matching."""
    session = get_session()
    try:
        lookup = (
            session.query(AthleteLookup)
            .filter_by(athlete_id=athlete_id, source=source)
            .one_or_none()
        )
        if lookup is None:
            lookup = AthleteLookup(athlete_id=athlete_id, source=source)
            session.add(lookup)
        lookup.manual_url = url_or_id
        lookup.status = "pending"
        lookup.note = "manually resolved, awaiting fetch"
        session.commit()
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
