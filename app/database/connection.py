"""PostgreSQL/SQLAlchemy connection boundary."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Normalize common Render/Postgres URLs to the psycopg SQLAlchemy dialect."""
    url = database_url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def build_engine(database_url: str | None) -> Engine | None:
    """Build an engine without connecting to the database during import/startup."""
    if not database_url:
        return None
    normalized = normalize_database_url(database_url)
    kwargs = {"pool_pre_ping": True}
    if not normalized.startswith("sqlite://"):
        kwargs.update({"pool_size": 5, "max_overflow": 0})
    return create_engine(normalized, **kwargs)


def build_session_factory(engine: Engine | None):
    """Create a SQLAlchemy session factory when an engine is available."""
    if engine is None:
        return None
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
