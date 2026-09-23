"""Slow-drip runner that works through the AthleteLookup queue.

Both external sources (World Athletics, Tilastopaja) have shown they block
or rate-limit after only a handful of requests. This runner is built around
that reality: small batches, generous randomized delays between every
network request (not just between athletes), a persistent browser profile
per source (so repeated invocations look like the same returning visitor),
and an immediate stop -- not a retry -- the moment a source looks blocked.
Progress is committed per-athlete, so a run that stops early loses nothing.

Usage is meant to be "run this a few times a day until the queue drains",
not "run this once and walk away".
"""

from __future__ import annotations

import datetime

from nordcross.db.models import Athlete, AthleteLookup, AthleteProgression, Category, Race, Result
from nordcross.db.session import get_session
from nordcross.external import tilastopaja, worldathletics
from nordcross.external.common import BlockedError, polite_delay
from nordcross.matching import name_key
from nordcross.scoring import normalize_event_label, points_for

MALE_CATEGORIES = {"MEN", "U20_MEN"}


def _athlete_category_code(session, athlete_id: int) -> str | None:
    row = (
        session.query(Category.code)
        .join(Race, Race.category_id == Category.id)
        .join(Result, Result.race_id == Race.id)
        .filter(Result.athlete_id == athlete_id)
        .first()
    )
    return row[0] if row else None


def _store_progression(session, athlete: Athlete, category_code: str, event_code: str,
                        performance_seconds: float, performance_display: str,
                        date: datetime.date, venue: str | None, source: str, source_ref: str | None,
                        points: int | None = None) -> None:
    existing = (
        session.query(AthleteProgression)
        .filter_by(athlete_id=athlete.id, event_code=event_code, date=date, performance_seconds=performance_seconds)
        .one_or_none()
    )
    if existing is None:
        existing = AthleteProgression(
            athlete_id=athlete.id, event_code=event_code, date=date, performance_seconds=performance_seconds,
        )
        session.add(existing)
    existing.performance_display = performance_display
    existing.venue = venue
    existing.source = source
    existing.source_ref = source_ref
    # Prefer the source's own officially-computed score (e.g. World
    # Athletics' "Score" column) over our own scoring-table interpolation,
    # falling back to our own calculation only when the source doesn't
    # provide one.
    existing.points = points if points is not None else points_for(event_code, category_code, performance_seconds)


def run_tilastopaja(limit: int = 5, headless: bool = True, user_data_dir: str = ".pw-profiles/tilastopaja") -> None:
    session = get_session()
    try:
        pending = (
            session.query(AthleteLookup)
            .filter_by(source="tilastopaja", status="pending")
            .order_by(AthleteLookup.id)
            .limit(limit)
            .all()
        )
        if not pending:
            print("No pending Tilastopaja lookups.")
            return

        pw, context, page = tilastopaja.open_session(user_data_dir, headless=headless)
        try:
            for lookup in pending:
                athlete = session.get(Athlete, lookup.athlete_id)
                category_code = _athlete_category_code(session, athlete.id) or "MEN"
                print(f"Looking up (tilastopaja): {athlete.full_name} ({athlete.birth_year})")

                polite_delay()
                candidates = tilastopaja.search_athlete(page, athlete.full_name)
                match = _pick_best_match(candidates, athlete, id_field="athleteId", dob_field="dateOfBirth")
                if match is None:
                    lookup.status = "not_found" if not candidates else "ambiguous"
                    lookup.note = f"{len(candidates)} candidate(s), none matched confidently"
                else:
                    external_id, confidence = match
                    polite_delay()
                    records = tilastopaja.fetch_progression(page, external_id, category_code)
                    for rec in records:
                        _store_tilastopaja_record(session, athlete, category_code, rec)
                    lookup.status = "done"
                    lookup.external_id = external_id
                    lookup.match_confidence = confidence
                    lookup.note = f"{len(records)} progression record(s)"

                lookup.attempts += 1
                lookup.last_attempt_at = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
        except BlockedError as e:
            print(f"STOPPING: {e}")
        finally:
            tilastopaja.close_session(pw, context)
    finally:
        session.close()


def run_worldathletics(limit: int = 5, headless: bool = True, user_data_dir: str = ".pw-profiles/worldathletics") -> None:
    session = get_session()
    try:
        pending = (
            session.query(AthleteLookup)
            .filter_by(source="worldathletics", status="pending")
            .order_by(AthleteLookup.id)
            .limit(limit)
            .all()
        )
        if not pending:
            print("No pending World Athletics lookups.")
            return

        pw, context, page = worldathletics.open_session(user_data_dir, headless=headless)
        try:
            for lookup in pending:
                athlete = session.get(Athlete, lookup.athlete_id)
                category_code = _athlete_category_code(session, athlete.id) or "MEN"
                expected_sex = "Men" if category_code in MALE_CATEGORIES else "Women"
                print(f"Looking up (worldathletics): {athlete.full_name} ({athlete.birth_year})")

                polite_delay()
                candidates = worldathletics.search_athlete(page, athlete.full_name)
                candidates = [c for c in candidates if c["sex"].lower().startswith(expected_sex[0].lower())]
                match = _pick_best_match(candidates, athlete, id_field="profile_url", dob_field="dob")
                if match is None:
                    lookup.status = "not_found" if not candidates else "ambiguous"
                    lookup.note = f"{len(candidates)} candidate(s), none matched confidently"
                else:
                    profile_url, confidence = match
                    polite_delay()
                    records = worldathletics.fetch_progression(page, profile_url)
                    for rec in records:
                        _store_worldathletics_record(session, athlete, category_code, rec)
                    athlete.world_athletics_id = worldathletics.profile_id_from_url(profile_url)
                    lookup.status = "done"
                    lookup.external_id = athlete.world_athletics_id
                    lookup.match_confidence = confidence
                    lookup.note = f"{len(records)} progression record(s)"

                lookup.attempts += 1
                lookup.last_attempt_at = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
        except BlockedError as e:
            print(f"STOPPING: {e}")
        finally:
            worldathletics.close_session(pw, context)
    finally:
        session.close()


def _pick_best_match(candidates: list[dict], athlete: Athlete, id_field: str, dob_field: str) -> tuple[str, str] | None:
    """Best-guess match on name + birth year, per the project's agreed
    "best-guess automatically, flag low-confidence" policy. Returns
    (external_id, confidence) or None if nothing is even name-plausible."""
    target_key = name_key(athlete.full_name)
    name_matches = [c for c in candidates if name_key(c.get("name", "")) == target_key]
    if not name_matches:
        return None

    if athlete.birth_year:
        year_matches = [c for c in name_matches if str(athlete.birth_year) in (c.get(dob_field) or "")]
        if len(year_matches) == 1:
            return year_matches[0][id_field], "high"

    if len(name_matches) == 1:
        return name_matches[0][id_field], "high" if not athlete.birth_year else "low"

    return name_matches[0][id_field], "low"


def _store_tilastopaja_record(session, athlete: Athlete, category_code: str, rec: dict) -> None:
    event_code = normalize_event_label(rec.get("event") or rec.get("discipline") or "")
    if event_code is None:
        return
    performance_seconds = _parse_mark_seconds(rec.get("mark") or rec.get("result") or rec.get("performance"))
    date = _parse_date(rec.get("date") or rec.get("compDate") or rec.get("resultDate"))
    if performance_seconds is None or date is None:
        return
    _store_progression(
        session, athlete, category_code, event_code, performance_seconds,
        str(rec.get("mark") or rec.get("result") or rec.get("performance")),
        date, rec.get("venue"), source="tilastopaja", source_ref=None,
    )


def _store_worldathletics_record(session, athlete: Athlete, category_code: str, rec: dict) -> None:
    event_code = normalize_event_label(rec.get("event") or "")
    if event_code is None:
        return
    performance_seconds = _parse_mark_seconds(rec.get("mark"))
    date = _parse_date(rec.get("date"))
    if performance_seconds is None or date is None:
        return
    _store_progression(
        session, athlete, category_code, event_code, performance_seconds, rec.get("mark"),
        date, rec.get("venue"), source="worldathletics", source_ref=None,
        points=rec.get("wa_score"),
    )


def _parse_mark_seconds(mark: str | None) -> float | None:
    if not mark:
        return None
    from nordcross.scrapers.common import parse_time_to_seconds
    return parse_time_to_seconds(mark.strip())


def _parse_date(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    for fmt in ("%d %b %Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None
