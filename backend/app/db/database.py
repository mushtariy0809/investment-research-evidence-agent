"""Database engine and session management.

The engine URL comes from DATABASE_URL, so switching SQLite -> PostgreSQL is a
config change, not a code change. We deliberately avoid SQLite-only features
(no JSON1 extension queries, no SQLite-specific column types) to keep that
migration path real.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {}
    if url.startswith("sqlite"):
        # SQLite: allow use across FastAPI's threadpool, and make sure the
        # parent directory exists (e.g. ./data/app.db).
        connect_args = {"check_same_thread": False}
        db_path = url.removeprefix("sqlite:///")
        if db_path and not db_path.startswith(":memory:"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    # For the MVP we create tables directly; in production this would be
    # replaced by Alembic migrations.
    from app.db import models  # noqa: F401  (register models with Base)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
