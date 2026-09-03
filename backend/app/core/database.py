"""SQLAlchemy engine / session. Works with SQLite (dev default) and any
PostgreSQL-compatible URL (production)."""
from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
_engine_kwargs: dict = {"pool_pre_ping": True}
if not settings.is_sqlite:
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
