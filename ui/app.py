"""JobHunt AI - local Streamlit dashboard (SPEC §7).

Run with:  streamlit run ui/app.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui import components as c  # noqa: E402
from ui.components import FeatureUnavailable, friendly_errors, g, load  # noqa: E402

RESUME_EXTS = {".tex", ".txt", ".md", ".pdf"}
TABS = ["Resume", "Find jobs", "Matches", "Applications", "Documents"]


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
        self.candidate_country = os.getenv("CANDIDATE_COUNTRY", "").strip()
        self.candidate_cities = tuple(x.strip() for x in os.getenv("CANDIDATE_CITIES", "").split(",") if x.strip())


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
    except FeatureUnavailable as exc:
        c.log.exception("init_db failed")
        return f"Database could not be initialised: {exc}"
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

def _resume_name(r: dict) -> str:
    when = r.get("created_at")
    day = when.strftime("%d %b %Y") if hasattr(when, "strftime") else ""
    return f"{_file_name(r)}  ({r.get('skill_count', 0)} skills{', ' + day if day else ''})"


def _file_name(resume: dict) -> str:
    """The uploaded file's name without the random prefix added when it was stored."""
    name = Path(str(g(resume, "file_path", default="") or "resume")).name
    return re.sub(r"^[0-9a-f]{8}-", "", name)


def _on_resume_pick() -> None:
    try:
        st.session_state["resume"] = repo().get_resume(st.session_state["resume_picker"])
    except Exception:
        c.log.exception("get_resume failed")


def _pick_resume() -> None:
    """Which resume every tab works from. A dropdown once more than one is stored."""
    current = current_resume()
    if not current:
        st.caption("No resume yet. Upload one on the Resume tab.")
        return
    try:
        resumes = repo().list_resumes()
    except Exception:
        c.log.exception("list_resumes failed")
        resumes = []
    by_id = {r["id"]: r for r in resumes}
    if len(by_id) < 2 or g(current, "id") not in by_id:
        st.markdown(f"**{_file_name(current)}**")
        st.caption(f"{len(c.as_list(g(current, 'skills', default=[])))} skills found")
        return
    st.session_state["resume_picker"] = current["id"]  # the dropdown always shows the resume in use
    st.selectbox("Resume in use", list(by_id), format_func=lambda i: _resume_name(by_id[i]),
                 key="resume_picker", on_change=_on_resume_pick,
                 help="Matches, applications, skill suggestions and documents all use this resume.")


def render_sidebar(settings) -> None:
    with st.sidebar:
        st.header("Your resume")
        _pick_resume()

        st.divider()
        st.header("Language model")
        st.caption("Writes cover letters and resume suggestions.")
        use_ollama = bool(getattr(settings, "use_ollama", True))
        base = str(getattr(settings, "ollama_base_url", "http://localhost:11434"))
        models = c.ollama_models(base) if use_ollama else []
        if use_ollama:
            count = f"{len(models)} model{'s' if len(models) != 1 else ''} installed"
            c.status_row("Ollama", bool(models) or c.ollama_reachable(base), f"ready, {count}",
                         "not running. Start it with `ollama serve`")
        else:
            c.status_row("Ollama", False, "", "turned off (USE_OLLAMA=false)")
        has_key = bool(getattr(settings, "gemini_api_key", None))
        c.status_row("Gemini", has_key, "API key configured", "not set up (no GEMINI_API_KEY)")
        _pick_model(settings, models, has_key)

        st.divider()
        st.header("Storage")
        st.markdown(f"**Database:** `{c.db_location(str(settings.database_url))}`")
        st.markdown(f"**Documents:** `{getattr(settings, 'docs_dir', '~/jobhunt_docs')}`")
        st.caption("Everything runs on this machine. Your data only leaves it if you enable Gemini.")


GEMINI = "gemini"  # same value as generator.llm.GEMINI, kept here so the sidebar never imports it


def _pick_model(settings, models: list, has_key: bool) -> None:
    """Dropdown of the installed Ollama models (smallest first) plus Gemini when a key is set."""
    names = [m["name"] for m in models]
    options = names + ([GEMINI] if has_key else [])
    if not options:
        st.session_state.pop("llm_model", None)
        return
    configured = str(getattr(settings, "ollama_model", "") or "")
    default = next((n for n in names if c.same_model(n, configured)), names[0] if names else GEMINI)
    if st.session_state.get("llm_model") not in options:
        st.session_state["llm_model"] = default
    sizes = {m["name"]: m["size"] for m in models}
    st.selectbox(
        "Model for writing", options, key="llm_model",
        format_func=lambda n: "Gemini (online, sends your resume to Google)" if n == GEMINI
        else f"{n} ({sizes[n]})" if sizes.get(n) else n,
        help="Smaller models write faster on a laptop without a graphics card. The default comes "
             "from OLLAMA_MODEL in .env. Install more with `ollama pull <name>`.")


def _chosen_model() -> str | None:
    return st.session_state.get("llm_model")


# --------------------------------------------------------------------------- overview

def _matches(resume: dict | None, limit: int = 500) -> list[dict]:
    if not resume or g(resume, "id") is None:
        return []
    try:
        return repo().list_matches(resume["id"], limit=limit)
    except Exception:
        c.log.exception("list_matches failed")
        return []


def _score_of(m: dict) -> float:
    try:
        return float(g(m, "confidence_score", "total", default=0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _count(matches: list[dict], status: str) -> int:
    return sum(1 for m in matches if g(m, "status", default="new") == status)


def next_step(has_resume: bool, jobs: int, matches: list[dict]) -> str:
    """The one thing to do next, in the order resume, collect, score, shortlist, apply."""
    if not has_resume:
        return "Upload your resume on the **Resume** tab."
    if not jobs:
        return "Collect some postings on the **Find jobs** tab."
    if not matches:
        return "Open **Matches** and press **Score stored jobs** to rank the postings against your resume."
    saved, applied = _count(matches, "saved"), _count(matches, "applied")
    if saved:
        return (f"You have {saved} saved job{'s' if saved != 1 else ''}. Draft a cover letter on the "
                "**Documents** tab, then mark each one applied under **Applications**.")
    if applied:
        return "Save more jobs on the **Matches** tab and update the ones you hear back from."
    return "Read through **Matches** and press **Save** on the jobs worth applying to."


def render_overview(resume: dict | None) -> None:
    """Headline numbers for the search so far and the next step, above the tabs."""
    matches = _matches(resume)
    jobs = int(db_counts().get("Jobs", 0) or 0)
    if resume and (jobs or matches):
        strong = sum(1 for m in matches if _score_of(m) >= 50 and g(m, "status", default="new") != "hidden")
        cells = [(jobs, "jobs collected"), (len(matches), "scored for this resume"), (strong, "strong matches"),
                 (_count(matches, "saved"), "saved"), (_count(matches, "applied"), "applied")]
        st.markdown('<div class="jh-stat">' + "".join(f"<div><b>{n}</b><span>{label}</span></div>"
                                                      for n, label in cells) + "</div>", unsafe_allow_html=True)
    # The line sits inside a styled block, so its Markdown bold becomes <b> by hand.
    step = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", c.html.escape(next_step(bool(resume), jobs, matches)))
    st.markdown(f'<div class="jh-next"><b>Next step:</b> {step}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- tab 1

def tab_resume(settings) -> None:
    st.subheader("Your resume")
    has_resume = bool(current_resume())
    with st.container(border=True):
        c.panel_title("Upload a newer version" if has_resume else "Upload your resume")
        uploaded = st.file_uploader(
            "Resume file", type=[e.lstrip(".") for e in sorted(RESUME_EXTS)], key="resume_upload",
            help="LaTeX (.tex), plain text (.txt), Markdown (.md) or PDF, up to 2 MB. Uploading a new "
                 "version replaces the one in use, keeps the skills you added by hand and scores your "
                 "stored jobs against it.")
        if uploaded is not None:
            fingerprint = (uploaded.name, uploaded.size)
            if st.session_state.get("resume_fingerprint") != fingerprint:
                with friendly_errors("process the resume"), st.spinner("Reading your resume..."):
                    data = uploaded.getvalue()
                    max_bytes = int(getattr(settings, "upload_max_bytes", 2_000_000))
                    load("security.sanitize", "validate_upload")(uploaded.name, data, RESUME_EXTS, max_bytes)
                    parsed = load("parser.resume_parser", "parse_resume_bytes")(uploaded.name, data)
                    file_path = _store_upload(settings, uploaded.name, data)
                    # An updated resume is a new row: bring the hand-added skills along.
                    resume_id = repo().save_resume(parsed, file_path,
                                                   inherit_skills_from=g(current_resume() or {}, "id"))
                    resume = repo().get_resume(resume_id) or dict(parsed, id=resume_id)
                    st.session_state["resume"] = resume
                    st.session_state["resume_fingerprint"] = fingerprint
                    found = f"{len(c.as_list(g(resume, 'skills', default=[])))} skills found"
                    scored = _rescore_after_upload(resume, settings)
                    if scored:
                        st.session_state.pop("skills_changed", None)
                        tail = f"{scored} stored jobs were scored against it, so **Matches** is up to date."
                    elif scored is None:
                        st.session_state["skills_changed"] = True
                        tail = "Scoring the stored jobs failed. Press **Score stored jobs** on the Matches tab."
                    else:
                        tail = "Next, open **Find jobs** to collect postings."
                    st.session_state["resume_notice"] = (
                        f"Resume {'updated' if has_resume else 'saved'}: {found}. {tail}")
                    st.rerun()  # so the sidebar and the numbers above pick up the new resume
        notice = st.session_state.pop("resume_notice", None)
        if notice:
            st.success(notice)

    resume = current_resume()
    if not resume:
        c.empty_state("file", "No resume yet",
                      "Upload your resume above. It is read on this machine and never sent anywhere.")
        return
    _render_resume(resume)


def _home_country(settings) -> str:
    """The country picked on the Matches tab, or the configured one before it was opened."""
    picked = st.session_state.get("home_country")
    if picked is not None:
        return "" if picked == NO_COUNTRY else str(picked)
    try:
        return load("matching.location", "normalize_country")(str(getattr(settings, "candidate_country", "") or ""))
    except Exception:
        return ""


def _rescore_after_upload(resume: dict, settings) -> int | None:
    """Score every stored job against a newly uploaded resume. Returns how many were scored,
    0 when there are no jobs yet, or None when scoring failed (the upload itself is kept)."""
    if g(resume, "id") is None or not int(db_counts().get("Jobs", 0) or 0):
        return 0
    try:
        with st.status("Scoring your stored jobs against this resume...", expanded=True) as box:
            bar = st.progress(0.0, text="Reading stored jobs")
            n = _score_and_save(resume, _home_country(settings),
                                tuple(getattr(settings, "candidate_cities", ()) or ()),
                                step=lambda fraction, text: bar.progress(min(1.0, fraction), text=text))
            box.update(label=f"Scored {n} jobs", state="complete", expanded=False)
        return n
    except Exception:
        c.log.exception("scoring after upload failed")
        return None


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


def _save_extra_skills(resume: dict, skills: list[str]) -> list[str]:
    """Persist hand-added skills and refresh the resume held in this session."""
    saved = repo().set_extra_skills(resume["id"], skills)
    st.session_state["resume"] = repo().get_resume(resume["id"]) or resume
    st.session_state["skills_changed"] = True
    return saved


def add_skills(resume: dict, typed: str) -> list[str]:
    """Add comma-separated skills typed by the user; returns the ones that were new."""
    canonical = load("parser.skills_vocab", "canonicalize")
    have = {str(s).lower() for s in c.as_list(g(resume, "skills", default=[]))}
    extra = list(c.as_list(g(resume, "extra_skills", default=[])))
    added = []
    for part in str(typed or "").replace(";", ",").replace("\n", ",").split(","):
        name = " ".join(part.split())[:40]
        name = canonical(name) or name
        if name and name.lower() not in have:
            have.add(name.lower())
            extra.append(name)
            added.append(name)
    if added:
        _save_extra_skills(resume, extra)
    return added


def _skills_editor(resume: dict) -> None:
    extra = c.as_list(g(resume, "extra_skills", default=[]))
    extra_low = {str(s).lower() for s in extra}
    parsed = [s for s in c.as_list(g(resume, "skills", default=[])) if str(s).lower() not in extra_low]
    box = st.container(border=True)
    with box:
        c.panel_title(f"Skills ({len(parsed) + len(extra)})")
        c.chips(parsed)
        if extra:
            st.caption("Added by you")
            c.chips(extra, "ok")
        with st.form("add_skill_form", clear_on_submit=True):
            col_in, col_btn = st.columns([5, 1], vertical_alignment="bottom")
            typed = col_in.text_input("Add a skill", placeholder="e.g. Kafka, Hibernate, System Design",
                                      help="For skills your resume file doesn't mention. Separate several "
                                           "with commas. They count in matching and skill suggestions.")
            submitted = col_btn.form_submit_button("Add skill", type="primary", use_container_width=True)
    if submitted:
        with friendly_errors("add the skill"):
            added = add_skills(resume, typed)
            if added:
                st.session_state["skill_notice"] = f"Added: {', '.join(added)}."
                st.rerun()
            elif str(typed).strip():
                st.info("That skill is already on your list.")
            else:
                st.warning("Type a skill first.")
    if extra:
        with box:
            col_pick, col_rm = st.columns([5, 1], vertical_alignment="bottom")
            remove = col_pick.selectbox("Remove a skill you added", ["(choose one)"] + extra, key="remove_skill")
            if col_rm.button("Remove", disabled=remove == "(choose one)", use_container_width=True,
                             key="remove_skill_btn"):
                with friendly_errors("remove the skill"):
                    _save_extra_skills(resume, [s for s in extra if s != remove])
                    st.session_state["skill_notice"] = f"Removed: {remove}."
                    st.rerun()
    notice = st.session_state.pop("skill_notice", None)
    if notice:
        st.success(f"{notice} Open **Matches** and press **Score stored jobs** to update the scores.")


def _render_resume(resume: dict) -> None:
    skills = c.as_list(g(resume, "skills", "skills_json", default=[]))
    experience = c.as_list(g(resume, "experience", "experience_json", default=[]))
    education = g(resume, "education", default="") or ""
    summary = g(resume, "summary", default="") or ""

    name = _file_name(resume)
    st.markdown(f'<div class="jh-stat"><div><b>{len(skills)}</b><span>skills</span></div>'
                f'<div><b>{len(experience)}</b><span>experience entries</span></div>'
                f'<div><b>{c.html.escape(name[:40])}</b><span>file in use</span></div></div>',
                unsafe_allow_html=True)

    if summary:
        st.markdown("#### Summary")
        st.write(summary)
    if g(resume, "id") is not None:
        _skills_editor(resume)
    else:
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
            for line in ([education] if isinstance(education, str) else c.as_list(education)):
                st.write(line)
        else:
            st.caption("No education section detected.")
    raw = g(resume, "raw_text", default="")
    if raw:
        with st.expander("Text read from your file"):
            st.text(raw[:10000])


# --------------------------------------------------------------------------- tab 2

def tab_scrape(settings) -> None:
    st.subheader("Find jobs")
    with st.expander("How this app collects jobs politely"):
        st.markdown(c.ETHICAL_NOTE)
    cap = int(getattr(settings, "max_jobs_per_session", 50) or 50)
    with st.form("scrape_form"):
        col1, col2 = st.columns(2)
        keywords = col1.text_input("Job keywords", "Python Developer", key="scrape_keywords",
                                   placeholder="e.g. Java Developer, Backend Engineer")
        location = col2.text_input("Location", "Remote", key="scrape_location",
                                   placeholder="e.g. Remote, or Bangalore, India")
        max_jobs = st.slider("Max jobs to scrape", 5, max(5, min(50, cap)), min(20, cap), key="scrape_max")
        sources = st.multiselect(
            "Sources", options=list(c.SOURCES), default=c.DEFAULT_SOURCES, format_func=c.source_name,
            key="scrape_sources",
            help="RemoteOK, Hacker News, The Muse and Arbeitnow are free public APIs. Greenhouse and Lever "
                 "read the company boards named in .env. Indeed, LinkedIn and Naukri are experimental and "
                 "usually return nothing.")
        submitted = st.form_submit_button("Find jobs", type="primary")

    if any(s in sources for s in ("indeed", "linkedin", "naukri")):
        st.caption("Playwright sources run a headless browser slowly and politely; they "
                   "return nothing if Playwright isn't installed or robots.txt disallows them.")

    if submitted:
        if not keywords.strip():
            st.warning("Enter at least one keyword.")
        elif not sources:
            st.warning("Pick at least one source.")
        else:
            names = ", ".join(c.source_name(x) for x in sources)
            with friendly_errors("scrape jobs"):
                with st.status(f"Collecting jobs from {names}...", expanded=True) as box:
                    st.write("Requests are spaced out to be polite to each site, so this can take a minute.")
                    jobs = _scrape(keywords.strip(), location.strip(), int(max_jobs), list(sources))
                    new = repo().upsert_jobs(jobs) if jobs else 0
                    box.update(label=f"Collected {len(jobs)} jobs" if jobs else "No jobs found",
                               state="complete" if jobs else "error", expanded=False)
                if jobs:
                    per = {}
                    for job in jobs:
                        per[c.source_name(job.get("source"))] = per.get(c.source_name(job.get("source")), 0) + 1
                    split = ", ".join(f"{n} from {name}" for name, n in sorted(per.items(), key=lambda x: -x[1]))
                    st.success(f"Collected {len(jobs)} jobs ({split}); {new} are new. "
                               "Open **Matches** and press **Score stored jobs** to rank them.")
                else:
                    st.warning("No jobs found. Try broader keywords, a different location or another source.")

    with friendly_errors("list stored jobs"):
        jobs = repo().list_jobs(limit=50)
        if not jobs:
            c.empty_state("search", "No jobs collected yet",
                          "Enter keywords and a location above, then press Find jobs.")
        if jobs:
            st.markdown("#### Recently stored jobs")
            st.caption(f"The {len(jobs)} most recent. Scores and filters are on the **Matches** tab.")
            for job in jobs[:_page_size("stored_jobs")]:
                with st.container(border=True):
                    st.markdown(c.job_card_html(job, tags=_posting_skills(str(job.get("description") or "")),
                                                link=True), unsafe_allow_html=True)
            _show_more("stored_jobs", len(jobs))
            _housekeeping(resume=current_resume())


def _housekeeping(resume: dict | None) -> None:
    """Back up stored jobs and matches as CSV, and delete postings that are too old to apply to."""
    hk = load("db.housekeeping")
    notice = st.session_state.pop("stale_notice", None)
    if notice:
        st.success(notice)
    with st.expander("Back up or clean up stored jobs"):
        st.markdown("**Back up**")
        st.caption("Download your stored jobs and scores as spreadsheets (CSV). "
                   "`python scripts/housekeeping.py backup` also copies the whole database.")
        if st.button("Prepare CSV files", key="backup_prepare"):
            with friendly_errors("prepare the backup"):
                st.session_state["backup_files"] = (hk.jobs_csv(), hk.matches_csv(g(resume or {}, "id")))
        files = st.session_state.get("backup_files")
        if files:
            day = load("db.database", "utcnow")().strftime("%Y-%m-%d")
            left, right = st.columns(2)
            left.download_button("Download jobs.csv", files[0], file_name=f"jobhunt-jobs-{day}.csv",
                                 mime="text/csv", use_container_width=True, key="backup_jobs")
            right.download_button("Download matches.csv", files[1], file_name=f"jobhunt-matches-{day}.csv",
                                  mime="text/csv", use_container_width=True, key="backup_matches",
                                  help="Scores and statuses for the resume in use.")

        st.divider()
        st.markdown("**Clean up**")
        days = st.number_input("Delete jobs older than (days)", min_value=7, max_value=365,
                               value=hk.DEFAULT_STALE_DAYS, step=1, key="stale_days",
                               help="Age is counted from the posting date, or from when the job was "
                                    "collected if the posting has no date.")
        summary = hk.stale_summary(int(days))
        kept = (f" {summary['kept']} older jobs stay because you saved, applied to or wrote for them."
                if summary["kept"] else "")
        if not summary["stale"]:
            st.caption(f"No jobs are older than {int(days)} days.{kept}")
            return
        st.caption(f"{summary['stale']} jobs are older than {int(days)} days and would be deleted with "
                   f"their scores.{kept} This cannot be undone, so back up first if you may want them.")
        sure = st.checkbox(f"Yes, delete {summary['stale']} old jobs", key="stale_confirm")
        if st.button(f"Delete {summary['stale']} old jobs", disabled=not sure, key="stale_delete"):
            with friendly_errors("delete old jobs"):
                n = hk.delete_stale_jobs(int(days))
                st.session_state.pop("stale_confirm", None)
                st.session_state.pop("backup_files", None)
                st.session_state["stale_notice"] = f"Deleted {n} jobs older than {int(days)} days."
                st.rerun()


PAGE = 10


def _page_size(key: str) -> int:
    return int(st.session_state.get(f"page_{key}", PAGE))


def _show_more(key: str, total: int) -> None:
    """'Show more' button that reveals the next PAGE cards of a list."""
    shown = _page_size(key)
    if shown < total and st.button(f"Show {min(PAGE, total - shown)} more", key=f"more_{key}",
                                   use_container_width=True):
        st.session_state[f"page_{key}"] = shown + PAGE
        st.rerun()


@st.cache_data(show_spinner=False, max_entries=1024)
def _posting_skills(jd_text: str) -> list:
    return load("parser.skills_vocab", "find_skills")(jd_text)[:7]


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


def _score_and_save(resume: dict, country: str = "", cities: tuple = (), step=None) -> int:
    """Score every stored job and save the results. ``step(fraction, text)`` reports progress."""
    step = step or (lambda fraction, text: None)
    r = repo()
    jobs = r.list_jobs(limit=500)
    if not jobs:
        return 0
    step(0.05, "Loading the language model (the first run can take a minute)")
    try:
        embedding = load("matching.semantic_matcher", "get_model")() is not None
    except Exception:
        embedding = False
    how = "meaning and keywords" if embedding else "keywords (the MiniLM model is not available)"
    step(0.3, f"Comparing your resume with {len(jobs)} jobs by {how}")
    results = load("matching.confidence_score", "score_jobs")(resume, jobs, country=country, cities=cities)
    saved = 0
    total = max(1, len(results or []))
    for i, res in enumerate(results or []):
        if i % 10 == 0:
            step(0.75 + 0.25 * i / total, f"Saving scores ({i} of {total})")
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


# Location statuses a candidate cannot act on (see matching/location.py).
BLOCKED_LOCATIONS = ("restricted", "elsewhere")
NO_COUNTRY = "(ignore location)"
ALL = "All"
ANY_YEARS = 15  # top of the years slider: no limit
SORTS = ("Best match", "Fewest missing skills", "Newest posting", "Least experience asked")


def _annotate(matches: list[dict], resume: dict, country: str, cities: tuple) -> float:
    """Attach location fit, years asked and the skill gap to each match (cheap rules,
    recomputed on the fly so no database change is needed). Returns the candidate's years."""
    fit = load("matching.location", "location_fit")
    labels = load("matching.location", "LABELS")
    cs = load("matching.confidence_score")
    gaps = load("matching.skill_gap")
    have = gaps.candidate_skills(resume)
    for m in matches:
        try:
            loc = fit(m, country, cities) if country else None
            m["_loc_status"] = loc["status"] if loc else ""
            m["_loc_text"] = f"{labels[loc['status']]}: {loc['reason']}" if loc else ""
            m["_years"] = cs.required_years_for(m)
            m["_gap"] = _cached_gap(cs.job_text(m), tuple(sorted(have)))
            m["_near"] = gaps.is_near_miss(m["_gap"])
        except Exception:
            c.log.exception("match annotation failed")
            m.update(_loc_status="", _loc_text="", _years=None, _near=False,
                     _gap={"required": [], "matched": [], "missing": [], "nice_missing": []})
    try:
        return float(cs.estimate_candidate_years(c.as_list(g(resume, "experience", default=[]))))
    except Exception:
        return 0.0


@st.cache_data(show_spinner=False, max_entries=2048)
def _cached_gap(jd_text: str, have: tuple) -> dict:
    return load("matching.skill_gap", "skill_gap")({"description": jd_text}, have)


def _country_picker(settings) -> str:
    places = load("matching.location", "PLACES")
    normalize = load("matching.location", "normalize_country")
    configured = normalize(str(getattr(settings, "candidate_country", "") or ""))
    options = [NO_COUNTRY] + sorted(set(places) | ({configured} if configured else set()))
    chosen = st.selectbox(
        "Your country", options, index=options.index(configured) if configured else 0, key="home_country",
        help="Jobs restricted to other countries, time zones or languages are ranked down. "
             "Set CANDIDATE_COUNTRY in .env to change the default.")
    return "" if chosen == NO_COUNTRY else chosen


def _sorted(matches: list[dict], how: str) -> list[dict]:
    score = lambda m: -float(g(m, "confidence_score", "total", default=0) or 0)  # noqa: E731
    if how == "Fewest missing skills":
        # Jobs that name too few skills to judge go last.
        return sorted(matches, key=lambda m: (len(m["_gap"]["required"]) < 3, len(m["_gap"]["missing"]), score(m)))
    if how == "Newest posting":
        return sorted(matches, key=lambda m: (g(m, "posted_date") is None, -(g(m, "posted_date").timestamp()
                                              if g(m, "posted_date") is not None else 0), score(m)))
    if how == "Least experience asked":
        return sorted(matches, key=lambda m: (m["_years"] is None, m["_years"] or 0, score(m)))
    return sorted(matches, key=score)


def tab_matches(resume: dict | None, settings=None) -> None:
    st.subheader("Job matches")
    if not resume or g(resume, "id") is None:
        c.empty_state("file", "Add your resume first",
                      "Matches are scored against your resume. Upload it on the Resume tab.")
        return

    cities = tuple(getattr(settings, "candidate_cities", ()) or ())
    panel = st.container(border=True)
    with panel:
        c.panel_title("Where you can work")
        top = st.columns([3, 2], vertical_alignment="bottom")
        with top[0]:
            country = _country_picker(settings)
        rescore = top[1].button(
            "Score stored jobs", type="primary", use_container_width=True,
            help="Re-scores every stored job against your resume. Do this after finding jobs, "
                 "adding skills or changing your country.")
    if rescore:
        with friendly_errors("score jobs"):
            with st.status("Scoring jobs against your resume...", expanded=True) as box:
                bar = st.progress(0.0, text="Reading stored jobs")
                n = _score_and_save(resume, country, cities,
                                    step=lambda fraction, text: bar.progress(min(1.0, fraction), text=text))
                bar.progress(1.0, text="Done")
                box.update(label=f"Scored {n} jobs" if n else "No jobs to score",
                           state="complete" if n else "error", expanded=False)
            st.session_state.pop("skills_changed", None)
            if n:
                st.success(f"Scored {n} jobs against your resume. The best matches are listed first.")
            else:
                st.warning("No jobs to score yet. Collect some on the Find jobs tab first.")
    elif st.session_state.get("skills_changed"):
        st.warning("Your resume or skills changed. Press **Score stored jobs** to update the scores.")

    with friendly_errors("load matches"):
        matches = repo().list_matches(resume["id"], limit=500)
        if not matches:
            c.empty_state("search", "No matches yet",
                          "Collect jobs on the Find jobs tab, then press Score stored jobs above.")
            return
        my_years = _annotate(matches, resume, country, cities)

        # ---- filters: sliders and checkboxes as before, dropdowns for the new choices
        with panel:
            st.divider()
            c.panel_title("Filters")
            # Widget keys carry a counter so "Reset filters" can put every control back to its default.
            k = f"_{st.session_state.get('filter_reset', 0)}"
            s1, s2 = st.columns([5, 1], vertical_alignment="bottom")
            query = s1.text_input("Search", key=f"f_search{k}",
                                  placeholder="Title, company, location or skill, e.g. Spring Boot Bangalore",
                                  help="Every word you type must appear in the job's title, company, "
                                       "location or required skills.")
            s2.button("Reset filters", key="filter_reset_btn", use_container_width=True, on_click=_reset_filters)
            f = st.columns(2)
            min_score = f[0].slider("Minimum confidence", 0, 100, 0, step=5, key=f"f_min{k}",
                                    help="50 and above is a strong match, 35 to 49 a possible one.")
            default_years = min(ANY_YEARS, int(my_years + 0.999) + 2)
            max_years = f[1].slider("Asks for at most (years)", 0, ANY_YEARS, default_years,
                                    key=f"f_years{k}_{default_years}",
                                    help=f"Your resume shows about {my_years:g} years. "
                                         f"{ANY_YEARS} shows every level.")
            c1, c2 = st.columns(2)
            hide_blocked = c1.checkbox("Only jobs I can take", value=bool(country), disabled=not country,
                                       key=f"f_blocked{k}_{int(bool(country))}",
                                       help="Hides jobs on-site in another country or restricted to "
                                            "other countries, time zones or languages. Needs your country.")
            keep_unknown = c2.checkbox("Include jobs that state no years", value=True, key=f"f_unknown{k}")
            d = st.columns(3)
            sources = sorted({str(g(m, "source", default="") or "") for m in matches} - {""})
            source = d[0].selectbox("Source", [ALL] + sources, format_func=c.source_name, key=f"f_source{k}")
            status = d[1].selectbox("Status", [ALL] + c.MATCH_STATUSES, format_func=c.status_name,
                                    key=f"f_status{k}",
                                    help="All leaves out hidden jobs. Saved, applied and rejected jobs "
                                         "are also listed on the Applications tab.")
            sort_by = d[2].selectbox("Sort by", SORTS, key=f"f_sort{k}")

        words = str(query or "").lower().split()

        def keep(m: dict) -> bool:
            if _score_of(m) < min_score:
                return False
            if words:
                hay = " ".join([str(g(m, "title", default="")), str(g(m, "company", default="")),
                                str(g(m, "location", default="")), " ".join(m["_gap"]["required"])]).lower()
                if not all(w in hay for w in words):
                    return False
            if hide_blocked and m["_loc_status"] in BLOCKED_LOCATIONS:
                return False
            if source != ALL and g(m, "source") != source:
                return False
            current = g(m, "status", default="new")
            if (status != ALL and current != status) or (status == ALL and current == "hidden"):
                return False  # hidden jobs only appear when you pick Status: hidden
            if m["_years"] is None:
                return keep_unknown
            return max_years >= ANY_YEARS or m["_years"] <= max_years

        shown = _sorted([m for m in matches if keep(m)], sort_by)
        hidden = sum(1 for m in matches if g(m, "status", default="new") == "hidden")
        near_count = sum(1 for m in shown if m.get("_near"))
        parts = [f"<span><b>{len(shown)}</b> of {len(matches)} jobs</span>"]
        if country and hide_blocked:
            parts.append(f'<span class="pill">{c.html.escape(country)} or remote</span>')
        if max_years < ANY_YEARS:
            parts.append(f'<span class="pill">up to {max_years} years</span>')
        if words:
            parts.append(f'<span class="pill">matching "{c.html.escape(" ".join(words)[:40])}"</span>')
        if near_count:
            parts.append(f"<span>&middot; <b>{near_count}</b> within 3 skills of a full match</span>")
        if hidden:
            parts.append(f"<span>&middot; {hidden} hidden (Status: Hidden shows them)</span>")
        c.strip(parts)
        if not shown:
            c.empty_state("filter", "No jobs pass these filters",
                          "Clear the search, raise the years limit or lower the minimum confidence. "
                          "Reset filters puts everything back.")
            return
        _charts(shown)
        _job_cards(shown, resume)
        _skill_suggestions(shown, resume)


def _reset_filters() -> None:
    st.session_state["filter_reset"] = int(st.session_state.get("filter_reset", 0)) + 1
    st.session_state.pop("page_matches", None)


def _charts(shown: list[dict]) -> None:
    """Score spread, where the jobs came from and the skills they ask for, for the jobs shown."""
    with st.expander("Charts for the jobs shown: scores, sources and skills in demand"):
        try:
            bands = [("Strong (50+)", 50, 101), ("Possible (35 to 49)", 35, 50), ("Weak (under 35)", 0, 35)]
            scores = [(name, sum(1 for m in shown if lo <= _score_of(m) < hi)) for name, lo, hi in bands]
            per_source: dict = {}
            wanted: dict = {}
            have = set()
            for m in shown:
                name = c.source_name(g(m, "source", default="")) or "Unknown"
                per_source[name] = per_source.get(name, 0) + 1
                have.update(m["_gap"]["matched"])
                for skill in m["_gap"]["required"]:
                    wanted[skill] = wanted.get(skill, 0) + 1
            top = sorted(wanted.items(), key=lambda x: (-x[1], x[0]))[:8]
            skills = [(f"{name}{'' if name in have else ' (missing)'}", n) for name, n in top]
            left, mid, right = st.columns(3)
            with left:
                st.markdown("**Match strength**")
                st.markdown(c.count_bars_html(scores), unsafe_allow_html=True)
            with mid:
                st.markdown("**Where the jobs came from**")
                st.markdown(c.count_bars_html(sorted(per_source.items(), key=lambda x: -x[1])),
                            unsafe_allow_html=True)
            with right:
                st.markdown("**Skills asked for most**")
                if skills:
                    st.markdown(c.count_bars_html(skills, note="Skills marked (missing) are not on your resume."),
                                unsafe_allow_html=True)
                else:
                    st.caption("These postings name no skills the app recognises.")
        except Exception:
            c.log.exception("charts failed")
            st.caption("Charts are unavailable right now.")


def _skill_suggestions(shown: list[dict], resume: dict) -> None:
    """Jobs that are only 1-3 must-have skills short, and the skills that close most of them."""
    near = [m for m in shown if m.get("_near")]
    st.markdown("#### Skills worth adding")
    if not near:
        st.caption("None of the jobs shown is within 3 skills of a full match. "
                   "Raise the years limit or untick **Only jobs I can take**.")
        return
    near.sort(key=lambda m: (len(m["_gap"]["missing"]),
                             -float(g(m, "confidence_score", "total", default=0) or 0)))
    todo = load("matching.skill_gap", "skills_to_learn")([{"gap": m["_gap"]} for m in near])
    st.caption(f"{len(near)} of the jobs shown are only 1 to 3 skills short. "
               "These skills come up most in them:")
    c.chips([f"{t['skill']} ({t['jobs']} job{'s' if t['jobs'] != 1 else ''})" for t in todo], "miss")
    lines = []
    for m in near[:12]:
        gap = m["_gap"]
        lines.append(f"- **{g(m, 'title', default='Untitled role')}** at {g(m, 'company', default='?')}: "
                     f"add **{', '.join(gap['missing'])}** "
                     f"(you have {len(gap['matched'])} of {len(gap['required'])})")
    st.markdown("\n".join(lines))
    with st.form("have_skill_form", clear_on_submit=True):
        col_pick, col_btn = st.columns([4, 1], vertical_alignment="bottom")
        have_it = col_pick.selectbox("Already have one of these? Add it to your skills",
                                     ["(choose a skill)"] + [t["skill"] for t in todo])
        if col_btn.form_submit_button("Add skill", use_container_width=True) and have_it != "(choose a skill)":
            with friendly_errors("add the skill"):
                if add_skills(resume, have_it):
                    st.rerun()


def _job_cards(shown: list[dict], resume: dict) -> None:
    """One card per job: summary, Save / Hide / Open, and an expander with the details."""
    have = {str(x).lower() for x in load("matching.skill_gap", "candidate_skills")(resume)}
    resume_text = load("matching.confidence_score", "resume_text")(resume)
    for m in shown[:_page_size("matches")]:
        _match_card(m, resume_text, have)
    _show_more("matches", len(shown))


STATUS_TOASTS = {"saved": "Saved. It is now listed under Applications.", "hidden": "Hidden from your matches.",
                 "applied": "Marked as applied.", "rejected": "Marked as rejected.",
                 "new": "Moved back to new."}


def _set_status(match_id: int, status: str) -> None:
    """Button callback: store a match's status and keep its Status dropdown in step."""
    try:
        repo().update_match_status(match_id, status)
        st.session_state[f"status_{match_id}"] = status
        st.toast(STATUS_TOASTS.get(status, f"Marked as {status}."))
    except Exception:
        c.log.exception("update_match_status failed")
        st.toast("Could not update the status. Details are in the log.")


def _match_card(m: dict, resume_text: str, have: set) -> None:
    match_id = g(m, "id", "match_id")
    gap = m.get("_gap") or {"missing": [], "matched": [], "required": []}
    status = g(m, "status", default="new")
    near = ""
    if m.get("_near"):
        n = len(gap["missing"])
        near = f"Only {n} skill{'s' if n != 1 else ''} short of a full match: {', '.join(gap['missing'])}"
    blocked = m.get("_loc_status") in BLOCKED_LOCATIONS
    with st.container(border=True):
        st.markdown(c.job_card_html(
            m, score=g(m, "confidence_score", "total"), years=m.get("_years"),
            fit=m.get("_loc_text") or "", fit_ok=None if not m.get("_loc_status") else not blocked,
            matched=gap["matched"], missing=gap["missing"], near=near, status=status),
            unsafe_allow_html=True)
        if match_id is not None:
            b1, b2, b3, _ = st.columns([1, 1, 1.4, 3])
            saved = status == "saved"
            b1.button("Unsave" if saved else "Save", key=f"save_{match_id}", use_container_width=True,
                      on_click=_set_status, args=(match_id, "new" if saved else "saved"))
            hidden = status == "hidden"
            b2.button("Unhide" if hidden else "Hide", key=f"hide_{match_id}", use_container_width=True,
                      on_click=_set_status, args=(match_id, "new" if hidden else "hidden"))
            url = str(g(m, "url", default="") or "")
            if url.startswith(("https://", "http://")):
                b3.link_button("Open posting", url, use_container_width=True)
        with st.expander("Score breakdown, skills and full posting"):
            _match_detail(m, resume_text, have)


def _match_detail(m: dict, resume_text: str, have: set) -> None:
    match_id = g(m, "id", "match_id")
    st.markdown(c.score_bars_html(
        [("Skills and keywords", g(m, "ats_score", "ats")), ("Experience fit", g(m, "experience_score", "experience")),
         ("Meaning match", g(m, "semantic_score", "semantic")), ("Freshness", g(m, "freshness_score", "freshness"))],
        note="The match score is 35% skills and keywords, 30% experience fit, 25% meaning match and "
             "10% freshness, then lowered if the job is not open to your location."),
        unsafe_allow_html=True)
    jd = g(m, "description", default="") or ""
    if jd and resume_text:
        _requirements(m, match_id, have, jd)
        try:
            words = _gap(resume_text, jd)
            left, right = st.columns(2)
            with left:
                st.markdown("**Matched keywords**")
                c.chips(words.get("matched", []), "ok")
            with right:
                st.markdown("**Missing keywords**")
                c.chips(words.get("missing", []), "miss")
        except Exception:
            c.log.exception("keyword_gap failed")
            st.caption("Keyword analysis unavailable.")
    current = g(m, "status", default="new")
    if match_id is not None:
        st.selectbox("Status", c.MATCH_STATUSES, format_func=c.status_name,
                     index=c.MATCH_STATUSES.index(current) if current in c.MATCH_STATUSES else 0,
                     key=f"status_{match_id}", on_change=_on_status_change, args=(match_id,),
                     help="Track this application. Saved, applied and rejected jobs are listed "
                          "on the Applications tab.")
    # Expanders cannot be nested, so the posting text sits behind a checkbox.
    if jd and st.checkbox("Show the full job description", key=f"jd_{match_id}"):
        st.markdown(c.description_html(jd), unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=512)
def _rule_requirements(jd_text: str) -> dict:
    return load("generator.jd_insights", "split_requirements")(jd_text)


def _requirements(m: dict, match_id, have: set, jd: str) -> None:
    """Must-have vs nice-to-have skills: instant rule-based split, LLM on request."""
    key = f"req_llm_{match_id}"
    try:
        req = st.session_state.get(key) or _rule_requirements(jd)
    except Exception:
        c.log.exception("requirement split failed")
        return
    if not req.get("must_have") and not req.get("nice_to_have"):
        return
    left, right = st.columns(2)
    for col, title, field in ((left, "Must-have skills", "must_have"),
                              (right, "Nice-to-have skills", "nice_to_have")):
        with col:
            st.markdown(f"**{title}**")
            skills = req.get(field, [])
            for kind, group in (("ok", [s for s in skills if s.lower() in have]),
                                ("miss", [s for s in skills if s.lower() not in have])):
                if group:
                    c.chips(group, kind)
            if not skills:
                st.caption("None found.")
    source = "language model" if req.get("source") == "llm" else "keyword rules"
    st.caption(f"A tick means the skill is on your resume, a cross means it is missing. Split by {source}.")
    if match_id is not None and req.get("source") != "llm" and st.button(
            "Re-check with the language model", key=f"req_btn_{match_id}"):
        try:
            with st.spinner("Asking the language model... (local models can take a minute)"):
                st.session_state[key] = load("generator.jd_insights", "analyze_requirements_llm")(
                    {"title": g(m, "title"), "description": jd}, model=_chosen_model())
            st.rerun()
        except Exception as exc:
            if _is_llm_unavailable(exc):
                st.warning(c.LLM_HELP)
            else:
                c.log.exception("LLM requirement analysis failed")
                st.warning("The language model could not analyse this posting.")


def _on_status_change(match_id: int) -> None:
    new = st.session_state.get(f"status_{match_id}")
    try:
        repo().update_match_status(match_id, new)
        st.toast(STATUS_TOASTS.get(new, f"Status set to {new}."))
    except Exception:
        c.log.exception("update_match_status failed")
        st.toast("Could not update the status. Details are in the log.")


# --------------------------------------------------------------------------- tab 4: applications

TRACK_VIEWS = ["all"] + c.TRACKED_STATUSES
TRACK_HINTS = {"saved": "to apply to", "applied": "waiting to hear back", "rejected": "closed"}


def _on_track_change(match_id: int) -> None:
    new = st.session_state.get(f"track_{match_id}")
    _set_status(match_id, new)


def _write_for(match_id: int) -> None:
    st.session_state["doc_job_pending"] = match_id
    st.toast("Job selected. Open the Documents tab to write for it.")


def tab_tracker(resume: dict | None) -> None:
    st.subheader("Applications")
    st.caption("The jobs you saved, applied to or were turned down for, in one place.")
    if not resume or g(resume, "id") is None:
        c.empty_state("file", "Add your resume first",
                      "Applications are tracked per resume. Upload yours on the Resume tab.")
        return
    tracked = [m for m in _matches(resume) if g(m, "status", default="new") in c.TRACKED_STATUSES]
    if not tracked:
        c.empty_state("check", "No applications tracked yet",
                      "Press Save on a job in the Matches tab. It will appear here, where you can "
                      "mark it applied or rejected.")
        return
    counts = {status: _count(tracked, status) for status in c.TRACKED_STATUSES}
    st.markdown('<div class="jh-stat">' + "".join(
        f"<div><b>{counts[status]}</b><span>{c.status_name(status).lower()}, {TRACK_HINTS[status]}</span></div>"
        for status in c.TRACKED_STATUSES) + "</div>", unsafe_allow_html=True)
    view = st.radio("Show", TRACK_VIEWS, horizontal=True, key="track_view",
                    format_func=lambda v: f"All ({len(tracked)})" if v == "all"
                    else f"{c.status_name(v)} ({counts[v]})")
    rows = [m for m in tracked if view == "all" or g(m, "status") == view]
    if not rows:
        c.empty_state("filter", f"Nothing marked {c.status_name(view).lower()} yet",
                      "Pick All to see every tracked job, or change a job's status below.")
        return
    order = {status: i for i, status in enumerate(c.TRACKED_STATUSES)}
    rows.sort(key=lambda m: (order.get(g(m, "status"), 9), -_score_of(m)))
    for m in rows:
        match_id = g(m, "id", "match_id")
        title = str(g(m, "title", default="Untitled role"))
        with st.container(border=True):
            info, state, actions = st.columns([5, 2, 2], vertical_alignment="center")
            details = [str(g(m, "company", default="Unknown company")), str(g(m, "location", default="") or ""),
                       f"score {c.fmt_score(_score_of(m))} ({c.score_label(_score_of(m)).lower()})",
                       c.time_ago(g(m, "posted_date")), c.source_name(g(m, "source", default=""))]
            info.markdown(f"**{_md(title)}**  \n{_md(' · '.join(d for d in details if d))}")
            st.session_state[f"track_{match_id}"] = g(m, "status")
            state.selectbox(f"Status of {title}", c.TRACKED_STATUSES + ["new", "hidden"],
                            format_func=lambda v: "Not tracked (back to new)" if v == "new" else c.status_name(v),
                            key=f"track_{match_id}", on_change=_on_track_change, args=(match_id,),
                            label_visibility="collapsed")
            actions.button("Write documents", key=f"write_{match_id}", use_container_width=True,
                           on_click=_write_for, args=(match_id,),
                           help="Selects this job on the Documents tab.")
            url = str(g(m, "url", default="") or "")
            if url.startswith(("https://", "http://")):
                actions.link_button("Open posting", url, use_container_width=True)


def _md(text: str) -> str:
    """Posting text for a Markdown line: no HTML, no accidental formatting."""
    return re.sub(r"([\\`*_{}\[\]<>#|~$])", r"\\\1", " ".join(str(text).split()))


# --------------------------------------------------------------------------- tab 5: documents

DOC_TYPES = {"cover_letter": "Cover letter", "resume_suggestions": "Resume suggestions"}


def _llm_note(settings) -> tuple[bool, str]:
    """Whether a language model is ready, and one line saying which one will write."""
    chosen = _chosen_model()
    if chosen == GEMINI:
        return True, "Written by Gemini. Your resume and the posting are sent to Google for this."
    if chosen:
        return True, (f"Written by {chosen} on this machine (change it in the sidebar). "
                      "Without a graphics card this can take a few minutes.")
    if settings is not None and bool(getattr(settings, "use_ollama", True)) and c.ollama_reachable(
            str(getattr(settings, "ollama_base_url", "http://localhost:11434"))):
        return True, f"Written by Ollama ({getattr(settings, 'ollama_model', 'mistral')}) on this machine."
    if settings is not None and getattr(settings, "gemini_api_key", None):
        return True, "Written by Gemini. Your resume and the posting are sent to Google for this."
    return False, "No language model is ready, so Generate cannot write yet. The sidebar shows what is missing."


def _export_buttons(content: str, stem: str, title: str, key: str) -> None:
    """Download the draft as text, Word or PDF."""
    export = load("ui.export")
    cols = st.columns(3)
    cols[0].download_button("Download .txt", content, file_name=f"{stem}.txt", mime="text/plain",
                            use_container_width=True, key=f"txt_{key}")
    for col, kind, build, mime in (
            (cols[1], "docx", export.to_docx,
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            (cols[2], "pdf", export.to_pdf, "application/pdf")):
        try:
            data = build(content, title)
        except export.ExportUnavailable as exc:
            col.button(f"Download .{kind}", disabled=True, use_container_width=True, key=f"{kind}_{key}",
                       help=str(exc))
        except Exception:
            c.log.exception("export to %s failed", kind)
            col.button(f"Download .{kind}", disabled=True, use_container_width=True, key=f"{kind}_{key}",
                       help=f"This draft could not be turned into a .{kind} file. Details are in the log.")
        else:
            col.download_button(f"Download .{kind}", data, file_name=f"{stem}.{kind}", mime=mime,
                                use_container_width=True, key=f"{kind}_{key}")


def tab_generate(resume: dict | None, settings=None) -> None:
    st.subheader("Tailored documents")
    st.caption("Draft a cover letter or resume suggestions for one job, edit the draft, then download it.")
    if not resume or g(resume, "id") is None:
        c.empty_state("file", "Add your resume first",
                      "Cover letters and resume suggestions are written from your resume.")
        return
    matches = _matches(resume, limit=100)
    if not matches:
        c.empty_state("search", "No matches to write for yet",
                      "Score some jobs on the Matches tab, then come back to draft a cover letter.")
        return

    # Jobs you are tracking come first, then the rest by score.
    rank = {"saved": 0, "applied": 1}
    matches.sort(key=lambda m: (rank.get(g(m, "status", default="new"), 2), -_score_of(m)))
    by_id = {g(m, "id", "match_id"): m for m in matches}
    if st.session_state.get("doc_job") not in by_id:
        st.session_state.pop("doc_job", None)
    pending = st.session_state.pop("doc_job_pending", None)
    if pending in by_id:
        st.session_state["doc_job"] = pending
    match_id = st.selectbox("Job", list(by_id), format_func=lambda i: c.match_label(by_id[i]), key="doc_job",
                            help="Saved and applied jobs are listed first, then the rest by match score. "
                                 "Type to search.")
    match = by_id[match_id]
    facts = [str(g(match, "location", default="") or ""),
             f"score {c.fmt_score(_score_of(match))} ({c.score_label(_score_of(match)).lower()})",
             c.time_ago(g(match, "posted_date")), c.source_name(g(match, "source", default=""))]
    st.caption(" · ".join(x for x in facts if x))
    doc_type = st.radio("Document", list(DOC_TYPES), format_func=DOC_TYPES.get, horizontal=True, key="doc_type")
    draft_key = f"draft_{match_id}_{doc_type}"

    ready, note = _llm_note(settings)
    go, about = st.columns([1, 4], vertical_alignment="center")
    generate = go.button("Generate", type="primary", use_container_width=True, key="doc_generate",
                         help="Writes a new draft. An existing draft for this job is replaced.")
    about.caption(note)
    if generate:
        job = _job_for(match)
        try:
            with st.spinner(f"Writing the {DOC_TYPES[doc_type].lower()}... (on a laptop this can take a few minutes)"):
                if doc_type == "cover_letter":
                    text = load("generator.cover_letter", "generate_cover_letter")(resume, job, model=_chosen_model())
                else:
                    text = load("generator.resume_optimizer", "suggest_resume_edits")(resume, job, model=_chosen_model())
            st.session_state[draft_key] = text or ""
            if text:
                st.toast("Draft ready. Edit it below, then download or save it.")
            else:
                st.warning("The language model returned an empty draft. Press Generate to try again.")
        except Exception as exc:
            if _is_llm_unavailable(exc):
                st.warning(c.LLM_HELP)
            else:
                with friendly_errors("generate the document"):
                    raise exc

    if draft_key in st.session_state:
        content = st.text_area("Edit before saving", key=draft_key, height=380)
        st.caption(f"{len(content.split())} words. Changes you type here go into the files below.")
        _draft_check(content, resume, match)
        safe_company = "".join(ch for ch in str(g(match, "company", default="job")) if ch.isalnum())[:40] or "job"
        title = f"{DOC_TYPES[doc_type]}: {g(match, 'title', default='')} at {g(match, 'company', default='')}"
        _export_buttons(content, f"{doc_type}_{safe_company}", title, "draft")
        if st.button("Save to documents", use_container_width=True, key="doc_save",
                     help="Keeps a copy in your documents folder and lists it under this job."):
            with friendly_errors("save the document"):
                path = load("generator.documents", "save_generated_doc")(match_id, doc_type, content)
                st.success(f"Saved to `{path}`. It is also listed below.")
    elif ready:
        st.caption("No draft for this job yet. Press Generate to write one.")

    with friendly_errors("list saved documents"):
        docs = repo().list_documents(match_id)
        if docs:
            with st.expander(f"Saved documents for this job ({len(docs)})"):
                for d in docs:
                    when = d.get("generated_at")
                    day = when.strftime("%d %b %Y, %H:%M") if hasattr(when, "strftime") else ""
                    name, get = st.columns([3, 1], vertical_alignment="center")
                    name.markdown(f"**{DOC_TYPES.get(d.get('doc_type'), d.get('doc_type'))}**  \n"
                                  f"<span class='jh-muted'>{day}</span>", unsafe_allow_html=True)
                    get.download_button("Download .txt", str(d.get("content") or ""),
                                        file_name=f"{d.get('doc_type')}_{d.get('id')}.txt", mime="text/plain",
                                        key=f"saved_doc_{d.get('id')}", use_container_width=True)


def _draft_check(content: str, resume: dict, match: dict) -> None:
    """Point at sentences that claim more than the resume shows (models embellish)."""
    try:
        flags = load("generator.fact_check", "check_draft")(content, resume, _job_for(match))
    except Exception:
        c.log.exception("draft check failed")
        return
    if not flags:
        st.caption("No claims found that go beyond your resume. Still read it once before you send it.")
        return
    lines = "\n".join(f"- *{c.html.escape(f['sentence'][:160])}*  \n  {f['why']}" for f in flags)
    st.warning(f"**Check {len(flags)} sentence{'s' if len(flags) != 1 else ''} before you send this.** "
               f"They may claim more than your resume shows:\n\n{lines}")


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

    st.title("JobHunt AI")
    st.caption("Find the jobs you can actually get, track your applications and write for each one. "
               "Everything stays on your own machine.")
    if problem.startswith("Database"):
        st.error(problem)
    render_sidebar(settings)
    overview = st.container()  # filled last, so it reflects what the tabs changed in this run

    t1, t2, t3, t4, t5 = st.tabs(TABS)
    with t1:
        with friendly_errors("show the resume tab"):
            tab_resume(settings)
    resume = current_resume()
    with t2:
        with friendly_errors("show the scrape tab"):
            tab_scrape(settings)
    with t3:
        with friendly_errors("show the matches tab"):
            tab_matches(resume, settings)
    with t4:
        with friendly_errors("show the applications tab"):
            tab_tracker(resume)
    with t5:
        with friendly_errors("show the documents tab"):
            tab_generate(resume, settings)
    with overview:
        with friendly_errors("show the overview"):
            render_overview(resume)


main()
