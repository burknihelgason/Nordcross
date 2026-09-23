"""Finds and merges athlete identities that step 2a's exact name-key match
missed -- same person, but rendered differently across sources (a hyphenated
vs spaced compound surname, a one-letter spelling variant, a dropped middle
name). Exact matching can't catch these; this uses fuzzy string similarity
scoped to (country, birth_year) to keep false-positive risk low.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from nordcross.db.models import Athlete, AthleteLookup, AthleteProgression, Result
from nordcross.db.session import get_session
from nordcross.matching import name_key as compute_name_key

STRICT_THRESHOLD = 0.80  # same country + same known birth_year
LOOSE_THRESHOLD = 0.92  # same country, birth_year missing on one/both sides -- higher bar


@dataclass
class DuplicateCandidate:
    athlete_a: Athlete
    athlete_b: Athlete
    similarity: float
    confidence: str  # 'high' (birth years matched) | 'review' (birth year missing)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _race_ids(session, athlete_id: int) -> set[int]:
    return {r.race_id for r in session.query(Result.race_id).filter_by(athlete_id=athlete_id).all()}


def find_potential_duplicates() -> list[DuplicateCandidate]:
    session = get_session()
    try:
        athletes = session.query(Athlete).all()
        by_country: dict[str | None, list[Athlete]] = {}
        for a in athletes:
            by_country.setdefault(a.country_code, []).append(a)

        candidates: list[DuplicateCandidate] = []
        for country, group in by_country.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    # Recompute from full_name rather than trusting the
                    # stored name_key column, which may predate a
                    # normalization fix (e.g. hyphen handling) and not
                    # reflect it until the athlete is next re-matched.
                    sim = _similarity(compute_name_key(a.full_name), compute_name_key(b.full_name))
                    threshold = STRICT_THRESHOLD if (a.birth_year and b.birth_year) else LOOSE_THRESHOLD
                    if sim < threshold:
                        continue
                    if a.birth_year and b.birth_year and a.birth_year != b.birth_year:
                        continue
                    # Two different placings in the same race can't be the
                    # same person -- a real case this caught: "Maren Halle
                    # Haugen" and "Ina Halle Haugen" both raced in 2019 and
                    # 2022 U20 Women (likely sisters), which plain name
                    # similarity alone couldn't tell apart from a typo.
                    if _race_ids(session, a.id) & _race_ids(session, b.id):
                        continue
                    confidence = "high" if (a.birth_year and b.birth_year) else "review"
                    candidates.append(DuplicateCandidate(a, b, sim, confidence))
        candidates.sort(key=lambda c: -c.similarity)
        return candidates
    finally:
        session.close()


def merge_athletes(keep_id: int, remove_id: int) -> None:
    """Reassigns everything pointing at `remove_id` onto `keep_id`, then
    deletes the now-empty duplicate. Safe to call even if both have rows in
    tables with a (athlete_id, source)-style unique constraint (AthleteLookup)
    -- the duplicate's row is dropped in favor of keep_id's if both exist."""
    if keep_id == remove_id:
        raise ValueError("keep_id and remove_id must differ")
    session = get_session()
    try:
        keep = session.get(Athlete, keep_id)
        remove = session.get(Athlete, remove_id)
        if keep is None or remove is None:
            raise ValueError(f"Athlete {keep_id if keep is None else remove_id} not found")

        session.query(Result).filter_by(athlete_id=remove_id).update({"athlete_id": keep_id})
        session.query(AthleteProgression).filter_by(athlete_id=remove_id).update({"athlete_id": keep_id})

        keep_sources = {
            lu.source for lu in session.query(AthleteLookup).filter_by(athlete_id=keep_id).all()
        }
        for lu in session.query(AthleteLookup).filter_by(athlete_id=remove_id).all():
            if lu.source in keep_sources:
                session.delete(lu)  # keep_id's own row for this source wins
            else:
                lu.athlete_id = keep_id

        if keep.birth_year is None and remove.birth_year is not None:
            keep.birth_year = remove.birth_year
        if len(remove.full_name) > len(keep.full_name) and not remove.full_name.isupper():
            keep.full_name = remove.full_name  # prefer the more complete/readable name

        session.delete(remove)
        session.commit()
    finally:
        session.close()
