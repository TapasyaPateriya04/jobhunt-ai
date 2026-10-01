"""Database housekeeping: clear out stale jobs and back up jobs and matches.

Stale jobs are removed with their scores, except jobs you are tracking (saved, applied,
rejected) or wrote a document for. Backups are CSV files, plus a copy of the SQLite file.
Plain dicts and strings in and out, like ``db.repository``.
"""
from __future__ import annotations

import csv
import io
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from db.database import Document, Job, Match, Resume, get_engine, get_session, utcnow
from db.repository import _scope

TRACKED_STATUSES = ("saved", "applied", "rejected")
DEFAULT_STALE_DAYS = 30
MIN_STALE_DAYS = 1

JOB_COLUMNS = ("id", "title", "company", "location", "source", "url", "posted_date", "experience_years",
               "scraped_at", "description")
MATCH_COLUMNS = ("match_id", "resume", "title", "company", "location", "source", "url", "posted_date", "status",
                 "confidence_score", "ats_score", "experience_score", "semantic_score", "freshness_score",
                 "calculated_at")


# --------------------------------------------------------------------------- stale jobs

def _stale_filter(days: int, now: Optional[datetime]):
    """Jobs posted (or, with no posting date, collected) more than ``days`` days ago."""
    cutoff = (now or utcnow()) - timedelta(days=max(MIN_STALE_DAYS, int(days)))
    return func.coalesce(Job.posted_date, Job.scraped_at) < cutoff


def _kept_filter():
    """Jobs worth keeping whatever their age: tracked by you, or with a document written."""
    tracked = exists().where(and_(Match.job_id == Job.id, Match.status.in_(TRACKED_STATUSES)))
    documented = exists().where(and_(Match.job_id == Job.id, Document.match_id == Match.id))
    return tracked | documented


def stale_summary(days: int = DEFAULT_STALE_DAYS, *, now: Optional[datetime] = None,
                  session: Optional[Session] = None) -> dict:
    """``{"stale": jobs that would be deleted, "kept": old jobs kept because you track them}``."""
    old = _stale_filter(days, now)
    with _scope(session) as s:
        stale = s.scalar(select(func.count()).select_from(Job).where(old, ~_kept_filter())) or 0
        kept = s.scalar(select(func.count()).select_from(Job).where(old, _kept_filter())) or 0
    return {"stale": int(stale), "kept": int(kept)}


def delete_stale_jobs(days: int = DEFAULT_STALE_DAYS, *, now: Optional[datetime] = None,
                      session: Optional[Session] = None) -> int:
    """Delete stale jobs and their matches; returns how many jobs were deleted."""
    with _scope(session) as s:
        ids = list(s.scalars(select(Job.id).where(_stale_filter(days, now), ~_kept_filter())))
        for start in range(0, len(ids), 500):  # stay under SQLite's bound-parameter limit
            chunk = ids[start:start + 500]
            # Matches go first so this works even where foreign-key cascades are off.
            s.execute(delete(Match).where(Match.job_id.in_(chunk)))
            s.execute(delete(Job).where(Job.id.in_(chunk)))
        return len(ids)


# --------------------------------------------------------------------------- CSV export

def _cell(value) -> object:
    """CSV-safe value. Text that a spreadsheet would run as a formula gets a leading quote."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv(columns: Iterable[str], rows: Iterable[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in columns])
    return out.getvalue()


def jobs_csv(*, session: Optional[Session] = None) -> str:
    """Every stored job, newest first."""
    with _scope(session) as s:
        jobs = s.scalars(select(Job).order_by(Job.scraped_at.desc(), Job.id.desc()))
        rows = [{col: getattr(j, col) for col in JOB_COLUMNS} for j in jobs]
    return _csv(JOB_COLUMNS, rows)


def matches_csv(resume_id: Optional[int] = None, *, session: Optional[Session] = None) -> str:
    """Scores and statuses (for one resume, or all), best match first."""
    stmt = (select(Match, Job, Resume.file_path).join(Job, Match.job_id == Job.id)
            .join(Resume, Match.resume_id == Resume.id)
            .order_by(Match.resume_id, Match.confidence_score.desc().nulls_last(), Match.id))
    if resume_id is not None:
        stmt = stmt.where(Match.resume_id == int(resume_id))
    rows = []
    with _scope(session) as s:
        for m, j, resume_path in s.execute(stmt):
            rows.append({
                "match_id": m.id, "resume": Path(str(resume_path or "")).name,
                "title": j.title, "company": j.company, "location": j.location, "source": j.source,
                "url": j.url, "posted_date": j.posted_date, "status": m.status,
                "confidence_score": m.confidence_score, "ats_score": m.ats_score,
                "experience_score": m.experience_score, "semantic_score": m.semantic_score,
                "freshness_score": m.freshness_score, "calculated_at": m.calculated_at,
            })
    return _csv(MATCH_COLUMNS, rows)


def backup(directory: str | Path, *, database_url: Optional[str] = None) -> list[Path]:
    """Write jobs and matches as CSV, plus a copy of the SQLite file, into ``directory``.

    Returns the files written. Each backup gets its own timestamp, so nothing is overwritten.
    """
    folder = Path(directory).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    written = []
    engine = get_engine(database_url)
    with get_session(engine) as s:
        tables = (("jobs", jobs_csv(session=s)), ("matches", matches_csv(session=s)))
    for name, text in tables:
        path = folder / f"jobhunt-{name}-{stamp}.csv"
        path.write_text(text, encoding="utf-8", newline="")
        written.append(path)
    url = make_url(str(engine.url))
    if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
        path = folder / f"jobhunt-{stamp}.db"
        source = sqlite3.connect(url.database)
        try:
            target = sqlite3.connect(path)
            try:
                source.backup(target)  # consistent copy even while the app has the file open
            finally:
                target.close()
        finally:
            source.close()
        written.append(path)
    return written


__all__ = ["stale_summary", "delete_stale_jobs", "jobs_csv", "matches_csv", "backup",
           "TRACKED_STATUSES", "DEFAULT_STALE_DAYS"]
