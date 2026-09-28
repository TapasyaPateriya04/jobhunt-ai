"""Smoke tests for the Streamlit dashboard using streamlit.testing.v1.AppTest."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")
TAB_LABELS = ["📄 Resume", "🔍 Scrape Jobs", "📊 Matches", "✉️ Generate Docs"]

RESUME = {
    "raw_text": "Jane Doe. Python developer with 5 years experience in Django, SQL, Docker and AWS.",
    "skills": ["Python", "Django", "SQL", "Docker", "AWS"],
    "experience": [{"title": "Backend Engineer", "company": "Acme", "dates": "2020-2025"}],
    "education": "B.Tech Computer Science",
    "summary": "Backend developer.",
}
JOB = {
    "title": "Python Developer", "company": "Initech", "location": "Remote",
    "description": "We need a Python developer with Django, PostgreSQL and Docker. 3+ years experience.",
    "source": "remoteok", "url": "https://remoteok.com/remote-jobs/1", "posted_date": None,
    "experience_years": 3,
}


@pytest.fixture
def ui_env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'ui_test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DOCS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("USE_OLLAMA", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    try:
        import config

        clear = getattr(config.get_settings, "cache_clear", None)
        if clear:
            clear()
    except Exception:
        pass
    from db.database import dispose_engines

    dispose_engines()
    yield url
    dispose_engines()


def _run() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def _assert_clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_renders_all_tabs_empty_db(ui_env):
    at = _run()
    _assert_clean(at)
    assert [t.label for t in at.tabs] == TAB_LABELS
    assert at.title[0].value.endswith("JobHunt AI")
    # Empty-state guidance on the data tabs.
    infos = " ".join(i.value for i in at.info)
    assert "Upload" in infos
    # The sidebar never shows a secret and reports Gemini as unconfigured.
    sidebar_md = " ".join(m.value for m in at.sidebar.markdown)
    assert "GEMINI_API_KEY" in sidebar_md


def test_gemini_key_never_displayed(ui_env, monkeypatch):
    secret = "AIzaSy-test-secret-value-123"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    try:
        import config

        clear = getattr(config.get_settings, "cache_clear", None)
        if clear:
            clear()
    except Exception:
        pass
    at = _run()
    _assert_clean(at)
    everything = " ".join(str(getattr(e, "value", "")) for e in at.markdown) + " ".join(
        str(getattr(e, "value", "")) for e in at.sidebar.markdown)
    assert secret not in everything
    assert "API key configured" in everything


def test_renders_with_resume_jobs_and_matches(ui_env):
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([JOB])
    job_id = repo.list_jobs()[0]["id"]
    repo.save_match(rid, job_id, {"total": 72.5, "ats": 60, "semantic": 70, "experience": 100, "freshness": 50})

    at = _run()
    _assert_clean(at)
    assert [t.label for t in at.tabs] == TAB_LABELS
    # Skills chips and the match detail / job picker are rendered.
    assert any("Django" in m.value for m in at.markdown)
    assert any("Initech" in e.label for e in at.expander)
    assert len(at.selectbox) >= 2  # status selector + job picker
    assert len(at.dataframe) >= 2  # stored jobs + matches


def test_status_change_persists(ui_env):
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([JOB])
    job_id = repo.list_jobs()[0]["id"]
    mid = repo.save_match(rid, job_id, {"total": 50, "ats": 50, "semantic": 50, "experience": 50, "freshness": 50})

    at = _run()
    at.selectbox(key=f"status_{mid}").select("applied").run()
    _assert_clean(at)
    assert repo.list_matches(rid)[0]["status"] == "applied"


def test_scoring_button_saves_matches(ui_env):
    pytest.importorskip("matching.confidence_score")
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([JOB])
    at = _run()
    next(b for b in at.button if b.label == "Score stored jobs").click().run()
    _assert_clean(at)
    matches = repo.list_matches(rid)
    assert len(matches) == 1 and matches[0]["confidence_score"] is not None


def test_generate_without_llm_shows_friendly_warning(ui_env, monkeypatch):
    pytest.importorskip("generator.llm")
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([JOB])
    job_id = repo.list_jobs()[0]["id"]
    repo.save_match(rid, job_id, {"total": 50, "ats": 50, "semantic": 50, "experience": 50, "freshness": 50})

    at = _run()
    next(b for b in at.button if b.label == "Generate").click().run()
    assert not at.exception
    # Either a draft was produced (an LLM happened to be reachable) or a friendly warning is shown.
    warned = any("ollama" in w.value.lower() for w in at.warning)
    drafted = any(t.label == "Edit before saving" for t in at.text_area)
    assert warned or drafted
