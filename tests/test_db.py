from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from db import repository as repo
from db.database import (
    Document,
    Job,
    Match,
    Resume,
    get_engine,
    get_session,
    init_db,
    resolve_database_url,
    utcnow,
)

PARSED = {
    "raw_text": "Python developer with SQL and Docker",
    "skills": ["python", "sql", "docker"],
    "experience": [{"title": "Dev", "company": "Acme", "years": 2}],
    "education": "BSc CS",
    "summary": "Backend dev",
}


def _job(i: int, **kw) -> dict:
    d = {
        "title": f"Engineer {i}",
        "company": "Acme",
        "location": "Remote",
        "description": "Build things with Python",
        "source": "remoteok",
        "url": f"https://example.com/jobs/{i}",
        "posted_date": datetime(2026, 9, 1),
        "experience_years": 2,
    }
    d.update(kw)
    return d


def _setup_match(s, score=80.0):
    rid = repo.save_resume(PARSED, "/tmp/r.tex", session=s)
    repo.upsert_jobs([_job(1)], session=s)
    jid = repo.list_jobs(session=s)[0]["id"]
    mid = repo.save_match(rid, jid, {"total": score}, session=s)
    return rid, jid, mid


# ----------------------------------------------------------------- schema

def test_schema_tables_indexes_and_constraints(db_engine):
    insp = inspect(db_engine)
    assert {"resumes", "jobs", "matches", "documents"} <= set(insp.get_table_names())
    job_cols = {c["name"] for c in insp.get_columns("jobs")}
    assert {"location", "posted_date", "experience_years", "dedupe_hash", "scraped_at"} <= job_cols
    match_cols = {c["name"] for c in insp.get_columns("matches")}
    assert {"experience_score", "freshness_score", "status", "calculated_at"} <= match_cols
    idx = {i["name"] for t in ("jobs", "matches") for i in insp.get_indexes(t)}
    assert {"ix_jobs_scraped_at", "ix_matches_resume_id", "ix_matches_confidence_score"} <= idx
    fks = insp.get_foreign_keys("matches") + insp.get_foreign_keys("documents")
    assert fks and all(fk["options"].get("ondelete") == "CASCADE" for fk in fks)


def test_init_db_idempotent(db_engine):
    init_db(db_engine)
    init_db(db_engine)


def test_foreign_keys_enforced(db_session):
    with pytest.raises(IntegrityError):
        repo.save_match(999, 999, {"total": 1}, session=db_session)


def test_dedupe_hash_unique(db_session):
    db_session.add(Job(title="a", dedupe_hash="x" * 64))
    db_session.add(Job(title="b", dedupe_hash="x" * 64))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ----------------------------------------------------------------- resumes

def test_save_and_get_resume(db_session):
    rid = repo.save_resume(PARSED, "/tmp/r.tex", session=db_session)
    r = repo.get_resume(rid, session=db_session)
    assert r["id"] == rid
    assert r["skills"] == ["python", "sql", "docker"]
    assert r["experience"][0]["company"] == "Acme"
    assert r["education"] == "BSc CS" and r["summary"] == "Backend dev"
    assert r["raw_text"].startswith("Python")
    assert isinstance(r["created_at"], datetime)
    assert all(not hasattr(v, "_sa_instance_state") for v in r.values())


def test_get_resume_missing_and_bad_id(db_session):
    assert repo.get_resume(12345, session=db_session) is None
    assert repo.get_resume("nope", session=db_session) is None


def test_save_resume_minimal(db_session):
    rid = repo.save_resume({}, "", session=db_session)
    r = repo.get_resume(rid, session=db_session)
    assert r["skills"] == [] and r["experience"] == [] and r["file_path"] is None


def test_latest_resume(db_session):
    assert repo.latest_resume(session=db_session) is None
    repo.save_resume(PARSED, "a", session=db_session)
    r2 = repo.save_resume({**PARSED, "summary": "second"}, "b", session=db_session)
    assert repo.latest_resume(session=db_session)["id"] == r2


# ----------------------------------------------------------------- jobs

def test_upsert_jobs_dedupes_by_url(db_session):
    assert repo.upsert_jobs([_job(1), _job(2)], session=db_session) == 2
    assert repo.upsert_jobs([_job(1), _job(3)], session=db_session) == 1
    # same url, different title -> duplicate
    assert repo.upsert_jobs([_job(1, title="Other")], session=db_session) == 0
    assert len(repo.list_jobs(session=db_session)) == 3


def test_upsert_jobs_dedupes_within_batch(db_session):
    assert repo.upsert_jobs([_job(1), _job(1)], session=db_session) == 1


def test_upsert_jobs_dedupes_without_url_case_insensitive(db_session):
    a = _job(1, url=None, title="Data Engineer", company="ACME", location="Berlin")
    b = _job(2, url="", title="data engineer", company="acme", location="berlin")
    assert repo.upsert_jobs([a], session=db_session) == 1
    assert repo.upsert_jobs([b], session=db_session) == 0
    c = _job(3, url=None, title="Data Engineer", company="ACME", location="Paris")
    assert repo.upsert_jobs([c], session=db_session) == 1


def test_dedupe_hash_rules():
    h1 = repo.compute_dedupe_hash({"url": "https://x/1", "title": "A"})
    h2 = repo.compute_dedupe_hash({"url": " https://x/1 ", "title": "B"})
    assert h1 == h2 and len(h1) == 64
    assert repo.compute_dedupe_hash({"title": "A", "company": "B", "location": "C"}) == \
        repo.compute_dedupe_hash({"title": "a", "company": "b", "location": "c"})


def test_upsert_jobs_skips_junk(db_session):
    assert repo.upsert_jobs([], session=db_session) == 0
    assert repo.upsert_jobs(None, session=db_session) == 0
    assert repo.upsert_jobs([{"company": "x"}, "bad", None], session=db_session) == 0


def test_upsert_jobs_coerces_fields(db_session):
    repo.upsert_jobs(
        [
            _job(1, posted_date="2026-09-01T10:00:00Z", experience_years="3"),
            _job(2, posted_date="garbage", experience_years="n/a"),
            _job(3, posted_date=datetime(2026, 9, 1, 12, tzinfo=timezone(timedelta(hours=2)))),
        ],
        session=db_session,
    )
    jobs = {j["url"]: j for j in repo.list_jobs(session=db_session)}
    j1 = jobs["https://example.com/jobs/1"]
    assert j1["posted_date"] == datetime(2026, 9, 1, 10) and j1["experience_years"] == 3
    j2 = jobs["https://example.com/jobs/2"]
    assert j2["posted_date"] is None and j2["experience_years"] is None
    assert jobs["https://example.com/jobs/3"]["posted_date"] == datetime(2026, 9, 1, 10)


def test_upsert_fills_missing_fields_on_existing(db_session):
    repo.upsert_jobs([_job(1, description=None)], session=db_session)
    repo.upsert_jobs([_job(1, description="now filled")], session=db_session)
    assert repo.list_jobs(session=db_session)[0]["description"] == "now filled"


def test_list_jobs_order_limit_and_get_job(db_session):
    repo.upsert_jobs([_job(i) for i in range(5)], session=db_session)
    jobs = repo.list_jobs(limit=3, session=db_session)
    assert len(jobs) == 3
    assert jobs[0]["id"] > jobs[-1]["id"]  # newest first (ties broken by id)
    assert repo.list_jobs(limit=0, session=db_session)  # clamped to >= 1
    assert len(repo.list_jobs(limit="bad", session=db_session)) == 5
    j = repo.get_job(jobs[0]["id"], session=db_session)
    assert j["title"] == jobs[0]["title"] and j["scraped_at"] is not None
    assert repo.get_job(99999, session=db_session) is None


# ----------------------------------------------------------------- matches

def test_save_match_upserts(db_session):
    rid, jid, mid = _setup_match(db_session, 50)
    mid2 = repo.save_match(
        rid, jid,
        {"total": 90, "ats": 80, "experience": 70, "semantic": 60, "freshness": 100},
        session=db_session,
    )
    assert mid2 == mid
    assert db_session.scalars(select(Match)).all().__len__() == 1
    m = repo.list_matches(rid, session=db_session)[0]
    assert m["confidence_score"] == 90 and m["ats_score"] == 80
    assert m["experience_score"] == 70 and m["semantic_score"] == 60
    assert m["freshness_score"] == 100 and m["status"] == "new"


def test_save_match_accepts_column_names_and_keeps_status(db_session):
    rid, jid, mid = _setup_match(db_session)
    repo.update_match_status(mid, "applied", session=db_session)
    repo.save_match(rid, jid, {"confidence_score": 42.5, "ats_score": "33"}, session=db_session)
    m = repo.list_matches(rid, session=db_session)[0]
    assert m["confidence_score"] == 42.5 and m["ats_score"] == 33.0
    assert m["status"] == "applied"
    repo.save_match(rid, jid, {"total": 1, "status": "saved"}, session=db_session)
    assert repo.list_matches(rid, session=db_session)[0]["status"] == "saved"


def test_save_resume_same_text_reuses_row(db_session):
    first = repo.save_resume(PARSED, "old/path.pdf", session=db_session)
    again = repo.save_resume({**PARSED, "skills": ["Rust"]}, "new/path.pdf", session=db_session)
    assert again == first  # re-running the pipeline must not pile up copies
    stored = repo.get_resume(first, session=db_session)
    assert stored["skills"] == ["Rust"] and stored["file_path"] == "new/path.pdf"
    other = repo.save_resume({**PARSED, "raw_text": "A different resume"}, "x", session=db_session)
    assert other != first
    # Resumes with no text are never merged with each other.
    assert repo.save_resume({}, "", session=db_session) != repo.save_resume({}, "", session=db_session)


def test_list_matches_sorted_and_joined(db_session):
    rid = repo.save_resume(PARSED, "r", session=db_session)
    other = repo.save_resume({**PARSED, "raw_text": "A different resume"}, "r2", session=db_session)
    repo.upsert_jobs([_job(i) for i in range(4)], session=db_session)
    jobs = repo.list_jobs(session=db_session)
    for j, score in zip(jobs, [10, 90, None, 50]):
        repo.save_match(rid, j["id"], {"total": score}, session=db_session)
    repo.save_match(other, jobs[0]["id"], {"total": 99}, session=db_session)

    ms = repo.list_matches(rid, session=db_session)
    assert [m["confidence_score"] for m in ms] == [90, 50, 10, None]
    first = ms[0]
    assert first["id"] == first["match_id"] and first["job_id"] == jobs[1]["id"]
    assert first["title"] == jobs[1]["title"] and first["company"] == "Acme"
    assert "url" in first and "description" in first
    assert len(repo.list_matches(rid, limit=2, session=db_session)) == 2
    assert repo.list_matches(424242, session=db_session) == []


def test_update_match_status(db_session):
    _, _, mid = _setup_match(db_session)
    assert repo.update_match_status(mid, "applied", session=db_session) is True
    assert repo.update_match_status(9999, "applied", session=db_session) is False
    with pytest.raises(ValueError):
        repo.update_match_status(mid, "  ", session=db_session)


# ----------------------------------------------------------------- documents

def test_save_and_list_documents(db_session):
    _, _, mid = _setup_match(db_session)
    d1 = repo.save_document(mid, "cover_letter", "Dear...", "/docs/a.md", session=db_session)
    d2 = repo.save_document(mid, "resume_edits", "Change X", None, session=db_session)
    docs = repo.list_documents(mid, session=db_session)
    assert {d["id"] for d in docs} == {d1, d2}
    assert docs[0]["id"] == d2  # newest first
    assert docs[1]["doc_type"] == "cover_letter" and docs[1]["file_path"] == "/docs/a.md"
    assert repo.list_documents(9999, session=db_session) == []


def test_save_document_validation(db_session):
    _, _, mid = _setup_match(db_session)
    with pytest.raises(ValueError):
        repo.save_document(mid, "", "x", None, session=db_session)
    with pytest.raises(ValueError):
        repo.save_document(9999, "cover_letter", "x", None, session=db_session)


# ----------------------------------------------------------------- cascade

def test_cascade_delete_resume_removes_matches_and_docs(db_session):
    rid, jid, mid = _setup_match(db_session)
    repo.save_document(mid, "cover_letter", "x", None, session=db_session)
    db_session.delete(db_session.get(Resume, rid))
    db_session.flush()
    assert db_session.scalars(select(Match)).all() == []
    assert db_session.scalars(select(Document)).all() == []
    assert repo.get_job(jid, session=db_session) is not None


def test_db_level_cascade_via_sql(db_session):
    from sqlalchemy import delete

    _, jid, mid = _setup_match(db_session)
    repo.save_document(mid, "cover_letter", "x", None, session=db_session)
    db_session.execute(delete(Job).where(Job.id == jid))  # bypasses ORM cascade
    db_session.flush()
    db_session.expunge_all()
    assert db_session.scalars(select(Match)).all() == []
    assert db_session.scalars(select(Document)).all() == []


# ----------------------------------------------------------------- engine / session

def test_default_session_path_uses_tmp_db_url(tmp_db_url):
    assert resolve_database_url() == tmp_db_url
    rid = repo.save_resume(PARSED, "f")  # no session kwarg -> committed via get_session()
    assert repo.get_resume(rid)["skills"] == PARSED["skills"]
    assert repo.upsert_jobs([_job(1)]) == 1
    jid = repo.list_jobs()[0]["id"]
    mid = repo.save_match(rid, jid, {"total": 77})
    assert repo.list_matches(rid)[0]["match_id"] == mid
    assert repo.update_match_status(mid, "saved") is True
    repo.save_document(mid, "cover_letter", "hi", None)
    assert len(repo.list_documents(mid)) == 1
    assert repo.latest_resume()["id"] == rid


def test_get_engine_cached_per_url(tmp_db_url, tmp_path):
    assert get_engine() is get_engine(tmp_db_url)
    other = f"sqlite:///{(tmp_path / 'other.db').as_posix()}"
    assert get_engine(other) is not get_engine(tmp_db_url)


def test_get_session_rolls_back_on_error(tmp_db_url):
    with pytest.raises(RuntimeError):
        with get_session() as s:
            s.add(Resume(raw_text="x", created_at=utcnow()))
            s.flush()
            raise RuntimeError("boom")
    with get_session() as s:
        assert s.scalars(select(Resume)).all() == []


def test_utcnow_is_naive_utc():
    now = utcnow()
    assert now.tzinfo is None
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds()) < 5


def test_init_db_script(tmp_path):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "init_db.py"
    spec = importlib.util.spec_from_file_location("init_db_script", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    url = f"sqlite:///{(tmp_path / 'script.db').as_posix()}"
    assert mod.main([url]) == 0
    assert "jobs" in inspect(get_engine(url)).get_table_names()
