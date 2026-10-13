"""Find jobs screen: search the sources, paste a posting, back up and clean up."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from api import catalog
from api.core import FeatureUnavailable, clamp, jsonable, load, log, repo, setting
from api.matching_view import home_cities, home_country, posting_skills, score_and_save

router = APIRouter()


class SearchIn(BaseModel):
    keywords: str
    location: str = ""
    max_jobs: int = 20
    sources: list[str] = Field(default_factory=list)
    resume_id: int | None = None
    country: str | None = None


class ManualIn(BaseModel):
    text: str
    url: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    resume_id: int | None = None


@router.get("/jobs")
def list_jobs(limit: int = 50) -> dict:
    """The most recently stored postings, with the skills each one names."""
    try:
        jobs = repo().list_jobs(limit=clamp(limit, 1, 500, 50))
    except Exception:
        log.exception("list_jobs failed")
        raise HTTPException(status_code=500, detail="The stored jobs could not be read.") from None
    return {"jobs": [_public_job(j) for j in jobs]}


@router.post("/jobs/search")
def search_jobs(body: SearchIn) -> dict:
    """Run a search, store what came back, then score the stored jobs."""
    keywords = body.keywords.strip()
    if not keywords:
        raise HTTPException(status_code=400, detail="Enter at least one keyword.")
    sources = [s for s in body.sources if s in catalog.SOURCES]
    if not sources:
        raise HTTPException(status_code=400, detail="Pick at least one source.")
    cap = int(setting("max_jobs_per_session", 50) or 50)
    try:
        jobs = _scrape(keywords, body.location.strip(), clamp(body.max_jobs, 1, cap, 20), sources)
    except FeatureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("scraping failed")
        raise HTTPException(status_code=502,
                            detail=f"The search could not finish ({type(exc).__name__}).") from exc
    new = repo().upsert_jobs(jobs) if jobs else 0
    per_source: dict = {}
    for job in jobs:
        name = catalog.source_name(job.get("source"))
        per_source[name] = per_source.get(name, 0) + 1
    return {
        "found": len(jobs),
        "new": new,
        "per_source": [{"name": n, "count": v} for n, v in sorted(per_source.items(), key=lambda x: -x[1])],
        "waiting": _waiting(sources),
        **_score_after(body.resume_id, body.country),
    }


@router.post("/jobs/manual")
def add_manual_job(body: ManualIn) -> dict:
    """Store a posting the user pasted in. The app never opens a link given here."""
    if not body.text.strip():
        raise HTTPException(status_code=400,
                            detail="Paste the posting first: the description is what your resume is scored against.")
    try:
        manual = load("scraper.manual_job")
    except FeatureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        job = manual.manual_job(body.text, body.url, body.title, body.company, body.location)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    new = repo().upsert_jobs([job])
    out = {"job": _public_job(job), "new": bool(new)}
    if new:
        out.update(_score_after(body.resume_id, None))
    return out


@router.get("/jobs/linkedin-search-url")
def linkedin_search_url(keywords: str = "", location: str = "") -> dict:
    """The LinkedIn search page for these keywords, for the user to open themselves."""
    try:
        return {"url": load("scraper.manual_job", "linkedin_search_url")(keywords.strip(), location.strip())}
    except FeatureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs/refresh-state")
def refresh_state() -> dict:
    """When LinkedIn and Naukri may next be searched, for the auto-refresh line."""
    try:
        js = load("scraper.jobspy_source")
    except FeatureUnavailable:
        return {"sites": [], "minutes": int(setting("jobspy_refresh_minutes", 60) or 60)}
    sites = []
    for site in js.enabled_sites():
        sites.append({"key": site, "name": catalog.source_name(site),
                      "wait_seconds": max(0.0, float(js.wait_seconds(site))),
                      "last_run": js.last_run(site)})
    return {"sites": sites, "minutes": int(setting("jobspy_refresh_minutes", 60) or 60)}


@router.post("/jobs/refresh")
def refresh_opt_in_sites(resume_id: int | None = None) -> dict:
    """Search the opt-in sites whose wait is over, with the last keywords and location."""
    try:
        js = load("scraper.jobspy_source")
    except FeatureUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    due = [s for s in js.enabled_sites() if js.wait_seconds(s) <= 0]
    if not due:
        return {"searched": [], "new": 0}
    keywords = str(_last_search().get("keywords") or "").strip()
    if not keywords:
        return {"searched": [], "new": 0}
    location = str(_last_search().get("location") or "").strip()
    cap = int(setting("jobspy_results_per_site", 15) or 15)
    jobs = load("scraper.service", "dedupe_jobs")(
        [j for site in due for j in js.fetch_jobspy(site, keywords, location, cap)])
    new = repo().upsert_jobs(jobs) if jobs else 0
    out = {"searched": [catalog.source_name(s) for s in due], "new": new}
    if new:
        out.update(_score_after(resume_id, None))
    return out


@router.get("/housekeeping/stale")
def stale(days: int = 30) -> dict:
    """How many postings are too old to apply to, and how many are kept because they are tracked."""
    hk = load("db.housekeeping")
    summary = hk.stale_summary(clamp(days, hk.MIN_STALE_DAYS, 365, hk.DEFAULT_STALE_DAYS))
    return {"days": days, "stale": int(summary["stale"]), "kept": int(summary["kept"]),
            "default_days": hk.DEFAULT_STALE_DAYS}


@router.delete("/housekeeping/stale")
def delete_stale(days: int = 30) -> dict:
    hk = load("db.housekeeping")
    deleted = hk.delete_stale_jobs(clamp(days, hk.MIN_STALE_DAYS, 365, hk.DEFAULT_STALE_DAYS))
    return {"deleted": int(deleted)}


@router.get("/housekeeping/backup/{kind}")
def backup_csv(kind: str, resume_id: int | None = None) -> Response:
    """The stored jobs or the scores for one resume as a CSV download."""
    hk = load("db.housekeeping")
    if kind == "jobs":
        body = hk.jobs_csv()
    elif kind == "matches":
        body = hk.matches_csv(resume_id)
    else:
        raise HTTPException(status_code=404, detail="Unknown backup.")
    day = load("db.database", "utcnow")().strftime("%Y-%m-%d")
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="jobhunt-{kind}-{day}.csv"'})


_LAST_SEARCH: dict = {}


def _last_search() -> dict:
    return _LAST_SEARCH


def _scrape(keywords: str, location: str, max_jobs: int, sources: list) -> list:
    _LAST_SEARCH.update(keywords=keywords, location=location)
    try:
        fn = load("scraper.service", "scrape_jobs")
    except FeatureUnavailable:
        fn = load("scraper", "scrape_jobs")
    return list(fn(keywords, location, max_jobs, sources) or [])


def _waiting(sources: list) -> list:
    """Opt-in sites still inside their wait, so the screen can say when they are next due."""
    try:
        js = load("scraper.jobspy_source")
    except FeatureUnavailable:
        return []
    out = []
    for site in sources:
        if site not in catalog.OPT_IN_SOURCES:
            continue
        wait = js.wait_seconds(site)
        if wait > 0:
            out.append({"name": catalog.source_name(site), "minutes": max(1, round(wait / 60))})
    return out


def _score_after(resume_id, country) -> dict:
    """Score the stored jobs after a search, the way the Streamlit app does."""
    try:
        resume = repo().get_resume(resume_id) if resume_id else repo().latest_resume()
    except Exception:
        log.exception("reading the resume failed")
        resume = None
    if not resume or resume.get("id") is None:
        return {"scored": 0, "score_error": ""}
    try:
        return {"scored": score_and_save(resume, home_country(country), home_cities()), "score_error": ""}
    except Exception as exc:
        log.exception("scoring after a search failed")
        return {"scored": 0,
                "score_error": f"The jobs were stored but not scored ({type(exc).__name__}). "
                               "Press Score stored jobs on the Matches tab."}


def _public_job(job: dict) -> dict:
    description = str(job.get("description") or "")
    return {
        "id": job.get("id"),
        "title": job.get("title") or "Untitled role",
        "company": job.get("company") or "Unknown company",
        "location": job.get("location") or "",
        "url": job.get("url") or "",
        "source": job.get("source") or "",
        "source_name": catalog.source_name(job.get("source")),
        "posted_date": jsonable(job.get("posted_date")),
        "experience_years": job.get("experience_years"),
        "skills": list(posting_skills(description)) if description else [],
        "snippet": _snippet(description),
    }


def _snippet(text: str, limit: int = 220) -> str:
    """First sentences of a posting on one line, without the Markdown marks many carry."""
    s = re.sub(r"\*\*|__|`|#{1,6}\s*", "", str(text or ""))
    s = " ".join(s.split())
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "..."
