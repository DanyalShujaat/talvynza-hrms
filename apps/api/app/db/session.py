"""Engine / session factory. PostgreSQL in production; SQLite supported for local dev and tests."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        eng = create_engine(url, **kwargs)

        @event.listens_for(eng, "connect")
        def _fk_pragma(dbapi_conn, _):  # enforce referential integrity on SQLite like PostgreSQL does
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
