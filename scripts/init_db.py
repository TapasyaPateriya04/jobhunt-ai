"""Create the JobHunt AI database, or upgrade an existing one to the latest schema.

Usage: python scripts/init_db.py [DATABASE_URL]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.database import get_engine, init_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    engine = init_db(get_engine(argv[0] if argv else None))
    print(f"Database is up to date at {engine.url.render_as_string(hide_password=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
