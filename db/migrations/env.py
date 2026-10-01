"""Alembic environment for JobHunt AI.

The app runs migrations itself (``db.database.init_db``) and hands over its own connection
through ``config.attributes["connection"]``. From the command line (``alembic upgrade head``,
``alembic revision --autogenerate -m "..."``) the URL comes from DATABASE_URL / .env as usual.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import Base, resolve_database_url  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or resolve_database_url()


def _configure(**kwargs) -> None:
    # Batch mode lets ALTER TABLE work on SQLite, which cannot drop or change columns in place.
    context.configure(target_metadata=target_metadata, render_as_batch=True, compare_type=True, **kwargs)


def run_migrations_offline() -> None:
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(_url())
    try:
        with engine.begin() as conn:
            _configure(connection=conn)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
