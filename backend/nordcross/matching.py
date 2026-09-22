from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict

from nordcross.db.models import Athlete, Country, Result
from nordcross.db.session import get_session


def name_key(raw_name: str) -> str:
    """Order-independent, accent-insensitive key used to match the same athlete
    across sources that format names differently (e.g. "SURNAME Given" vs
    "Given Surname")."""
    folded = unicodedata.normalize("NFKD", raw_name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    tokens = sorted(t.casefold() for t in folded.split() if t)
    return " ".join(tokens)


def pick_display_name(names: list[str]) -> str:
    mixed_case = [n for n in names if not n.isupper()]
    candidates = mixed_case or names
    return max(candidates, key=len)


def match_athletes() -> None:
    """Group results into athletes by (country, name_key), upserting Athlete rows
    and linking Result.athlete_id. Idempotent: safe to re-run after new ingests."""
    session = get_session()
    try:
        results = session.query(Result).all()
        valid_country_codes = {c.code for c in session.query(Country).all()}

        groups: dict[tuple[str | None, str], list[Result]] = defaultdict(list)
        for r in results:
            country_code = r.raw_country if r.raw_country in valid_country_codes else None
            groups[(country_code, name_key(r.raw_name))].append(r)

        existing = {(a.country_code, a.name_key): a for a in session.query(Athlete).all()}

        for (country_code, key), rows in groups.items():
            if not key:
                continue

            display_name = pick_display_name([r.raw_name for r in rows])
            birth_years = [r.birth_year for r in rows if r.birth_year is not None]
            birth_year = Counter(birth_years).most_common(1)[0][0] if birth_years else None

            athlete = existing.get((country_code, key))
            if athlete is None:
                athlete = Athlete(
                    full_name=display_name,
                    name_key=key,
                    country_code=country_code,
                    birth_year=birth_year,
                )
                session.add(athlete)
                session.flush()
                existing[(country_code, key)] = athlete
            else:
                athlete.full_name = display_name
                athlete.birth_year = birth_year

            for r in rows:
                r.athlete_id = athlete.id
                r.athlete_match_confidence = (
                    "high" if r.birth_year is None or r.birth_year == birth_year else "low"
                )

        session.commit()
    finally:
        session.close()
