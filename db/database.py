"""SQLAlchemy 2.0 models and engine/session helpers (SPEC §6 ERD).

SQLite by default; everything here is portable to PostgreSQL (SPEC §11).
Timestamps are stored as *naive UTC* datetimes (see :func:`utcnow`).
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from sqlalchemy import (
    DateTime,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///jobhunt.db"


def utcnow() -> datetime:
    """Current time as naive UTC (consistent storage format for all timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)
    skills_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list[str]
    experience_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON list[dict]
    education: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    matches: Mapped[list["Match"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", passive_deletes=True
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(Text)
    company: Mapped[Optional[str]] = mapped_column(Text)
    location: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(64))
    url: Mapped[Optional[str]] = mapped_column(Text)
    posted_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    experience_years: Mapped[Optional[int]] = mapped_column(Integer)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    matches: Mapped[list["Match"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_jobs_scraped_at", "scraped_at"),)


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    ats_score: Mapped[Optional[float]] = mapped_column(Float)
    experience_score: Mapped[Optional[float]] = mapped_column(Float)
    semantic_score: Mapped[Optional[float]] = mapped_column(Float)
    freshness_score: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    resume: Mapped[Resume] = relationship(back_populates="matches")
    job: Mapped[Job] = relationship(back_populates="matches")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="match", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("resume_id", "job_id", name="uq_matches_resume_job"),
        Index("ix_matches_resume_id", "resume_id"),
        Index("ix_matches_confidence_score", "confidence_score"),
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    file_path: Mapped[Optional[str]] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    match: Mapped[Match] = relationship(back_populates="documents")


# --------------------------------------------------------------------------- engine

@event.listens_for(Engine, "connect")
def _sqlite_fk_pragma(dbapi_connection, connection_record) -> None:  # pragma: no cover - trivial
    """Enable FK enforcement (needed for ON DELETE CASCADE) on every SQLite connection."""
    try:
        import sqlite3
    except ImportError:
        return
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


_engines: dict[str, Engine] = {}
_sessionmakers: dict[int, sessionmaker] = {}
_lock = threading.Lock()


def resolve_database_url() -> str:
    """Database URL from config.get_settings(), falling back to $DATABASE_URL / default."""
    try:
        from config import get_settings  # lazy: config is owned by another module

        url = getattr(get_settings(), "database_url", None)
        if url:
            return str(url)
    except Exception:
        pass
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine(url: Optional[str] = None) -> Engine:
    """Return a cached Engine for ``url`` (default: configured database URL)."""
    url = url or resolve_database_url()
    with _lock:
        engine = _engines.get(url)
        if engine is None:
            kwargs: dict = {"future": True}
            if url.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False}
            else:
                kwargs["pool_pre_ping"] = True
            engine = create_engine(url, **kwargs)
            _engines[url] = engine
        return engine


def init_db(engine: Optional[Engine] = None) -> Engine:
    """Create all tables (idempotent). Returns the engine used."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)
    return engine


def _sessionmaker_for(engine: Engine) -> sessionmaker:
    with _lock:
        sm = _sessionmakers.get(id(engine))
        if sm is None or sm.kw.get("bind") is not engine:
            sm = sessionmaker(bind=engine, expire_on_commit=False, future=True)
            _sessionmakers[id(engine)] = sm
        return sm


_initialized: set[int] = set()


@contextmanager
def get_session(engine: Optional[Engine] = None) -> Iterator[Session]:
    """Transactional session scope: commits on success, rolls back on error.

    Tables are created on first use of an engine so callers never hit
    "no such table" on a fresh database.
    """
    engine = engine or get_engine()
    if id(engine) not in _initialized:
        init_db(engine)
        _initialized.add(id(engine))
    session = _sessionmaker_for(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engines() -> None:
    """Dispose and forget all cached engines (useful in tests)."""
    with _lock:
        for eng in _engines.values():
            eng.dispose()
        _engines.clear()
        _sessionmakers.clear()
        _initialized.clear()


__all__ = [
    "Base",
    "Resume",
    "Job",
    "Match",
    "Document",
    "utcnow",
    "get_engine",
    "init_db",
    "get_session",
    "resolve_database_url",
    "dispose_engines",
    "DEFAULT_DATABASE_URL",
]
