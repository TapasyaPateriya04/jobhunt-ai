"""What the app knows about itself: storage, language model, counts, next step."""
from __future__ import annotations

import json
import urllib.request

from fastapi import APIRouter

from api import catalog
from api.core import FeatureUnavailable, db_location, g, load, log, repo, score_of, setting, settings

router = APIRouter()

GEMINI = "gemini"  # same value as generator.llm.GEMINI


@router.get("/catalog")
def get_catalog() -> dict:
    """Names, bands and wording the screens use, so no label is written twice."""
    opt_in = [s for s in catalog.OPT_IN_SOURCES if s in tuple(setting("jobspy_sites", ()) or ())]
    boards = {"greenhouse": tuple(setting("greenhouse_boards", ()) or ()),
              "lever": tuple(setting("lever_companies", ()) or ())}
    sources = []
    for key, (name, about) in catalog.SOURCES.items():
        if key in catalog.OPT_IN_SOURCES and key not in opt_in:
            continue
        sources.append({"key": key, "name": name, "about": about,
                        "default": key in catalog.DEFAULT_SOURCES or key in opt_in,
                        "configured": bool(boards[key]) if key in boards else True,
                        "opt_in": key in catalog.OPT_IN_SOURCES})
    return {
        "sources": sources,
        "statuses": [{"key": s, "label": catalog.status_name(s)} for s in catalog.MATCH_STATUSES],
        "tracked_statuses": [{"key": s, "label": catalog.status_name(s), "hint": catalog.TRACK_HINTS[s]}
                             for s in catalog.TRACKED_STATUSES],
        "bands": catalog.SCORE_BANDS,
        "score_parts": catalog.SCORE_PARTS,
        "score_note": catalog.SCORE_NOTE,
        "doc_types": [{"key": k, "label": v} for k, v in catalog.DOC_TYPES.items()],
        "sorts": catalog.SORTS,
        "collection_note": [{"title": t, "body": b} for t, b in catalog.COLLECTION_NOTE],
        "max_jobs_per_session": int(setting("max_jobs_per_session", 50) or 50),
        "upload_max_bytes": int(setting("upload_max_bytes", 2_000_000) or 2_000_000),
        "refresh_minutes": int(setting("jobspy_refresh_minutes", 60) or 60),
        "auto_refresh_offered": bool(opt_in) and bool(setting("jobspy_auto_refresh", True)),
    }


@router.get("/countries")
def get_countries() -> dict:
    """The places location fit knows about, plus the one configured in .env."""
    try:
        places = sorted(load("matching.location", "PLACES"))
        configured = load("matching.location", "normalize_country")(str(setting("candidate_country", "") or ""))
    except FeatureUnavailable:
        return {"countries": [], "configured": "", "cities": list(setting("candidate_cities", ()) or ())}
    if configured and configured not in places:
        places = sorted(set(places) | {configured})
    return {"countries": places, "configured": configured,
            "cities": list(setting("candidate_cities", ()) or ())}


@router.get("/status")
def get_status() -> dict:
    """Storage, language model and row counts: everything the sidebar shows."""
    s = settings()
    base = str(getattr(s, "ollama_base_url", "http://localhost:11434"))
    use_ollama = bool(getattr(s, "use_ollama", True))
    models = ollama_models(base) if use_ollama else []
    has_key = bool(getattr(s, "gemini_api_key", None))
    return {
        "database": db_location(str(s.database_url)),
        "docs_dir": str(getattr(s, "docs_dir", "~/jobhunt_docs")),
        "counts": db_counts(),
        "ollama": {
            "enabled": use_ollama,
            "reachable": bool(models) or (use_ollama and ollama_reachable(base)),
            "base_url": base,
            "configured_model": str(getattr(s, "ollama_model", "") or ""),
            "models": models,
        },
        "gemini": {"configured": has_key, "model": str(getattr(s, "gemini_model", "") or "")},
        "models": [m["name"] for m in models] + ([GEMINI] if has_key else []),
        "embedding_model": _embedding_name(),
    }


@router.get("/overview")
def get_overview(resume_id: int | None = None) -> dict:
    """The headline numbers above the tabs and the one thing to do next."""
    resume = _resume(resume_id)
    matches = _matches(resume)
    jobs = int(db_counts().get("jobs", 0) or 0)
    strong = sum(1 for m in matches if score_of(m) >= 50 and g(m, "status", default="new") != "hidden")
    counts = {s: sum(1 for m in matches if g(m, "status", default="new") == s)
              for s in catalog.MATCH_STATUSES}
    return {
        "has_resume": bool(resume),
        "stats": [
            {"value": jobs, "label": "jobs collected"},
            {"value": len(matches), "label": "scored for this resume"},
            {"value": strong, "label": "strong matches"},
            {"value": counts["saved"], "label": "saved"},
            {"value": counts["applied"], "label": "applied"},
        ],
        "counts": counts,
        "next_step": next_step(bool(resume), jobs, matches),
    }


def next_step(has_resume: bool, jobs: int, matches: list) -> dict:
    """The one thing to do next, in the order resume, collect, score, shortlist, apply.

    ``tab`` lets the front end turn the sentence into a button.
    """
    if not has_resume:
        return {"tab": "resume", "text": "Upload your resume on the Resume tab."}
    if not jobs:
        return {"tab": "jobs", "text": "Collect some postings on the Find jobs tab."}
    if not matches:
        return {"tab": "matches",
                "text": "Open Matches and press Score stored jobs to rank the postings against your resume."}
    saved = sum(1 for m in matches if g(m, "status", default="new") == "saved")
    applied = sum(1 for m in matches if g(m, "status", default="new") == "applied")
    if saved:
        return {"tab": "documents",
                "text": f"You have {saved} saved job{'s' if saved != 1 else ''}. Draft a cover letter on the "
                        "Documents tab, then mark each one applied under Applications."}
    if applied:
        return {"tab": "matches",
                "text": "Save more jobs on the Matches tab and update the ones you hear back from."}
    return {"tab": "matches", "text": "Read through Matches and press Save on the jobs worth applying to."}


def db_counts() -> dict:
    try:
        from sqlalchemy import func, select

        dbm = load("db.database")
        with dbm.get_session() as session:
            return {name: session.scalar(select(func.count()).select_from(model)) or 0
                    for name, model in (("resumes", dbm.Resume), ("jobs", dbm.Job),
                                        ("matches", dbm.Match), ("documents", dbm.Document))}
    except Exception:
        log.exception("counting rows failed")
        return {}


def _resume(resume_id: int | None) -> dict | None:
    try:
        return repo().get_resume(resume_id) if resume_id else repo().latest_resume()
    except Exception:
        log.exception("reading the resume failed")
        return None


def _matches(resume: dict | None, limit: int = 500) -> list:
    if not resume or g(resume, "id") is None:
        return []
    try:
        return repo().list_matches(resume["id"], limit=limit)
    except Exception:
        log.exception("list_matches failed")
        return []


def _embedding_name() -> str:
    """'all-MiniLM-L6-v2' when the model loaded, '' when scoring falls back to keywords."""
    try:
        sm = load("matching.semantic_matcher")
        return str(getattr(sm, "MODEL_NAME", "all-MiniLM-L6-v2")) if sm.get_model() is not None else ""
    except Exception:
        return ""


def ollama_reachable(base_url: str) -> bool:
    """Quick (1 s) probe of Ollama's /api/tags. Only local endpoints are probed."""
    try:
        try:
            base_url = load("security.url_guard", "validate_llm_endpoint")(base_url)
        except FeatureUnavailable:
            pass
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=1) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception:
        return False


def ollama_models(base_url: str) -> list:
    """Installed Ollama models as ``[{"name", "size"}]``, smallest first; [] when Ollama is off."""
    try:
        try:
            base_url = load("security.url_guard", "validate_llm_endpoint")(base_url)
        except FeatureUnavailable:
            pass
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=1) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:
        return []
    models = []
    for m in data.get("models") or []:
        name = str(m.get("name") or "").strip()
        if name:
            models.append({"name": name, "size": str((m.get("details") or {}).get("parameter_size") or ""),
                           "bytes": int(m.get("size") or 0)})
    return sorted(models, key=lambda m: m["bytes"])
