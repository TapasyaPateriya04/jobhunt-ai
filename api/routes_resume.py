"""Resume screen: upload, switch, and the skills typed in by hand."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.core import as_list, g, jsonable, load, log, repo, setting
from api.matching_view import candidate_years, home_cities, home_country, score_and_save

router = APIRouter()

RESUME_EXTS = {".tex", ".txt", ".md", ".pdf"}
LANGUAGES = ("Java", "Python", "JavaScript", "TypeScript", "Go", "Kotlin", "C#", "C++", "Ruby", "PHP",
             "Rust", "Scala", "Swift", "Dart")


class SkillsIn(BaseModel):
    add: str | None = None
    remove: str | None = None


@router.get("/resumes")
def list_resumes() -> dict:
    """Every stored resume, newest first, for the picker in the sidebar."""
    try:
        rows = repo().list_resumes()
    except Exception:
        log.exception("list_resumes failed")
        rows = []
    return {"resumes": [{"id": r["id"], "name": file_name(r), "skill_count": len(as_list(r.get("skills"))),
                         "created_at": jsonable(r.get("created_at"))} for r in rows]}


@router.get("/resume")
def get_resume(id: int | None = None) -> dict:
    """The resume in use: the one asked for, else the most recent."""
    try:
        resume = repo().get_resume(id) if id else repo().latest_resume()
    except Exception:
        log.exception("reading the resume failed")
        resume = None
    return {"resume": public_resume(resume)}


@router.post("/resume/upload")
def upload_resume(file: UploadFile = File(...), replaces: int | None = None) -> dict:
    """Validate, parse and store an uploaded resume, then score the stored jobs against it."""
    data = file.file.read()
    name = str(file.filename or "resume")
    max_bytes = int(setting("upload_max_bytes", 2_000_000) or 2_000_000)
    try:
        load("security.sanitize", "validate_upload")(name, data, RESUME_EXTS, max_bytes)
        parsed = load("parser.resume_parser", "parse_resume_bytes")(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = _store_upload(name, data)
    resume_id = repo().save_resume(parsed, path, inherit_skills_from=replaces)
    resume = repo().get_resume(resume_id) or dict(parsed, id=resume_id)
    scored, error = _rescore(resume)
    return {"resume": public_resume(resume), "scored": scored, "score_error": error}


@router.post("/resume/{resume_id}/skills")
def edit_skills(resume_id: int, body: SkillsIn) -> dict:
    """Add comma-separated skills, or remove one that was added by hand."""
    resume = repo().get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="That resume is not stored any more.")
    extra = [str(s) for s in as_list(resume.get("extra_skills"))]
    added: list[str] = []
    if body.remove:
        extra = [s for s in extra if s != body.remove]
    if body.add:
        canonical = load("parser.skills_vocab", "canonicalize")
        have = {str(s).lower() for s in as_list(resume.get("skills"))}
        for part in str(body.add).replace(";", ",").replace("\n", ",").split(","):
            skill = " ".join(part.split())[:40]
            skill = canonical(skill) or skill
            if skill and skill.lower() not in have:
                have.add(skill.lower())
                extra.append(skill)
                added.append(skill)
    repo().set_extra_skills(resume_id, extra)
    fresh = repo().get_resume(resume_id) or resume
    return {"resume": public_resume(fresh), "added": added,
            "removed": body.remove if body.remove else None}


@router.post("/resume/{resume_id}/score")
def score_resume(resume_id: int, country: str | None = None) -> dict:
    """Score every stored job against this resume (the Score stored jobs button)."""
    resume = repo().get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="That resume is not stored any more.")
    scored, error = _rescore(resume, country)
    if error:
        raise HTTPException(status_code=500, detail=error)
    return {"scored": scored}


def _rescore(resume: dict, country: str | None = None) -> tuple[int, str]:
    try:
        return score_and_save(resume, home_country(country), home_cities()), ""
    except Exception as exc:
        log.exception("scoring stored jobs failed")
        return 0, f"The jobs could not be scored ({type(exc).__name__}). Press Score stored jobs to try again."


def public_resume(resume: dict | None) -> dict | None:
    """The resume as the screens read it. The raw text is trimmed, never the whole file."""
    if not resume:
        return None
    skills = [str(s) for s in as_list(g(resume, "skills", "skills_json", default=[]))]
    extra = [str(s) for s in as_list(resume.get("extra_skills"))]
    extra_low = {s.lower() for s in extra}
    experience = as_list(g(resume, "experience", "experience_json", default=[]))
    raw = str(g(resume, "raw_text", default="") or "")
    return {
        "id": g(resume, "id"),
        "name": file_name(resume),
        "created_at": jsonable(g(resume, "created_at")),
        "skills": [s for s in skills if s.lower() not in extra_low],
        "extra_skills": extra,
        "skill_count": len(skills),
        "experience": [experience_line(x) for x in experience[:12]],
        "experience_count": len(experience),
        "education": [str(x) for x in ([g(resume, "education")] if isinstance(g(resume, "education"), str)
                                       else as_list(g(resume, "education"))) if str(x).strip()],
        "summary": str(g(resume, "summary", default="") or ""),
        "raw_text": raw[:10000],
        "raw_truncated": len(raw) > 10000,
        "years": round(candidate_years(resume), 1),
        "suggested_keywords": suggested_keywords(resume),
        "suggested_location": str(setting("candidate_country", "") or "").strip() or "Remote",
    }


def file_name(resume: dict) -> str:
    """The uploaded file's name without the random prefix added when it was stored."""
    name = Path(str(g(resume, "file_path", default="") or "resume")).name
    return re.sub(r"^[0-9a-f]{8}-", "", name)


def experience_line(item) -> dict:
    """One experience entry split into its heading and its dates (same fields the app reads)."""
    if not isinstance(item, dict):
        return {"head": " ".join(str(item).split())[:200], "dates": ""}
    title = g(item, "title", "role", "position", default="")
    org = g(item, "company", "organization", "org", default="")
    dates = g(item, "dates", "duration", "period", default="")
    if not dates and (item.get("start") or item.get("end")):
        dates = f"{item.get('start') or ''} - {item.get('end') or ''}"
    head = " at ".join(p for p in (str(title), str(org)) if p)
    if not head:
        import json

        head = json.dumps(item)[:200]
    return {"head": head, "dates": str(dates or "")}


def suggested_keywords(resume: dict | None) -> str:
    """A first search from the resume: the language it mentions most, plus Developer."""
    skills = [str(s) for s in as_list(g(resume or {}, "skills", default=[]))]
    lowered = {s.lower() for s in skills}
    langs = [lang for lang in LANGUAGES if lang.lower() in lowered]
    if not langs:
        return "Software Engineer"
    text = str(g(resume or {}, "raw_text", default="") or "")

    def mentions(lang: str) -> int:
        # "Java" must not count "JavaScript"; "C" must not count "C++" or "C#".
        return len(re.findall(r"(?<![\w+#])" + re.escape(lang) + r"(?![\w+#])", text, re.I))

    order = {lang: i for i, lang in enumerate(langs)}
    return f"{max(langs, key=lambda lang: (mentions(lang), -order[lang]))} Developer"


def _store_upload(filename: str, data: bytes) -> str:
    """Keep a copy of the upload in docs_dir/uploads (safe path); fall back to the bare name."""
    try:
        sanitize = load("security.sanitize")
        base = Path(os.path.expanduser(str(setting("docs_dir", "~/jobhunt_docs")))) / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        path = sanitize.safe_join(base, sanitize.safe_filename(filename))
        path.write_bytes(data)
        return str(path)
    except Exception:
        log.warning("Could not store the uploaded resume copy")
        return filename
