"""Turning stored matches into what the Matches screen needs.

The same cheap rules the Streamlit app recomputes on the fly (location fit, years
asked, skill gap) with the same per-job caches, so switching front ends does not
change a single score.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from api.core import as_list, g, load, log, score_of, setting
from api.catalog import BLOCKED_LOCATIONS, band_label, source_name


@lru_cache(maxsize=4096)
def _fit(title: str, location: str, description: str, source: str, country: str, cities: tuple) -> dict:
    """Location fit is the slowest per-job rule, so compute it once per job."""
    return load("matching.location", "location_fit")(
        {"title": title, "location": location, "description": description, "source": source}, country, cities)


@lru_cache(maxsize=2048)
def _gap(jd_text: str, have: tuple) -> dict:
    return load("matching.skill_gap", "skill_gap")({"description": jd_text}, have)


@lru_cache(maxsize=512)
def _keyword_gap(resume_text: str, jd_text: str) -> dict:
    return load("matching.ats_scorer", "keyword_gap")(resume_text, jd_text, top_n=15)


@lru_cache(maxsize=512)
def _requirements(jd_text: str) -> dict:
    return load("generator.jd_insights", "split_requirements")(jd_text)


@lru_cache(maxsize=1024)
def posting_skills(jd_text: str) -> tuple:
    return tuple(load("parser.skills_vocab", "find_skills")(jd_text)[:7])


def home_country(country=None) -> str:
    """The country to judge locations against: the one asked for, else the configured one."""
    if country is not None:
        return str(country or "")
    try:
        return load("matching.location", "normalize_country")(str(setting("candidate_country", "") or ""))
    except Exception:
        return ""


def home_cities() -> tuple:
    return tuple(setting("candidate_cities", ()) or ())


def band_of(total) -> str:
    """"strong", "possible" or "weak", from the one function both front ends use."""
    try:
        return str(load("matching.confidence_score", "band")(total))
    except Exception:
        return "none"


def thresholds() -> dict:
    """The numbers the score guide quotes, read from matching/confidence_score.py."""
    cs = load("matching.confidence_score")
    return {
        "strong": float(cs.STRONG_AT),
        "possible": float(cs.POSSIBLE_AT),
        "strong_skills": float(cs.STRONG_MIN_SKILLS),
        "possible_skills": float(cs.POSSIBLE_MIN_SKILLS),
        "title_cap": float(cs.TITLE_SKILL_CAP),
    }


def rescore_if_formula_changed(resume: dict, country: str, cities: tuple) -> int:
    """Stored scores were saved by an older formula: score them again, once.

    The marker file is the one ``ui/app.py`` writes, so whichever front end opens first
    does the work and the other finds it done.
    """
    import os

    try:
        version = int(load("matching.confidence_score", "SCORING_VERSION"))
    except Exception:
        return 0
    marker = Path(os.path.expanduser(str(setting("docs_dir", "~/jobhunt_docs")))) / ".scoring_version"
    try:
        if marker.read_text(encoding="utf-8").strip() == str(version):
            return 0
    except OSError:
        pass
    scored = score_and_save(resume, country, cities)
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(version), encoding="utf-8")
    except OSError:
        log.warning("Could not save the scoring version")
    return scored


def candidate_years(resume: dict) -> float:
    try:
        return float(load("matching.confidence_score", "estimate_candidate_years")(
            as_list(g(resume, "experience", default=[]))))
    except Exception:
        return 0.0


def score_and_save(resume: dict, country: str = "", cities: tuple = ()) -> int:
    """Score every stored job against ``resume`` and save the matches. Returns how many."""
    r = load("db.repository")
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
    _fit.cache_clear()
    return saved


def embedding_ready() -> bool:
    """Whether the MiniLM model is loaded, so the UI can say how jobs were compared."""
    try:
        return load("matching.semantic_matcher", "get_model")() is not None
    except Exception:
        return False


def annotate(matches: list, resume: dict, country: str, cities: tuple) -> list:
    """Each stored match as the front end reads it: scores, gap, location fit, years."""
    labels = load("matching.location", "LABELS")
    cs = load("matching.confidence_score")
    gaps = load("matching.skill_gap")
    have = gaps.candidate_skills(resume)
    have_key = tuple(sorted(have))
    out = []
    for m in matches:
        total = score_of(m)
        band = band_of(total)
        row = {
            "id": g(m, "id", "match_id"),
            "job_id": g(m, "job_id"),
            "title": g(m, "title", default="Untitled role"),
            "company": g(m, "company", default="Unknown company"),
            "location": g(m, "location", default="") or "",
            "url": g(m, "url", default="") or "",
            "source": g(m, "source", default="") or "",
            "source_name": source_name(g(m, "source", default="")),
            "posted_date": g(m, "posted_date"),
            "status": g(m, "status", default="new"),
            "score": round(total, 1),
            "band": band,
            "band_label": band_label(band),
            "parts": {
                "ats": _num(g(m, "ats_score", "ats")),
                "experience": _num(g(m, "experience_score", "experience")),
                "semantic": _num(g(m, "semantic_score", "semantic")),
                "freshness": _num(g(m, "freshness_score", "freshness")),
            },
            "snippet": _snippet(g(m, "description", default="") or ""),
            "has_description": bool(g(m, "description", default="")),
        }
        try:
            loc = _fit(str(g(m, "title", default="") or ""), str(g(m, "location", default="") or ""),
                       str(g(m, "description", default="") or ""), str(g(m, "source", default="") or ""),
                       country, tuple(cities)) if country else None
            gap = _gap(cs.job_text(m), have_key)
            row["location_status"] = loc["status"] if loc else ""
            row["location_text"] = f"{labels[loc['status']]}: {loc['reason']}" if loc else ""
            row["location_ok"] = None if not loc else loc["status"] not in BLOCKED_LOCATIONS
            row["years"] = cs.required_years_for(m)
            row["gap"] = {k: list(gap.get(k, [])) for k in ("required", "matched", "missing", "nice_missing")}
            row["near_miss"] = bool(gaps.is_near_miss(gap))
        except Exception:
            log.exception("match annotation failed")
            row.update(location_status="", location_text="", location_ok=None, years=None, near_miss=False,
                       gap={"required": [], "matched": [], "missing": [], "nice_missing": []})
        out.append(row)
    return out


def detail(match: dict, resume: dict) -> dict:
    """The score breakdown screen: requirement split and matched / missing keywords."""
    jd = str(g(match, "description", default="") or "")
    cs = load("matching.confidence_score")
    resume_text = cs.resume_text(resume)
    have = {str(x).lower() for x in load("matching.skill_gap", "candidate_skills")(resume)}
    out = {"description": jd, "requirements": {"must_have": [], "nice_to_have": [], "source": ""},
           "keywords": {"matched": [], "missing": []}, "have": sorted(have)}
    if not jd:
        return out
    try:
        out["requirements"] = _requirements(jd)
    except Exception:
        log.exception("requirement split failed")
    if resume_text:
        try:
            words = _keyword_gap(resume_text, jd)
            out["keywords"] = {"matched": list(words.get("matched", [])),
                               "missing": list(words.get("missing", []))}
        except Exception:
            log.exception("keyword_gap failed")
    return out


def skills_to_learn(rows: list) -> list:
    """Skills that would close the most near-miss jobs among ``rows``."""
    near = [r for r in rows if r.get("near_miss")]
    if not near:
        return []
    try:
        return list(load("matching.skill_gap", "skills_to_learn")([{"gap": r["gap"]} for r in near]))
    except Exception:
        log.exception("skills_to_learn failed")
        return []


def _num(value):
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _snippet(text: str, limit: int = 240) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "..."
