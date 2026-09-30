"""Repository layer: plain-dict CRUD over the models in db.database.

Every public function takes an optional ``session=`` kwarg. When given, the
caller owns the transaction (we only ``flush``); otherwise a fresh
``get_session()`` scope is opened and committed. No ORM objects leak out.
Only portable SQLAlchemy constructs are used (SQLite and PostgreSQL).
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Any, Iterable, Iterator, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.database import Document, Job, Match, Resume, get_session, utcnow

MAX_LIMIT = 1000
MAX_STATUS_LEN = 32
MAX_DOC_TYPE_LEN = 32
MAX_SOURCE_LEN = 64


# --------------------------------------------------------------------------- helpers

@contextmanager
def _scope(session: Optional[Session]) -> Iterator[Session]:
    if session is not None:
        yield session
        session.flush()
    else:
        with get_session() as s:
            yield s


def _clamp_limit(limit: Any, default: int = 50) -> int:
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, MAX_LIMIT))


def _str_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _to_naive_utc(v: Any) -> Optional[datetime]:
    """Coerce datetime/date/ISO string/epoch to naive UTC datetime; else None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, date):
        dt = datetime(v.year, v.month, v.day)
    elif isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            dt = datetime.fromtimestamp(float(v), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(v, str):
        s = v.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _to_int_or_none(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_float_or_none(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _loads_list(s: Optional[str]) -> list:
    if not s:
        return []
    try:
        val = json.loads(s)
    except (TypeError, ValueError):
        return []
    return val if isinstance(val, list) else []


def compute_dedupe_hash(job: dict) -> str:
    """sha256 of the url if present, else of lower('title|company|location')."""
    url = _str_or_none(job.get("url"))
    if url:
        key = "url:" + url
    else:
        parts = [(_str_or_none(job.get(k)) or "").lower() for k in ("title", "company", "location")]
        key = "tcl:" + "|".join(parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _resume_to_dict(r: Resume) -> dict:
    return {
        "id": r.id,
        "file_path": r.file_path,
        "raw_text": r.raw_text or "",
        "skills": _loads_list(r.skills_json),
        "experience": _loads_list(r.experience_json),
        "education": r.education or "",
        "summary": r.summary or "",
        "created_at": r.created_at,
    }


def _job_to_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "description": j.description,
        "source": j.source,
        "url": j.url,
        "posted_date": j.posted_date,
        "experience_years": j.experience_years,
        "scraped_at": j.scraped_at,
        "dedupe_hash": j.dedupe_hash,
    }


def _match_to_dict(m: Match) -> dict:
    return {
        "id": m.id,
        "match_id": m.id,
        "resume_id": m.resume_id,
        "job_id": m.job_id,
        "confidence_score": m.confidence_score,
        "ats_score": m.ats_score,
        "experience_score": m.experience_score,
        "semantic_score": m.semantic_score,
        "freshness_score": m.freshness_score,
        "status": m.status,
        "calculated_at": m.calculated_at,
    }


def _document_to_dict(d: Document) -> dict:
    return {
        "id": d.id,
        "match_id": d.match_id,
        "doc_type": d.doc_type,
        "content": d.content,
        "file_path": d.file_path,
        "generated_at": d.generated_at,
    }


# --------------------------------------------------------------------------- resumes

def save_resume(parsed: dict, file_path: str, *, session: Optional[Session] = None) -> int:
    """Persist a parsed resume dict; returns its resume id.

    Saving a resume whose text is already stored refreshes that row (newer parse, path and
    timestamp) and returns its id, so re-running the pipeline does not pile up copies.
    """
    parsed = parsed or {}
    skills = parsed.get("skills") or []
    experience = parsed.get("experience") or []
    raw_text = parsed.get("raw_text") or ""
    with _scope(session) as s:
        r = None
        if raw_text.strip():
            r = s.scalars(select(Resume).where(Resume.raw_text == raw_text)
                          .order_by(Resume.id).limit(1)).first()
        if r is None:
            r = Resume(raw_text=raw_text)
            s.add(r)
        r.file_path = _str_or_none(file_path)
        r.skills_json = json.dumps(list(skills), ensure_ascii=False, default=str)
        r.experience_json = json.dumps(list(experience), ensure_ascii=False, default=str)
        r.education = _str_or_none(parsed.get("education"))
        r.summary = _str_or_none(parsed.get("summary"))
        r.created_at = utcnow()
        s.flush()
        return int(r.id)


def get_resume(id: int, *, session: Optional[Session] = None) -> Optional[dict]:
    rid = _to_int_or_none(id)
    if rid is None:
        return None
    with _scope(session) as s:
        r = s.get(Resume, rid)
        return _resume_to_dict(r) if r else None


def latest_resume(*, session: Optional[Session] = None) -> Optional[dict]:
    with _scope(session) as s:
        r = s.scalars(
            select(Resume).order_by(Resume.created_at.desc(), Resume.id.desc()).limit(1)
        ).first()
        return _resume_to_dict(r) if r else None


# --------------------------------------------------------------------------- jobs

def upsert_jobs(jobs: Iterable[dict], *, session: Optional[Session] = None) -> int:
    """Insert new jobs, skipping duplicates (by dedupe hash). Returns number inserted.

    Existing rows are left unchanged (first-seen wins), apart from filling in
    fields that were previously empty.
    """
    rows: dict[str, dict] = {}
    for job in jobs or []:
        if not isinstance(job, dict):
            continue
        if not (_str_or_none(job.get("url")) or _str_or_none(job.get("title"))):
            continue  # nothing identifying; skip junk
        h = compute_dedupe_hash(job)
        rows.setdefault(h, job)
    if not rows:
        return 0

    with _scope(session) as s:
        existing: dict[str, Job] = {}
        hashes = list(rows)
        for i in range(0, len(hashes), 500):  # keep IN() lists bounded
            chunk = hashes[i : i + 500]
            for j in s.scalars(select(Job).where(Job.dedupe_hash.in_(chunk))):
                existing[j.dedupe_hash] = j

        inserted = 0
        now = utcnow()
        for h, job in rows.items():
            values = {
                "title": _str_or_none(job.get("title")),
                "company": _str_or_none(job.get("company")),
                "location": _str_or_none(job.get("location")),
                "description": job.get("description") or None,
                "source": (_str_or_none(job.get("source")) or None),
                "url": _str_or_none(job.get("url")),
                "posted_date": _to_naive_utc(job.get("posted_date")),
                "experience_years": _to_int_or_none(job.get("experience_years")),
            }
            if values["source"]:
                values["source"] = values["source"][:MAX_SOURCE_LEN]
            cur = existing.get(h)
            if cur is not None:
                for k, v in values.items():
                    if v is not None and getattr(cur, k) in (None, ""):
                        setattr(cur, k, v)
                continue
            s.add(Job(dedupe_hash=h, scraped_at=now, **values))
            inserted += 1
        s.flush()
        return inserted


def list_jobs(limit: int = 50, *, session: Optional[Session] = None) -> list[dict]:
    """Most recently scraped jobs first."""
    with _scope(session) as s:
        stmt = select(Job).order_by(Job.scraped_at.desc(), Job.id.desc()).limit(_clamp_limit(limit))
        return [_job_to_dict(j) for j in s.scalars(stmt)]


def get_job(id: int, *, session: Optional[Session] = None) -> Optional[dict]:
    jid = _to_int_or_none(id)
    if jid is None:
        return None
    with _scope(session) as s:
        j = s.get(Job, jid)
        return _job_to_dict(j) if j else None


# --------------------------------------------------------------------------- matches

_SCORE_KEYS = {
    "confidence_score": ("total", "confidence_score", "confidence"),
    "ats_score": ("ats", "ats_score"),
    "experience_score": ("experience", "experience_score"),
    "semantic_score": ("semantic", "semantic_score"),
    "freshness_score": ("freshness", "freshness_score"),
}


def _extract_scores(scores: dict) -> dict:
    out: dict[str, Optional[float]] = {}
    for col, keys in _SCORE_KEYS.items():
        val = None
        for k in keys:
            if k in scores:
                val = _to_float_or_none(scores[k])
                break
        out[col] = val
    return out


def save_match(
    resume_id: int, job_id: int, scores: dict, *, session: Optional[Session] = None
) -> int:
    """Create or update the (resume_id, job_id) match with ``scores``; returns match id.

    ``scores`` may use confidence_score keys (total/ats/experience/semantic/freshness)
    or column names (confidence_score/ats_score/...). An existing match keeps its status
    unless ``scores["status"]`` is given.
    """
    scores = scores or {}
    values = _extract_scores(scores)
    status = _str_or_none(scores.get("status"))
    rid, jid = int(resume_id), int(job_id)
    with _scope(session) as s:
        m = s.scalars(
            select(Match).where(Match.resume_id == rid, Match.job_id == jid)
        ).first()
        if m is None:
            m = Match(resume_id=rid, job_id=jid, status=(status or "new")[:MAX_STATUS_LEN])
            s.add(m)
        elif status:
            m.status = status[:MAX_STATUS_LEN]
        for k, v in values.items():
            setattr(m, k, v)
        m.calculated_at = utcnow()
        s.flush()
        return int(m.id)


def list_matches(
    resume_id: int, limit: int = 50, *, session: Optional[Session] = None
) -> list[dict]:
    """Matches for a resume joined with job fields, highest confidence first."""
    rid = _to_int_or_none(resume_id)
    if rid is None:
        return []
    with _scope(session) as s:
        stmt = (
            select(Match, Job)
            .join(Job, Match.job_id == Job.id)
            .where(Match.resume_id == rid)
            .order_by(Match.confidence_score.desc().nulls_last(), Match.id.asc())
            .limit(_clamp_limit(limit))
        )
        out = []
        for m, j in s.execute(stmt):
            d = _job_to_dict(j)
            d.pop("id")
            d.update(_match_to_dict(m))  # "id" is the match id; job id in "job_id"
            out.append(d)
        return out


def update_match_status(match_id: int, status: str, *, session: Optional[Session] = None) -> bool:
    """Set a match's status. Returns False if the match does not exist."""
    st = _str_or_none(status)
    if not st:
        raise ValueError("status must be a non-empty string")
    mid = _to_int_or_none(match_id)
    if mid is None:
        return False
    with _scope(session) as s:
        m = s.get(Match, mid)
        if m is None:
            return False
        m.status = st[:MAX_STATUS_LEN]
        return True


# --------------------------------------------------------------------------- documents

def save_document(
    match_id: int,
    doc_type: str,
    content: str,
    file_path: Optional[str],
    *,
    session: Optional[Session] = None,
) -> int:
    dt = _str_or_none(doc_type)
    if not dt:
        raise ValueError("doc_type must be a non-empty string")
    with _scope(session) as s:
        mid = int(match_id)
        if s.get(Match, mid) is None:
            raise ValueError(f"match {mid} does not exist")
        d = Document(
            match_id=mid,
            doc_type=dt[:MAX_DOC_TYPE_LEN],
            content=content,
            file_path=_str_or_none(file_path),
            generated_at=utcnow(),
        )
        s.add(d)
        s.flush()
        return int(d.id)


def list_documents(match_id: int, *, session: Optional[Session] = None) -> list[dict]:
    """Documents for a match, newest first."""
    mid = _to_int_or_none(match_id)
    if mid is None:
        return []
    with _scope(session) as s:
        stmt = (
            select(Document)
            .where(Document.match_id == mid)
            .order_by(Document.generated_at.desc(), Document.id.desc())
        )
        return [_document_to_dict(d) for d in s.scalars(stmt)]


__all__ = [
    "compute_dedupe_hash",
    "save_resume",
    "get_resume",
    "latest_resume",
    "upsert_jobs",
    "list_jobs",
    "get_job",
    "save_match",
    "list_matches",
    "update_match_status",
    "save_document",
    "list_documents",
]
