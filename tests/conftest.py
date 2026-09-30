"""Shared pytest fixtures.

- ``db_engine``: fresh in-memory SQLite engine (StaticPool) with all tables created.
- ``db_session``: a Session bound to ``db_engine``; pass it as ``session=`` to
  db.repository functions. Rolled back and closed after the test.
- ``tmp_db_url``: points DATABASE_URL at a temp SQLite file for code paths that use
  the default engine (``get_session()`` with no args); returns the URL.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _clear_settings_cache() -> None:
    try:
        import config  # type: ignore
    except Exception:
        return
    clear = getattr(getattr(config, "get_settings", None), "cache_clear", None)
    if callable(clear):
        clear()


@pytest.fixture(autouse=True)
def no_home_country(monkeypatch):
    """Scores must not depend on the CANDIDATE_COUNTRY in a developer's own .env."""
    monkeypatch.setenv("CANDIDATE_COUNTRY", "")
    monkeypatch.setenv("CANDIDATE_CITIES", "")


@pytest.fixture
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from db.database import init_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_engine):
    from sqlalchemy.orm import Session

    session = Session(bind=db_engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def tmp_db_url(tmp_path, monkeypatch):
    from db.database import dispose_engines

    url = f"sqlite:///{(tmp_path / 'jobhunt_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    _clear_settings_cache()
    dispose_engines()
    try:
        yield url
    finally:
        dispose_engines()
        monkeypatch.delenv("DATABASE_URL", raising=False)
        _clear_settings_cache()
