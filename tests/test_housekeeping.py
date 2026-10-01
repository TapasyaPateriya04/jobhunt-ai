"""Phase 5: migrations, stale-job clean-up and CSV backups."""
from __future__ import annotations

import csv
import importlib.util
import io
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("alembic")
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from db import housekeeping as hk  # noqa: E402
from db import repository as repo  # noqa: E402
from db.database import Base, alembic_config, init_db, schema_revision  # noqa: E402

NOW = datetime(2026, 10, 1, 12, 0)
RESUME = {"raw_text": "Python developer", "skills": ["Python"], "experience": [], "education": "", "summary": ""}
SCORES = {"total": 60, "ats": 50, "semantic": 50, "experience": 50, "freshness": 50}
ROOT = Path(__file__).resolve().parent.parent


def _job(i: int, posted=None, **kw) -> dict:
    return {"title": f"Engineer {i}", "company": "Acme", "location": "Remote", "description": "Python",
            "source": "remoteok", "url": f"https://example.com/jobs/{i}", "posted_date": posted, **kw}


def _ids(session) -> dict:
    return {j["title"]: j["id"] for j in repo.list_jobs(limit=100, session=session)}


# --------------------------------------------------------------------------- migrations

def test_fresh_database_is_migrated_to_head(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    assert schema_revision(engine) is None
    init_db(engine)
    init_db(engine)  # idempotent
    assert schema_revision(engine) == "0001_baseline"
    assert {"resumes", "jobs", "matches", "documents", "alembic_version"} <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_migrations_match_the_models(tmp_path):
    """The migrations must build exactly the schema the models describe. If this fails after
    a model change, write a migration: alembic revision --autogenerate -m "..."."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    init_db(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    engine.dispose()


def test_database_made_before_migrations_keeps_its_data(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    Base.metadata.create_all(engine)  # how init_db made databases until now
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO jobs (title, dedupe_hash, scraped_at) VALUES ('Old job', 'h', '2026-09-01')"))
    init_db(engine)
    assert schema_revision(engine) == "0001_baseline"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM jobs")).scalar() == "Old job"
    engine.dispose()


def test_migrations_downgrade_and_upgrade(tmp_path):
    from alembic import command

    engine = create_engine(f"sqlite:///{(tmp_path / 'd.db').as_posix()}")
    init_db(engine)
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    init_db(engine)
    assert {"jobs", "matches"} <= set(inspect(engine).get_table_names())
    engine.dispose()


# --------------------------------------------------------------------------- stale jobs

@pytest.fixture
def seeded(db_session):
    rid = repo.save_resume(RESUME, "cv.txt", session=db_session)
    repo.upsert_jobs([
        _job(1, NOW - timedelta(days=90)),             # old, untracked: deleted
        _job(2, NOW - timedelta(days=90)),             # old but saved: kept
        _job(3, NOW - timedelta(days=90)),             # old, has a cover letter: kept
        _job(4, NOW - timedelta(days=5)),              # recent: kept
        _job(5, None),                                 # no posting date, collected long ago: deleted
    ], session=db_session)
    ids = _ids(db_session)
    db_session.execute(text("UPDATE jobs SET scraped_at = :t WHERE id = :i"),
                       {"t": NOW - timedelta(days=60), "i": ids["Engineer 5"]})
    mids = {title: repo.save_match(rid, jid, SCORES, session=db_session) for title, jid in ids.items()}
    repo.update_match_status(mids["Engineer 2"], "saved", session=db_session)
    repo.save_document(mids["Engineer 3"], "cover_letter", "Dear team", None, session=db_session)
    return rid, ids


def test_stale_summary_and_delete_keep_tracked_jobs(db_session, seeded):
    rid, ids = seeded
    assert hk.stale_summary(30, now=NOW, session=db_session) == {"stale": 2, "kept": 2}
    assert hk.delete_stale_jobs(30, now=NOW, session=db_session) == 2
    assert set(_ids(db_session)) == {"Engineer 2", "Engineer 3", "Engineer 4"}
    assert len(repo.list_matches(rid, limit=100, session=db_session)) == 3  # their scores went too
    assert hk.stale_summary(30, now=NOW, session=db_session) == {"stale": 0, "kept": 2}
    # A longer window deletes nothing; the tracked jobs survive any window.
    assert hk.delete_stale_jobs(365, now=NOW, session=db_session) == 0
    assert hk.delete_stale_jobs(1, now=NOW, session=db_session) == 1  # only the 5-day-old job
    assert set(_ids(db_session)) == {"Engineer 2", "Engineer 3"}


# --------------------------------------------------------------------------- CSV and backups

def test_csv_exports_rows_and_neutralises_formulas(db_session, seeded):
    rid, _ = seeded
    repo.upsert_jobs([_job(9, NOW, title="=HYPERLINK(\"http://evil\")", company="-Acme")], session=db_session)
    jobs = list(csv.DictReader(io.StringIO(hk.jobs_csv(session=db_session))))
    assert len(jobs) == 6 and list(jobs[0]) == list(hk.JOB_COLUMNS)
    evil = next(j for j in jobs if "HYPERLINK" in j["title"])
    assert evil["title"].startswith("'=") and evil["company"] == "'-Acme"

    matches = list(csv.DictReader(io.StringIO(hk.matches_csv(rid, session=db_session))))
    assert len(matches) == 5 and matches[0]["resume"] == "cv.txt" and matches[0]["confidence_score"] == "60.0"
    assert {m["status"] for m in matches} == {"new", "saved"}
    assert hk.matches_csv(9999, session=db_session).strip() == ",".join(hk.MATCH_COLUMNS)


def test_backup_writes_csvs_and_a_database_copy(tmp_db_url, tmp_path):
    rid = repo.save_resume(RESUME, "cv.txt")
    repo.upsert_jobs([_job(1, NOW)])
    repo.save_match(rid, repo.list_jobs()[0]["id"], SCORES)
    files = hk.backup(tmp_path / "backups")
    assert sorted(p.suffix for p in files) == [".csv", ".csv", ".db"]
    copy = create_engine(f"sqlite:///{next(p for p in files if p.suffix == '.db').as_posix()}")
    with copy.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM matches")).scalar() == 1
    copy.dispose()


def test_housekeeping_script_only_deletes_with_yes(tmp_db_url, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("housekeeping_script", ROOT / "scripts" / "housekeeping.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    repo.upsert_jobs([_job(1, datetime(2020, 1, 1)), _job(2, datetime.now())])
    assert script.main(["clean", "--days", "30"]) == 0
    assert "1 jobs are older than 30 days" in capsys.readouterr().out and len(repo.list_jobs()) == 2
    assert script.main(["clean", "--days", "30", "--yes"]) == 0
    assert "Deleted 1 jobs" in capsys.readouterr().out and len(repo.list_jobs()) == 1
    assert script.main(["status"]) == 0 and "Schema version: 0001_baseline" in capsys.readouterr().out
    assert script.main(["backup", "--dir", str(tmp_path / "b")]) == 0
    assert len(list((tmp_path / "b").iterdir())) == 3
