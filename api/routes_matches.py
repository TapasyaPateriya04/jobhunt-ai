"""Matches and Applications screens: ranked jobs, their breakdown, their status."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import catalog
from api.core import clamp, jsonable, llm_error, load, log, repo
from api.matching_view import (annotate, candidate_years, detail, home_cities, home_country,
                               rescore_if_formula_changed, skills_to_learn)

router = APIRouter()


class StatusIn(BaseModel):
    status: str


@router.get("/matches")
def list_matches(resume_id: int, country: str | None = None, limit: int = 500) -> dict:
    """Every scored job for a resume, annotated with location fit, years and the skill gap."""
    resume = repo().get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="That resume is not stored any more.")
    place = home_country(country)
    # Scores saved by an older formula are redone once, by whichever front end opens first.
    rescored = rescore_if_formula_changed(resume, place, home_cities())
    try:
        rows = repo().list_matches(resume_id, limit=clamp(limit, 1, 1000, 500))
    except Exception:
        log.exception("list_matches failed")
        raise HTTPException(status_code=500, detail="The matches could not be read.") from None
    annotated = [jsonable(r) for r in annotate(rows, resume, place, home_cities())]
    return {
        "matches": annotated,
        "rescored": rescored,
        "country": place,
        "cities": list(home_cities()),
        "candidate_years": round(candidate_years(resume), 1),
        "sources": sorted({r["source"] for r in annotated if r["source"]}),
        "source_names": {r["source"]: r["source_name"] for r in annotated if r["source"]},
    }


@router.get("/matches/{match_id}")
def get_match(match_id: int, resume_id: int) -> dict:
    """One job in full: the posting, the requirement split and the keyword gap."""
    resume = repo().get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="That resume is not stored any more.")
    rows = [m for m in repo().list_matches(resume_id, limit=1000) if m.get("id") == match_id]
    if not rows:
        raise HTTPException(status_code=404, detail="That job is not in your matches.")
    return jsonable(detail(rows[0], resume))


@router.post("/matches/{match_id}/requirements")
def llm_requirements(match_id: int, resume_id: int, model: str | None = None) -> dict:
    """Re-read the posting's must-have and nice-to-have skills with the language model."""
    rows = [m for m in repo().list_matches(resume_id, limit=1000) if m.get("id") == match_id]
    if not rows:
        raise HTTPException(status_code=404, detail="That job is not in your matches.")
    match = rows[0]
    try:
        return load("generator.jd_insights", "analyze_requirements_llm")(
            {"title": match.get("title"), "description": match.get("description") or ""}, model=model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error(exc, "read this posting")) from exc


@router.patch("/matches/{match_id}/status")
def set_status(match_id: int, body: StatusIn) -> dict:
    """Save, hide, mark applied or rejected."""
    if body.status not in catalog.MATCH_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown status.")
    try:
        ok = repo().update_match_status(match_id, body.status)
    except Exception:
        log.exception("update_match_status failed")
        raise HTTPException(status_code=500, detail="The status could not be saved.") from None
    if not ok:
        raise HTTPException(status_code=404, detail="That job is not in your matches.")
    return {"status": body.status, "message": STATUS_MESSAGES.get(body.status, f"Marked as {body.status}.")}


@router.get("/skills-to-learn")
def learn(resume_id: int, country: str | None = None) -> dict:
    """Skills that would close the most near-miss jobs, and the jobs they would close."""
    resume = repo().get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="That resume is not stored any more.")
    rows = annotate(repo().list_matches(resume_id, limit=500), resume, home_country(country), home_cities())
    near = [r for r in rows if r.get("near_miss") and r.get("status") != "hidden"]
    near.sort(key=lambda r: (len(r["gap"]["missing"]), -float(r["score"] or 0)))
    return {
        "skills": skills_to_learn(near),
        "jobs": [{"id": r["id"], "title": r["title"], "company": r["company"],
                  "missing": r["gap"]["missing"], "matched": len(r["gap"]["matched"]),
                  "required": len(r["gap"]["required"])} for r in near[:12]],
        "near_count": len(near),
    }


STATUS_MESSAGES = {
    "saved": "Saved. It is now listed under Applications.",
    "hidden": "Hidden from your matches.",
    "applied": "Marked as applied.",
    "rejected": "Marked as rejected.",
    "new": "Moved back to new.",
}
