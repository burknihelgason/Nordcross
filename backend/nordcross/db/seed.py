from nordcross.db.models import Category, Country
from nordcross.db.session import get_session

COUNTRIES = [
    ("NOR", "Norway"),
    ("SWE", "Sweden"),
    ("DEN", "Denmark"),
    ("FIN", "Finland"),
    ("ISL", "Iceland"),
]

CATEGORIES = [
    ("MEN", "Men"),
    ("WOMEN", "Women"),
    ("U20_MEN", "U20 Men"),
    ("U20_WOMEN", "U20 Women"),
]


def seed_reference_data() -> None:
    session = get_session()
    try:
        for code, name in COUNTRIES:
            if not session.get(Country, code):
                session.add(Country(code=code, name=name))
        existing_categories = {c.code for c in session.query(Category).all()}
        for code, name in CATEGORIES:
            if code not in existing_categories:
                session.add(Category(code=code, name=name))
        session.commit()
    finally:
        session.close()
