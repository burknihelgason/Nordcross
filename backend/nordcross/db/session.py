from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from nordcross.config import sqlalchemy_url

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(sqlalchemy_url(), fast_executemany=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()
