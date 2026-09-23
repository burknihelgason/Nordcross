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


def _token_similarity(a: str, b: str) -> float:
    """Score two space-joined, sorted token strings by best-matching each
    token on the shorter side against the longer side, rather than diffing
    the whole string -- so a name that differs by one token (a middle name
    abbreviated to an initial, e.g. "Kalstrup" -> "K.") doesn't tank the
    score just because the strings are now different lengths. A bare
    initial is treated as compatible with any token sharing its first
    letter; found via a real case: "SCHULTZ Line Kalstrup" vs "Line K.
    SCHULZ" scores 0.74 on whole-string similarity (below threshold) but
    ~0.97 here, correctly surfacing the surname typo (Schultz/Schulz) once
    the initial isn't distorting the comparison.

    Requires at least one strong match between two *non-initial* tokens
    before returning anything -- otherwise a bare initial can spuriously
    "match" an unrelated word starting with the same letter and inflate
    the score for two unrelated people. Found via a real false positive:
    "SÆFELDT Sophie" scored 0.95 against "Sebastian S GRØNKJÆR" purely
    because Sebastian's middle initial "S" happens to be the first letter
    of "Sæfeldt" -- two different people, sharing no actual name part."""
    tokens_a, tokens_b = a.split(), b.split()
    if not tokens_a or not tokens_b:
        return 0.0

    full_a = [t for t in tokens_a if len(t.rstrip(".")) > 1]
    full_b = [t for t in tokens_b if len(t.rstrip(".")) > 1]
    has_strong_link = any(
        t == u or SequenceMatcher(None, t, u).ratio() >= 0.8 for t in full_a for u in full_b
    )
    if not has_strong_link:
        return 0.0

    smaller, larger = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    scores = []
    for t in smaller:
        t_bare = t.rstrip(".")
        best = 0.0
        for u in larger:
            u_bare = u.rstrip(".")
            if t == u:
                best = 1.0
                break
            if (len(t_bare) == 1 and u_bare.startswith(t_bare)) or (len(u_bare) == 1 and t_bare.startswith(u_bare)):
                best = max(best, 0.9)
                continue
            best = max(best, SequenceMatcher(None, t, u).ratio())
        scores.append(best)
    return sum(scores) / len(scores)


_STATUS_RANK = {"done": 2, "ambiguous": 1, "pending": 1, "failed": 0, "not_found": 0}


def _lookup_quality(lu: AthleteLookup) -> tuple[int, int]:
    """Ranks a lookup row so merge_athletes can keep the better of two rows
    for the same source instead of always favoring keep_id's. A resolved
    external_id always beats one without, regardless of status text."""
    return (1 if lu.external_id else 0, _STATUS_RANK.get(lu.status, 0))


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
                    key_a, key_b = compute_name_key(a.full_name), compute_name_key(b.full_name)
                    sim = max(_similarity(key_a, key_b), _token_similarity(key_a, key_b))
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

        # Progression rows collide on (athlete_id, event_code, date,
        # performance_seconds) -- a real case if both duplicate athletes were
        # independently matched to the same external profile, so they'd
        # carry identical progression rows. Drop remove_id's copy in that
        # case rather than reassigning into a constraint violation.
        keep_progression_keys = {
            (p.event_code, p.date, p.performance_seconds)
            for p in session.query(AthleteProgression).filter_by(athlete_id=keep_id).all()
        }
        for p in session.query(AthleteProgression).filter_by(athlete_id=remove_id).all():
            if (p.event_code, p.date, p.performance_seconds) in keep_progression_keys:
                session.delete(p)
            else:
                p.athlete_id = keep_id

        # When both sides have a lookup row for the same source, keep
        # whichever is actually more complete rather than always favoring
        # keep_id's -- found via a real case (Nahom Tesfalem Tewelde): keep_id
        # had only ever tried (and failed) a search under its own truncated
        # name, so its "ambiguous" row would have won over remove_id's
        # genuinely resolved one and silently discarded a real match.
        for source in {lu.source for lu in session.query(AthleteLookup).filter(
            AthleteLookup.athlete_id.in_([keep_id, remove_id])
        ).all()}:
            k_lu = session.query(AthleteLookup).filter_by(athlete_id=keep_id, source=source).one_or_none()
            r_lu = session.query(AthleteLookup).filter_by(athlete_id=remove_id, source=source).one_or_none()
            if k_lu and r_lu:
                if _lookup_quality(r_lu) > _lookup_quality(k_lu):
                    session.delete(k_lu)
                    r_lu.athlete_id = keep_id
                else:
                    session.delete(r_lu)
            elif r_lu:
                r_lu.athlete_id = keep_id

        if keep.birth_year is None and remove.birth_year is not None:
            keep.birth_year = remove.birth_year
        if len(remove.full_name) > len(keep.full_name) and not remove.full_name.isupper():
            keep.full_name = remove.full_name  # prefer the more complete/readable name

        session.delete(remove)
        session.commit()
    finally:
        session.close()
