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

import streamlit as st  # noqa: E402

from ui import components as c  # noqa: E402
from ui.components import FeatureUnavailable, friendly_errors, g, load  # noqa: E402

RESUME_EXTS = {".tex", ".txt", ".md", ".pdf"}
TABS = ["Resume", "Find jobs", "Matches", "Documents"]


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

def _resume_name(r: dict) -> str:
    name = Path(str(r.get("file_path") or "resume")).name
    when = r.get("created_at")
    day = when.strftime("%d %b %Y") if hasattr(when, "strftime") else ""
    return f"{name}  ({r.get('skill_count', 0)} skills{', ' + day if day else ''})"


def _pick_resume() -> None:
    """Dropdown to switch between stored resumes (shown once there is more than one)."""
    try:
        resumes = repo().list_resumes()
    except Exception:
        c.log.exception("list_resumes failed")
        return
    if len(resumes) < 2:
        return
    by_id = {r["id"]: r for r in resumes}
    current = g(current_resume() or {}, "id")
    ids = list(by_id)
    chosen = st.selectbox("Resume in use", ids, index=ids.index(current) if current in ids else 0,
                          format_func=lambda i: _resume_name(by_id[i]), key="resume_picker",
                          help="Matches, skill suggestions and documents use this resume.")
    if chosen != current:
        st.session_state["resume"] = repo().get_resume(chosen)
        st.rerun()


def tab_resume(settings) -> None:
    st.subheader("Your resume")
    has_resume = bool(current_resume())
    with st.container(border=True):
        c.panel_title("Update your resume" if has_resume else "Upload your resume")
        _pick_resume()
        uploaded = st.file_uploader(
            "Resume file", type=[e.lstrip(".") for e in sorted(RESUME_EXTS)], key="resume_upload",
            help="LaTeX (.tex), plain text (.txt), Markdown (.md) or PDF, up to 2 MB. Uploading a new "
                 "version replaces the one in use and keeps the skills you added by hand.")
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
                    st.session_state["skills_changed"] = True
                    st.success(f"Resume {'updated' if has_resume else 'saved'}: "
                               f"{len(c.as_list(g(resume, 'skills', default=[])))} skills found. "
                               "Next, open **Find jobs**, then score them under **Matches**.")

    resume = current_resume()
    if not resume:
        c.empty_state("file", "No resume yet",
                      "Upload your resume above. It is read on this machine and never sent anywhere.")
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
            col_in, col_btn = st.columns([5, 1])
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
            col_pick, col_rm = st.columns([5, 1])
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

    name = Path(str(g(resume, "file_path", default="") or "resume")).name
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
            st.write(education if isinstance(education, str) else c.as_list(education))
        else:
            st.caption("No education section detected.")
    raw = g(resume, "raw_text", default="")
    if raw:
        with st.expander("Raw extracted text"):
            st.text(raw[:10000])


# --------------------------------------------------------------------------- tab 2

def tab_scrape(settings) -> None:
    st.subheader("Find jobs")
    with st.expander("How this app collects jobs politely"):
        st.markdown(c.ETHICAL_NOTE)
    cap = int(getattr(settings, "max_jobs_per_session", 50) or 50)
    with st.form("scrape_form"):
        col1, col2 = st.columns(2)
        keywords = col1.text_input("Job keywords", "Python Developer")
        location = col2.text_input("Location", "Remote")
        max_jobs = st.slider("Max jobs to scrape", 5, max(5, min(50, cap)), min(20, cap))
        sources = st.multiselect("Sources", options=list(c.SOURCES), default=c.DEFAULT_SOURCES,
                                 format_func=lambda s: c.SOURCES[s])
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
            with friendly_errors("scrape jobs"), st.spinner("Scraping... (being polite, this can take a while)"):
                jobs = _scrape(keywords.strip(), location.strip(), int(max_jobs), list(sources))
                new = repo().upsert_jobs(jobs) if jobs else 0
                if jobs:
                    st.success(f"Fetched {len(jobs)} jobs, {new} new. Check the **Matches** tab.")
                else:
                    st.warning("No jobs found. Try broader keywords or another source.")

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


def _score_and_save(resume: dict, country: str = "", cities: tuple = ()) -> int:
    r = repo()
    jobs = r.list_jobs(limit=500)
    if not jobs:
        return 0
    results = load("matching.confidence_score", "score_jobs")(resume, jobs, country=country, cities=cities)
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
        top = st.columns([3, 2])
        with top[0]:
            country = _country_picker(settings)
        rescore = top[1].button(
            "Score stored jobs", type="primary", use_container_width=True,
            help="Re-scores every stored job against your resume. Do this after finding jobs, "
                 "adding skills or changing your country.")
    if rescore:
        with friendly_errors("score jobs"), st.spinner("Scoring jobs against your resume..."):
            n = _score_and_save(resume, country, cities)
            st.session_state.pop("skills_changed", None)
            if n:
                st.success(f"Scored {n} jobs.")
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
            f = st.columns(2)
            min_score = f[0].slider("Minimum confidence", 0, 100, 0, step=5)
            default_years = min(ANY_YEARS, int(my_years + 0.999) + 2)
            max_years = f[1].slider("Asks for at most (years)", 0, ANY_YEARS, default_years,
                                    help=f"Your resume shows about {my_years:g} years. "
                                         f"{ANY_YEARS} shows every level.")
            c1, c2 = st.columns(2)
            hide_blocked = c1.checkbox("Only jobs I can take", value=bool(country), disabled=not country,
                                       help="Hides jobs on-site in another country or restricted to "
                                            "other countries, time zones or languages. Needs your country.")
            keep_unknown = c2.checkbox("Include jobs that state no years", value=True)
            d = st.columns(3)
            sources = sorted({str(g(m, "source", default="") or "") for m in matches} - {""})
            source = d[0].selectbox("Source", [ALL] + sources,
                                    format_func=lambda s: c.SOURCES.get(s, s).split(" (")[0])
            status = d[1].selectbox("Status", [ALL] + c.MATCH_STATUSES,
                                    help="Use this as your application tracker.")
            sort_by = d[2].selectbox("Sort by", SORTS)

        def keep(m: dict) -> bool:
            if float(g(m, "confidence_score", "total", default=0) or 0) < min_score:
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
        if near_count:
            parts.append(f"<span>&middot; <b>{near_count}</b> within 3 skills of a full match</span>")
        if hidden:
            parts.append(f"<span>&middot; {hidden} hidden (Status: hidden shows them)</span>")
        c.strip(parts)
        if not shown:
            c.empty_state("filter", "No jobs pass these filters",
                          "Raise the years limit, lower the minimum confidence or untick a filter.")
            return
        _job_cards(shown, resume)
        _skill_suggestions(shown, resume)


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
        col_pick, col_btn = st.columns([4, 1])
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


def _set_status(match_id: int, status: str) -> None:
    """Button callback: store a match's status and keep its Status dropdown in step."""
    try:
        repo().update_match_status(match_id, status)
        st.session_state[f"status_{match_id}"] = status
        st.toast(f"Marked as {status}.")
    except Exception:
        c.log.exception("update_match_status failed")
        st.toast("Could not update status.")


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
        note="Weighted 35 / 30 / 25 / 10, then scaled down if you cannot take the job where it is."),
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
        st.selectbox("Status", c.MATCH_STATUSES,
                     index=c.MATCH_STATUSES.index(current) if current in c.MATCH_STATUSES else 0,
                     key=f"status_{match_id}", on_change=_on_status_change, args=(match_id,))
    # Expanders cannot be nested, so the posting text sits behind a checkbox.
    if jd and st.checkbox("Show the full job description", key=f"jd_{match_id}"):
        st.text(jd[:12000])


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
    st.caption(f"Green = on your resume, red = missing. Split by {source}.")
    if match_id is not None and req.get("source") != "llm" and st.button(
            "Re-check with the language model", key=f"req_btn_{match_id}"):
        try:
            with st.spinner("Asking the language model... (local models can take a minute)"):
                st.session_state[key] = load("generator.jd_insights", "analyze_requirements_llm")(
                    {"title": g(m, "title"), "description": jd})
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
        st.toast(f"Status set to {new}.")
    except Exception:
        c.log.exception("update_match_status failed")
        st.toast("Could not update status.")


# --------------------------------------------------------------------------- tab 4

DOC_TYPES = {"cover_letter": "Cover letter", "resume_suggestions": "Resume suggestions"}


def tab_generate(resume: dict | None) -> None:
    st.subheader("Tailored documents")
    if not resume or g(resume, "id") is None:
        c.empty_state("file", "Add your resume first",
                      "Cover letters and resume suggestions are written from your resume.")
        return
    try:
        matches = repo().list_matches(resume["id"], limit=100)
    except Exception:
        c.log.exception("list_matches failed")
        matches = []
    if not matches:
        c.empty_state("search", "No matches to write for yet",
                      "Score some jobs on the Matches tab, then come back to draft a cover letter.")
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

    st.title("JobHunt AI")
    st.caption("Find jobs you can actually get: your resume, polite job collection, ranked matches "
               "and tailored documents, all on your own machine.")
    if problem.startswith("Database"):
        st.error(problem)
    render_sidebar(settings)

    t1, t2, t3, t4 = st.tabs(TABS)
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
        with friendly_errors("show the documents tab"):
            tab_generate(resume)


main()
