"""JobHunt AI - local Streamlit dashboard (SPEC §7).

Run with:  streamlit run ui/app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from ui import components as c  # noqa: E402
from ui.components import FeatureUnavailable, friendly_errors, g, load  # noqa: E402

RESUME_EXTS = {".tex", ".txt", ".md", ".pdf"}


# --------------------------------------------------------------------------- setup

class _FallbackSettings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///jobhunt.db")
        self.use_ollama = os.getenv("USE_OLLAMA", "true").lower() not in {"0", "false", "no"}
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY") or None
        self.docs_dir = os.getenv("DOCS_DIR", "~/jobhunt_docs")
        self.max_jobs_per_session = 50
        self.upload_max_bytes = 2_000_000


def get_settings():
    try:
        return load("config", "get_settings")()
    except Exception:
        return _FallbackSettings()


@st.cache_resource(show_spinner=False)
def bootstrap(database_url: str) -> str:
    """One-time logging + schema setup per database URL. Returns an error string or ''."""
    problems = []
    try:
        load("security.logging_setup", "setup_logging")()
    except Exception as exc:  # logging is nice-to-have
        problems.append(f"logging setup skipped ({type(exc).__name__})")
    try:
        load("db.database", "init_db")()
    except Exception as exc:
        c.log.exception("init_db failed")
        return f"Database could not be initialised ({type(exc).__name__}). Check DATABASE_URL."
    return "; ".join(problems) if problems else ""


def repo():
    return load("db.repository")


def db_counts() -> dict:
    try:
        from sqlalchemy import func, select

        dbm = load("db.database")
        with dbm.get_session() as s:
            return {name: s.scalar(select(func.count()).select_from(model)) or 0
                    for name, model in (("Resumes", dbm.Resume), ("Jobs", dbm.Job),
                                        ("Matches", dbm.Match), ("Documents", dbm.Document))}
    except Exception:
        return {}


def current_resume() -> dict | None:
    if st.session_state.get("resume") is None:
        try:
            st.session_state["resume"] = repo().latest_resume()
        except Exception:
            c.log.exception("latest_resume failed")
            st.session_state["resume"] = None
    return st.session_state.get("resume")


# --------------------------------------------------------------------------- sidebar

def render_sidebar(settings) -> None:
    with st.sidebar:
        st.header("System status")
        st.caption("LLM backends")
        use_ollama = bool(getattr(settings, "use_ollama", True))
        base = str(getattr(settings, "ollama_base_url", "http://localhost:11434"))
        model = getattr(settings, "ollama_model", "mistral")
        if use_ollama:
            c.status_row("Ollama", c.ollama_reachable(base), f"reachable ({model})",
                         "not reachable - run `ollama serve`")
        else:
            c.status_row("Ollama", False, "", "disabled (USE_OLLAMA=false)")
        has_key = bool(getattr(settings, "gemini_api_key", None))
        c.status_row("Gemini", has_key, "API key configured", "no GEMINI_API_KEY set")

        st.divider()
        st.caption("Storage")
        st.markdown(f"**Database:** `{c.db_location(str(settings.database_url))}`")
        st.markdown(f"**Documents:** `{getattr(settings, 'docs_dir', '~/jobhunt_docs')}`")
        counts = db_counts()
        if counts:
            cols = st.columns(2)
            for i, (k, v) in enumerate(counts.items()):
                cols[i % 2].metric(k, v)
        st.divider()
        st.caption("Everything runs locally. Your data never leaves this machine "
                   "unless you enable Gemini.")


# --------------------------------------------------------------------------- tab 1

def tab_resume(settings) -> None:
    st.subheader("Upload your resume")
    st.caption("LaTeX (.tex), plain text (.txt), Markdown (.md) or PDF. Max 2 MB.")
    uploaded = st.file_uploader("Resume file", type=[e.lstrip(".") for e in sorted(RESUME_EXTS)],
                                key="resume_upload")
    if uploaded is not None:
        fingerprint = (uploaded.name, uploaded.size)
        if st.session_state.get("resume_fingerprint") != fingerprint:
            with friendly_errors("process the resume"), st.spinner("Parsing resume..."):
                data = uploaded.getvalue()
                max_bytes = int(getattr(settings, "upload_max_bytes", 2_000_000))
                load("security.sanitize", "validate_upload")(uploaded.name, data, RESUME_EXTS, max_bytes)
                parsed = load("parser.resume_parser", "parse_resume_bytes")(uploaded.name, data)
                file_path = _store_upload(settings, uploaded.name, data)
                resume_id = repo().save_resume(parsed, file_path)
                resume = repo().get_resume(resume_id) or dict(parsed, id=resume_id)
                st.session_state["resume"] = resume
                st.session_state["resume_fingerprint"] = fingerprint
                st.success("Resume parsed and saved. Head to **Scrape Jobs** next.")

    resume = current_resume()
    if not resume:
        st.info("No resume saved yet. Upload one above to get started.")
        return
    _render_resume(resume)


def _store_upload(settings, filename: str, data: bytes) -> str:
    """Keep a copy of the upload in docs_dir/uploads (safe path); fall back to the bare name."""
    try:
        sanitize = load("security.sanitize")
        base = Path(os.path.expanduser(str(getattr(settings, "docs_dir", "~/jobhunt_docs")))) / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        path = sanitize.safe_join(base, sanitize.safe_filename(filename))
        path.write_bytes(data)
        return str(path)
    except Exception:
        c.log.warning("Could not store uploaded resume copy", exc_info=True)
        return filename


def _render_resume(resume: dict) -> None:
    skills = c.as_list(g(resume, "skills", "skills_json", default=[]))
    experience = c.as_list(g(resume, "experience", "experience_json", default=[]))
    education = g(resume, "education", default="") or ""
    summary = g(resume, "summary", default="") or ""

    m1, m2, m3 = st.columns(3)
    m1.metric("Skills detected", len(skills))
    m2.metric("Experience entries", len(experience))
    m3.metric("Resume ID", g(resume, "id", default="-"))

    if summary:
        st.markdown("#### Summary")
        st.write(summary)
    st.markdown("#### Skills")
    c.chips(skills)
    left, right = st.columns(2)
    with left:
        st.markdown("#### Experience")
        if experience:
            for item in experience[:12]:
                st.markdown(f"- {c.experience_line(item)}", unsafe_allow_html=True)
        else:
            st.caption("No experience section detected.")
    with right:
        st.markdown("#### Education")
        if education:
            st.write(education if isinstance(education, str) else c.as_list(education))
        else:
            st.caption("No education section detected.")
    raw = g(resume, "raw_text", default="")
    if raw:
        with st.expander("Raw extracted text"):
            st.text(raw[:10000])


# --------------------------------------------------------------------------- tab 2

def tab_scrape(settings) -> None:
    st.subheader("Scrape job listings")
    st.info(c.ETHICAL_NOTE)
    cap = int(getattr(settings, "max_jobs_per_session", 50) or 50)
    with st.form("scrape_form"):
        col1, col2 = st.columns(2)
        keywords = col1.text_input("Job keywords", "Python Developer")
        location = col2.text_input("Location", "Remote")
        max_jobs = st.slider("Max jobs to scrape", 5, max(5, min(50, cap)), min(20, cap))
        sources = st.multiselect("Sources", options=list(c.SOURCES), default=c.DEFAULT_SOURCES,
                                 format_func=lambda s: c.SOURCES[s])
        submitted = st.form_submit_button("Start scraping", type="primary")

    if any(s in sources for s in ("indeed", "linkedin", "naukri")):
        st.caption("Playwright sources run a headless browser slowly and politely; they "
                   "return nothing if Playwright isn't installed or robots.txt disallows them.")

    if submitted:
        if not keywords.strip():
            st.warning("Enter at least one keyword.")
        elif not sources:
            st.warning("Pick at least one source.")
        else:
            with friendly_errors("scrape jobs"), st.spinner("Scraping... (being polite, this can take a while)"):
                jobs = _scrape(keywords.strip(), location.strip(), int(max_jobs), list(sources))
                new = repo().upsert_jobs(jobs) if jobs else 0
                if jobs:
                    st.success(f"Fetched {len(jobs)} jobs, {new} new. Check the **Matches** tab.")
                else:
                    st.warning("No jobs found. Try broader keywords or another source.")

    with friendly_errors("list stored jobs"):
        jobs = repo().list_jobs(limit=50)
        if jobs:
            st.markdown("#### Recently stored jobs")
            df = pd.DataFrame([{
                "Company": j.get("company"), "Title": j.get("title"), "Location": j.get("location"),
                "Source": j.get("source"), "Posted": j.get("posted_date"), "Link": j.get("url"),
            } for j in jobs])
            st.dataframe(df, hide_index=True, use_container_width=True,
                         column_config={"Link": st.column_config.LinkColumn("Link", display_text="Open")})


def _scrape(keywords: str, location: str, max_jobs: int, sources: list[str]) -> list[dict]:
    try:
        fn = load("scraper.service", "scrape_jobs")
    except FeatureUnavailable:
        fn = load("scraper", "scrape_jobs")
    return list(fn(keywords, location, max_jobs, sources) or [])


# --------------------------------------------------------------------------- tab 3

@st.cache_data(show_spinner=False, max_entries=512)
def _gap(resume_text: str, jd_text: str) -> dict:
    return load("matching.ats_scorer", "keyword_gap")(resume_text, jd_text, top_n=15)


def _score_and_save(resume: dict) -> int:
    r = repo()
    jobs = r.list_jobs(limit=200)
    if not jobs:
        return 0
    results = load("matching.confidence_score", "score_jobs")(resume, jobs)
    saved = 0
    for i, res in enumerate(results or []):
        if not isinstance(res, dict):
            continue
        if isinstance(res.get("scores"), dict):  # contract: job copies with "scores" attached
            scores, job_id = res["scores"], res.get("id")
        else:  # tolerate bare score dicts returned in input order
            scores = res
            job_id = res.get("job_id") or (jobs[i].get("id") if i < len(jobs) else None)
        if job_id is None or "total" not in scores:
            continue
        r.save_match(resume["id"], job_id, scores)
        saved += 1
    return saved


def tab_matches(resume: dict | None) -> None:
    st.subheader("Job matches")
    if not resume or g(resume, "id") is None:
        st.info("Upload a resume first (Resume tab).")
        return

    col_a, col_b = st.columns([1, 3])
    if col_a.button("Score stored jobs", type="primary"):
        with friendly_errors("score jobs"), st.spinner("Scoring jobs against your resume..."):
            n = _score_and_save(resume)
            if n:
                st.success(f"Scored {n} jobs.")
            else:
                st.warning("No jobs to score yet - scrape some first.")
    min_score = col_b.slider("Minimum confidence", 0, 100, 0, step=5)

    with friendly_errors("load matches"):
        matches = repo().list_matches(resume["id"], limit=200)
        if not matches:
            st.info("No matches yet. Scrape jobs, then click **Score stored jobs**.")
            return
        shown = [m for m in matches if float(g(m, "confidence_score", "total", default=0) or 0) >= min_score]
        st.caption(f"{len(shown)} of {len(matches)} matches at or above {min_score}%. "
                   "Click a column header to sort.")
        if not shown:
            return
        df = pd.DataFrame([{
            "Company": g(m, "company"), "Title": g(m, "title"), "Location": g(m, "location"),
            "Total": g(m, "confidence_score", "total"), "ATS": g(m, "ats_score", "ats"),
            "Semantic": g(m, "semantic_score", "semantic"),
            "Experience": g(m, "experience_score", "experience"),
            "Freshness": g(m, "freshness_score", "freshness"),
            "Status": g(m, "status", default="new"), "Link": g(m, "url"),
        } for m in shown])
        pct = lambda label: st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f")  # noqa: E731
        st.dataframe(df, hide_index=True, use_container_width=True, column_config={
            "Total": pct("Total"), "ATS": st.column_config.NumberColumn("ATS", format="%.0f"),
            "Semantic": st.column_config.NumberColumn("Semantic", format="%.0f"),
            "Experience": st.column_config.NumberColumn("Experience", format="%.0f"),
            "Freshness": st.column_config.NumberColumn("Freshness", format="%.0f"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open"),
        })

        st.markdown("#### Details")
        resume_text = g(resume, "raw_text", default="") or ""
        for m in shown[:30]:
            _match_detail(m, resume_text)
        if len(shown) > 30:
            st.caption("Showing details for the top 30. Raise the minimum score to narrow the list.")


def _match_detail(m: dict, resume_text: str) -> None:
    match_id = g(m, "id", "match_id")
    with st.expander(c.match_label(m)):
        cols = st.columns(5)
        for col, (lbl, keys) in zip(cols, [("Total", ("confidence_score", "total")),
                                           ("ATS", ("ats_score", "ats")),
                                           ("Semantic", ("semantic_score", "semantic")),
                                           ("Experience", ("experience_score", "experience")),
                                           ("Freshness", ("freshness_score", "freshness"))]):
            col.metric(lbl, c.fmt_score(g(m, *keys)))
        url = g(m, "url")
        if url:
            st.markdown(f"[View posting]({url})")
        jd = g(m, "description", default="") or ""
        if jd and resume_text:
            try:
                gap = _gap(resume_text, jd)
                left, right = st.columns(2)
                with left:
                    st.markdown("**Matched keywords**")
                    c.chips(gap.get("matched", []), "ok")
                with right:
                    st.markdown("**Missing keywords**")
                    c.chips(gap.get("missing", []), "miss")
            except Exception:
                c.log.exception("keyword_gap failed")
                st.caption("Keyword analysis unavailable.")
        current = g(m, "status", default="new")
        if match_id is not None:
            st.selectbox("Status", c.MATCH_STATUSES,
                         index=c.MATCH_STATUSES.index(current) if current in c.MATCH_STATUSES else 0,
                         key=f"status_{match_id}", on_change=_on_status_change, args=(match_id,))


def _on_status_change(match_id: int) -> None:
    new = st.session_state.get(f"status_{match_id}")
    try:
        repo().update_match_status(match_id, new)
        st.toast(f"Status set to {new}.")
    except Exception:
        c.log.exception("update_match_status failed")
        st.toast("Could not update status.")


# --------------------------------------------------------------------------- tab 4

DOC_TYPES = {"cover_letter": "Cover letter", "resume_suggestions": "Resume suggestions"}


def tab_generate(resume: dict | None) -> None:
    st.subheader("Generate documents")
    if not resume or g(resume, "id") is None:
        st.info("Upload a resume first (Resume tab).")
        return
    try:
        matches = repo().list_matches(resume["id"], limit=100)
    except Exception:
        c.log.exception("list_matches failed")
        matches = []
    if not matches:
        st.info("No matches yet. Score some jobs in the **Matches** tab first.")
        return

    by_id = {g(m, "id", "match_id"): m for m in matches}
    match_id = st.selectbox("Job", list(by_id), format_func=lambda i: c.match_label(by_id[i]))
    doc_type = st.radio("Document", list(DOC_TYPES), format_func=DOC_TYPES.get, horizontal=True)
    match = by_id[match_id]
    draft_key = f"draft_{match_id}_{doc_type}"

    if st.button("Generate", type="primary"):
        job = _job_for(match)
        try:
            with st.spinner("Running the language model... (local models can take a minute)"):
                if doc_type == "cover_letter":
                    text = load("generator.cover_letter", "generate_cover_letter")(resume, job)
                else:
                    text = load("generator.resume_optimizer", "suggest_resume_edits")(resume, job)
            st.session_state[draft_key] = text or ""
        except Exception as exc:
            if _is_llm_unavailable(exc):
                st.warning(c.LLM_HELP)
            else:
                with friendly_errors("generate the document"):
                    raise exc

    if draft_key in st.session_state:
        content = st.text_area("Edit before saving", key=draft_key, height=380)
        safe_company = "".join(ch for ch in str(g(match, "company", default="job")) if ch.isalnum())[:40] or "job"
        col1, col2 = st.columns(2)
        col1.download_button("Download .txt", content, file_name=f"{doc_type}_{safe_company}.txt",
                             mime="text/plain", use_container_width=True)
        if col2.button("Save to documents", use_container_width=True):
            with friendly_errors("save the document"):
                path = load("generator.documents", "save_generated_doc")(match_id, doc_type, content)
                st.success(f"Saved to `{path}`.")

    with friendly_errors("list saved documents"):
        docs = repo().list_documents(match_id)
        if docs:
            with st.expander(f"Saved documents for this job ({len(docs)})"):
                for d in docs:
                    st.markdown(f"- **{DOC_TYPES.get(d.get('doc_type'), d.get('doc_type'))}** - "
                                f"`{d.get('file_path') or 'database only'}` "
                                f"<span class='jh-muted'>{d.get('generated_at') or ''}</span>",
                                unsafe_allow_html=True)


def _job_for(match: dict) -> dict:
    job_id = g(match, "job_id")
    if job_id is not None:
        try:
            job = repo().get_job(job_id)
            if job:
                return job
        except Exception:
            c.log.warning("get_job failed", exc_info=True)
    keys = ("title", "company", "location", "description", "source", "url", "posted_date", "experience_years")
    return {k: match.get(k) for k in keys}


def _is_llm_unavailable(exc: Exception) -> bool:
    try:
        return isinstance(exc, load("generator.llm", "LLMUnavailable"))
    except FeatureUnavailable:
        return type(exc).__name__ == "LLMUnavailable"


# --------------------------------------------------------------------------- main

def main() -> None:
    st.set_page_config(page_title="JobHunt AI", page_icon="🎯", layout="wide")
    c.inject_css()
    settings = get_settings()
    problem = bootstrap(str(settings.database_url))

    st.title("🎯 JobHunt AI")
    st.caption("Local, budget-friendly job search: parse your resume, collect jobs politely, "
               "rank matches, and draft tailored documents.")
    if problem.startswith("Database"):
        st.error(problem)
    render_sidebar(settings)

    t1, t2, t3, t4 = st.tabs(["📄 Resume", "🔍 Scrape Jobs", "📊 Matches", "✉️ Generate Docs"])
    with t1:
        with friendly_errors("show the resume tab"):
            tab_resume(settings)
    resume = current_resume()
    with t2:
        with friendly_errors("show the scrape tab"):
            tab_scrape(settings)
    with t3:
        with friendly_errors("show the matches tab"):
            tab_matches(resume)
    with t4:
        with friendly_errors("show the documents tab"):
            tab_generate(resume)


main()
