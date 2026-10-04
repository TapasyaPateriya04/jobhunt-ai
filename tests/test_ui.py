"""Smoke tests for the Streamlit dashboard using streamlit.testing.v1.AppTest."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "ui" / "app.py")
TAB_LABELS = ["Resume", "Find jobs", "Matches", "Applications", "Documents"]

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
    empties = " ".join(m.value for m in at.markdown if "jh-empty" in m.value)
    assert "No resume yet" in empties and "Add your resume first" in empties
    assert "No jobs collected yet" in empties
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
    # Each job is a card with its own expander; the sliders stay; new filters are dropdowns.
    cards = [m.value for m in at.markdown if "jh-card" in m.value and "<style>" not in m.value]
    assert len(cards) == 2 and all("Initech" in card for card in cards)  # stored job + match
    assert "jh-score" in cards[1] and ">72<" in cards[1]
    assert any(e.label == "Score breakdown, skills and full posting" for e in at.expander)
    assert {"Save", "Hide"} <= {b.label for b in at.button}
    assert {"Minimum confidence", "Asks for at most (years)"} <= {s.label for s in at.slider}
    assert {"Your country", "Source", "Status", "Sort by"} <= {s.label for s in at.selectbox}
    assert {"Only jobs I can take", "Include jobs that state no years",
            "Show the full job description"} <= {c.label for c in at.checkbox}
    assert len(at.dataframe) == 0  # cards replaced the tables


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


def _seed(total=50.0, job=None):
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([job or JOB])
    job_id = repo.list_jobs()[0]["id"]
    repo.save_match(rid, job_id, {"total": total, "ats": 50, "semantic": 50, "experience": 50, "freshness": 50})
    return rid


def test_add_skill_by_typing_is_saved_and_shown(ui_env):
    from db import repository as repo

    rid = _seed()
    at = _run()
    at.text_input[0].input("postgresql, Figma , python").run()   # "python" is already there
    next(b for b in at.button if b.label == "Add skill").click().run()
    _assert_clean(at)
    assert repo.get_resume(rid)["extra_skills"] == ["PostgreSQL", "Figma"]  # canonical names, no duplicate
    assert any("PostgreSQL" in m.value and "Figma" in m.value for m in at.markdown)
    assert any("Added: PostgreSQL, Figma" in s.value for s in at.success)

    # Removing one goes through a dropdown + button.
    at.selectbox(key="remove_skill").select("Figma").run()
    at.button(key="remove_skill_btn").click().run()
    _assert_clean(at)
    assert repo.get_resume(rid)["extra_skills"] == ["PostgreSQL"]


def test_skill_suggestions_for_jobs_a_few_skills_short(ui_env):
    from db import repository as repo

    # The posting asks for Python, Django, PostgreSQL, Docker; the resume lacks only PostgreSQL.
    rid = _seed()
    at = _run()
    _assert_clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "Skills worth adding" in text and "PostgreSQL (1 job)" in text
    assert "Only 1 skill short of a full match: PostgreSQL" in text
    assert "add **PostgreSQL** (you have 3 of 4)" in text

    # "Already have it" adds the skill, after which the job is no longer short of anything.
    at.selectbox[[s.label for s in at.selectbox].index(
        "Already have one of these? Add it to your skills")].select("PostgreSQL").run()
    [b for b in at.button if b.label == "Add skill"][-1].click().run()
    _assert_clean(at)
    assert repo.get_resume(rid)["extra_skills"] == ["PostgreSQL"]
    assert "skill short" not in " ".join(m.value for m in at.markdown)


def test_filters_hide_jobs_by_location_and_level(ui_env, monkeypatch):
    monkeypatch.setenv("CANDIDATE_COUNTRY", "India")
    _seed(job={**JOB, "location": "REMOTE (US only)"})
    at = _run()
    _assert_clean(at)
    assert at.selectbox(key="home_country").value == "India"
    assert any("No jobs pass these filters" in m.value for m in at.markdown)   # US-only job is hidden
    next(c for c in at.checkbox if c.label == "Only jobs I can take").uncheck().run()
    _assert_clean(at)
    assert any(e.label == "Score breakdown, skills and full posting" for e in at.expander)
    assert any("Limited to United States" in m.value for m in at.markdown)  # the card says why
    # The years slider hides a posting that asks for 3 years.
    next(s for s in at.slider if s.label == "Asks for at most (years)").set_value(1).run()
    assert any("No jobs pass these filters" in m.value for m in at.markdown)


def test_resume_switcher_appears_with_two_resumes(ui_env):
    from db import repository as repo

    repo.save_resume(RESUME, "first.txt")
    second = repo.save_resume({**RESUME, "raw_text": "Another resume. Java developer."}, "second.txt")
    at = _run()
    _assert_clean(at)
    picker = at.selectbox(key="resume_picker")
    assert picker.value == second and len(picker.options) == 2


def test_save_and_hide_buttons_on_a_job_card(ui_env):
    from db import repository as repo

    rid = _seed()
    mid = repo.list_matches(rid)[0]["id"]
    at = _run()
    at.button(key=f"save_{mid}").click().run()
    _assert_clean(at)
    assert repo.list_matches(rid)[0]["status"] == "saved"
    assert at.button(key=f"save_{mid}").label == "Unsave"
    assert at.selectbox(key=f"status_{mid}").value == "saved"   # the dropdown follows the button
    assert any('jh-badge saved' in m.value for m in at.markdown)

    at.button(key=f"hide_{mid}").click().run()
    _assert_clean(at)
    assert repo.list_matches(rid)[0]["status"] == "hidden"
    assert any("No jobs pass these filters" in m.value for m in at.markdown)  # hidden jobs leave the list
    # ... and come back under Status: hidden, where they can be unhidden.
    at.selectbox[[s.label for s in at.selectbox].index("Status")].select("hidden").run()
    at.button(key=f"hide_{mid}").click().run()
    assert repo.list_matches(rid)[0]["status"] == "new"


def test_cards_are_paged_and_escape_posting_text(ui_env):
    from db import repository as repo

    rid = repo.save_resume(RESUME, "resume.txt")
    jobs = [{**JOB, "title": f"Dev {i} <script>alert(1)</script>", "url": f"https://remoteok.com/remote-jobs/{i}"}
            for i in range(13)]
    repo.upsert_jobs(jobs)
    for j in repo.list_jobs(limit=50):
        repo.save_match(rid, j["id"], {"total": 50, "ats": 50, "semantic": 50, "experience": 50, "freshness": 50})
    at = _run()
    _assert_clean(at)
    cards = [m.value for m in at.markdown if "jh-card" in m.value and "<style>" not in m.value]
    assert len(cards) == 20  # 10 stored jobs + 10 matches on the first page
    assert all("<script>" not in card and "&lt;script&gt;" in card for card in cards)
    at.button(key="more_matches").click().run()
    _assert_clean(at)
    cards = [m.value for m in at.markdown if "jh-card" in m.value and "<style>" not in m.value]
    assert len(cards) == 23 and not any(b.key == "more_matches" for b in at.button)


def test_job_card_helpers():
    from datetime import datetime, timedelta

    from ui import components as c

    now = datetime(2026, 9, 30)
    assert [c.time_ago(now - timedelta(days=d), now) for d in (0, 1, 2, 20, 90)] == [
        "Today", "1 day ago", "2 days ago", "2 weeks ago", "3 months ago"]
    assert c.time_ago(None) == "" and c.time_ago("2026-09-01") == ""
    assert c.snippet("a  b\n c") == "a b c" and c.snippet("word " * 100, 20) == "word word word word..."
    card = c.job_card_html({"title": "T", "company": "Acme & Co", "location": "Pune", "source": "themuse",
                            "url": "javascript:alert(1)", "description": "d"}, score="n/a", link=True,
                           fit='Limited to "US"', fit_ok=False, missing=["Kafka"], status="applied")
    assert "Acme &amp; Co" in card and "javascript:" not in card and "jh-score" not in card
    assert 'class="bad"' in card and "&quot;US&quot;" in card and "jh-tag miss" in card
    assert "jh-badge applied" in card and "The Muse" in card


def test_score_breakdown_and_summary_strip(ui_env):
    _seed(total=72.5)
    at = _run()
    _assert_clean(at)
    html = " ".join(m.value for m in at.markdown)
    assert "jh-bars" in html and "Skills and keywords" in html and "Experience fit" in html
    assert 'class="jh-strip"' in html and "<b>1</b> of 1 jobs" in html
    assert "jh-score hi" in html  # 72.5 is a strong match


def test_overview_names_the_next_step(ui_env):
    at = _run()
    assert any("Next step:" in m.value and "Upload your resume" in m.value for m in at.markdown)
    rid = _seed(total=72.5)
    at = _run()
    _assert_clean(at)
    text = " ".join(m.value for m in at.markdown)
    assert "<b>1</b><span>strong matches</span>" in text and "press <b>Save</b>" in text
    # Saving a job moves the next step on to writing for it.
    from db import repository as repo

    at.button(key=f"save_{repo.list_matches(rid)[0]['id']}").click().run()
    assert any("You have 1 saved job." in m.value for m in at.markdown)


def test_score_is_labelled_in_words(ui_env):
    from ui import components as c

    assert [c.score_label(v) for v in (72, 40, 10, None)] == [
        "Strong match", "Possible match", "Weak match", "Not scored"]
    card = c.job_card_html({"title": "T", "company": "C"}, score=40)
    assert "jh-score mid" in card and "Possible match" in card and 'aria-label="Match score 40 out of 100' in card


def test_applications_tab_tracks_saved_jobs(ui_env):
    from db import repository as repo

    rid = _seed()
    mid = repo.list_matches(rid)[0]["id"]
    at = _run()
    assert any("No applications tracked yet" in m.value for m in at.markdown)
    at.button(key=f"save_{mid}").click().run()
    _assert_clean(at)
    assert not any("No applications tracked yet" in m.value for m in at.markdown)
    assert at.selectbox(key=f"track_{mid}").value == "saved"
    assert any("<b>1</b><span>saved, to apply to</span>" in m.value for m in at.markdown)

    # Changing the status there is stored and the card on the Matches tab follows.
    at.selectbox(key=f"track_{mid}").select("applied").run()
    _assert_clean(at)
    assert repo.list_matches(rid)[0]["status"] == "applied"
    assert at.selectbox(key=f"status_{mid}").value == "applied"
    assert any("jh-badge applied" in m.value for m in at.markdown)

    # "Write documents" selects the job on the Documents tab.
    at.button(key=f"write_{mid}").click().run()
    _assert_clean(at)
    assert at.selectbox(key="doc_job").value == mid


def test_search_and_reset_filters(ui_env):
    _seed()
    at = _run()
    search = next(t for t in at.text_input if t.label == "Search")
    search.input("initech django").run()
    _assert_clean(at)
    assert any("<b>1</b> of 1 jobs" in m.value for m in at.markdown)
    next(t for t in at.text_input if t.label == "Search").input("cobol").run()
    assert any("No jobs pass these filters" in m.value for m in at.markdown)
    at.button(key="filter_reset_btn").click().run()
    _assert_clean(at)
    assert next(t for t in at.text_input if t.label == "Search").value == ""
    assert any("<b>1</b> of 1 jobs" in m.value for m in at.markdown)


def test_job_description_is_formatted_and_escaped(ui_env):
    from db import repository as repo
    from ui import components as c

    html = c.description_html("About us\n\nWe build <b>things</b>.\n- Python\n* Django\nRequirements:\n1. SQL")
    assert "<h6>About us</h6>" in html and "<p>We build &lt;b&gt;things&lt;/b&gt;.</p>" in html
    assert "<ul><li>Python</li><li>Django</li></ul>" in html and "<h6>Requirements</h6><ul><li>SQL</li></ul>" in html
    # A sentence broken across lines stays one paragraph instead of becoming a heading.
    assert c.description_html("We migrate to our\nCelonis Platform\nSaaS solution.") == (
        '<div class="jh-jd" tabindex="0" role="region" aria-label="Full job description">'
        "<p>We migrate to our Celonis Platform SaaS solution.</p></div>")

    rid = _seed()
    mid = repo.list_matches(rid)[0]["id"]
    at = _run()
    at.checkbox(key=f"jd_{mid}").check().run()
    _assert_clean(at)
    assert any('class="jh-jd"' in m.value and "PostgreSQL" in m.value for m in at.markdown)


def test_scoring_reports_progress(ui_env):
    pytest.importorskip("matching.confidence_score")
    from db import repository as repo

    repo.save_resume(RESUME, "resume.txt")
    repo.upsert_jobs([JOB])
    at = _run()
    next(b for b in at.button if b.label == "Score stored jobs").click().run()
    _assert_clean(at)
    assert [s.label for s in at.status] == ["Scored 1 jobs"] and at.status[0].state == "complete"
    assert any("Scored 1 jobs against your resume" in s.value for s in at.success)


def test_export_to_word_and_pdf():
    pytest.importorskip("docx")
    pytest.importorskip("fpdf")
    from ui import export

    draft = "Dear Hiring Manager,\n\nI\u2019m applying \u2014 **gladly**.\n\n## Skills\n- Java\n- Spring Boot"
    assert [kind for kind, _ in export._blocks(draft)] == [
        "para", "blank", "para", "blank", "heading", "bullet", "bullet"]
    assert export.to_docx(draft, "Cover letter")[:2] == b"PK"
    assert export.to_pdf(draft, "Cover letter")[:5] == b"%PDF-"
    assert export._latin1("I\u2019m \u2014 \u4e2d") == "I'm - ?"


def test_draft_can_be_downloaded_in_three_formats(ui_env, monkeypatch):
    pytest.importorskip("docx")
    pytest.importorskip("fpdf")
    from db import repository as repo

    rid = _seed()
    mid = repo.list_matches(rid)[0]["id"]
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state[f"draft_{mid}_cover_letter"] = "Dear team,\n\nHello."
    at.run()
    _assert_clean(at)
    assert any(t.label == "Edit before saving" for t in at.text_area)
    assert any("3 words" in cap.value for cap in at.caption)
    labels = [el.proto.label for el in at.get("download_button")]
    assert labels == ["Download .txt", "Download .docx", "Download .pdf"]


def test_charts_summarise_the_jobs_shown(ui_env):
    from ui import components as c

    bars = c.count_bars_html([("A <b>", 4), ("B", 1)], note="n")
    assert "A &lt;b&gt;" in bars and "width:100%" in bars and "width:25%" in bars and "<b>1</b>" in bars
    _seed(total=72.5)
    at = _run()
    _assert_clean(at)
    assert any(e.label.startswith("Charts for the jobs shown") for e in at.expander)
    charts = " ".join(m.value for m in at.markdown if "jh-counts" in m.value and "<style>" not in m.value)
    assert "<label>Strong (50+)</label>" in charts and "<label>RemoteOK</label>" in charts
    assert "PostgreSQL (missing)" in charts


def test_missing_library_says_how_to_start_the_app(monkeypatch):
    import importlib

    from ui import components as c

    def fake_import(name):
        raise ModuleNotFoundError("No module named 'sqlalchemy'", name="sqlalchemy")

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(c.FeatureUnavailable) as info:
        c.load("db.database", "init_db")
    assert "`sqlalchemy` library is not installed" in str(info.value)
    assert "-m streamlit run ui/app.py" in str(info.value)

    def missing_project_module(name):
        raise ModuleNotFoundError(f"No module named '{name}'", name=name)

    monkeypatch.setattr(importlib, "import_module", missing_project_module)
    with pytest.raises(c.FeatureUnavailable, match="is not available yet"):
        c.load("generator.cover_letter")


def test_backup_and_clean_up_panel(ui_env):
    pytest.importorskip("alembic")
    from datetime import datetime

    from db import repository as repo

    rid = _seed()
    repo.upsert_jobs([{**JOB, "title": "Ancient role", "url": "https://remoteok.com/remote-jobs/old",
                       "posted_date": datetime(2020, 1, 1)}])
    at = _run()
    _assert_clean(at)
    assert any(e.label == "Back up or clean up stored jobs" for e in at.expander)
    at.button(key="backup_prepare").click().run()
    _assert_clean(at)
    labels = [el.proto.label for el in at.get("download_button")]
    assert {"Download jobs.csv", "Download matches.csv"} <= set(labels)

    assert at.button(key="stale_delete").disabled  # nothing happens until the box is ticked
    at.checkbox(key="stale_confirm").check().run()
    at.button(key="stale_delete").click().run()
    _assert_clean(at)
    assert [j["title"] for j in repo.list_jobs()] == ["Python Developer"]
    assert len(repo.list_matches(rid)) == 1
    assert any("Deleted 1 jobs older than 30 days" in s.value for s in at.success)


def test_model_picker_lists_ollama_models_and_reaches_the_generator(ui_env, monkeypatch):
    from ui import components as c
    import generator.cover_letter as cover_letter

    monkeypatch.setenv("USE_OLLAMA", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral")
    models = [{"name": "llama3.2:3b", "size": "3.2B", "bytes": 2}, {"name": "mistral:latest", "size": "7.2B", "bytes": 4}]
    monkeypatch.setattr(c, "ollama_models", lambda base: models)
    monkeypatch.setattr(c, "ollama_reachable", lambda base: True)
    used = {}
    monkeypatch.setattr(cover_letter, "generate_cover_letter",
                        lambda resume, job, model=None: used.setdefault("model", model) and "Dear Hiring Manager,")
    _seed()
    at = _run()
    _assert_clean(at)
    picker = at.selectbox(key="llm_model")
    assert picker.options == ["llama3.2:3b (3.2B)", "mistral:latest (7.2B)"]
    assert picker.value == "mistral:latest"  # OLLAMA_MODEL=mistral is the default
    assert "2 models installed" in " ".join(m.value for m in at.sidebar.markdown)
    picker.select("llama3.2:3b").run()
    next(b for b in at.button if b.label == "Generate").click().run()
    _assert_clean(at)
    assert used["model"] == "llama3.2:3b"
    assert any("Written by llama3.2:3b" in cap.value for cap in at.caption)


def test_draft_with_invented_claims_gets_a_warning(ui_env):
    from db import repository as repo

    rid = _seed()
    mid = repo.list_matches(rid)[0]["id"]
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state[f"draft_{mid}_cover_letter"] = (
        "Dear Hiring Manager,\n\nAs a seasoned engineer with 8 years of experience, I am a great fit.")
    at.run()
    _assert_clean(at)
    (warning,) = [w.value for w in at.warning if "before you send this" in w.value]
    assert "Check 1 sentence" in warning and "seasoned" in warning and "8 years" in warning
