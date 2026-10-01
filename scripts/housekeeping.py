"""Database housekeeping from the command line.

Usage:
  python scripts/housekeeping.py status
  python scripts/housekeeping.py backup [--dir DIR]          (default: <docs_dir>/backups)
  python scripts/housekeeping.py clean [--days 30] [--yes]   (without --yes it only reports)

``clean`` deletes jobs posted or collected more than DAYS days ago, with their scores. Jobs
you saved, applied to, were rejected for or wrote a document for are always kept.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import housekeeping as hk  # noqa: E402
from db.database import get_engine, init_db, schema_revision  # noqa: E402


def _docs_dir() -> Path:
    try:
        from config import get_settings

        return Path(get_settings().docs_dir).expanduser()
    except Exception:
        return Path("~/jobhunt_docs").expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JobHunt AI database housekeeping")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show the schema version and how many jobs are stale")
    b = sub.add_parser("backup", help="write jobs and matches as CSV plus a copy of the database")
    b.add_argument("--dir", default=None, help="folder for the backup (default: <docs_dir>/backups)")
    c = sub.add_parser("clean", help="delete stale jobs (reports only, unless --yes)")
    c.add_argument("--days", type=int, default=hk.DEFAULT_STALE_DAYS, help="age in days (default 30)")
    c.add_argument("--yes", action="store_true", help="really delete")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = init_db(get_engine())
    if args.command == "status":
        summary = hk.stale_summary()
        print(f"Schema version: {schema_revision(engine)}")
        print(f"Jobs older than {hk.DEFAULT_STALE_DAYS} days: {summary['stale']} would be deleted, "
              f"{summary['kept']} kept because you track them")
    elif args.command == "backup":
        folder = Path(args.dir) if args.dir else _docs_dir() / "backups"
        for path in hk.backup(folder):
            print(f"Wrote {path}")
    else:
        summary = hk.stale_summary(args.days)
        if not args.yes:
            print(f"{summary['stale']} jobs are older than {args.days} days and would be deleted "
                  f"({summary['kept']} kept because you track them). Run again with --yes to delete.")
        else:
            print(f"Deleted {hk.delete_stale_jobs(args.days)} jobs older than {args.days} days.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
