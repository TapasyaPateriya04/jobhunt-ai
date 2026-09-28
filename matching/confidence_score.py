"""Confidence score (SPEC §5.3): weighted blend of ATS, experience, semantic, freshness.

total = 0.35 * ats + 0.25 * experience + 0.20 * semantic + 0.20 * freshness   (all 0-100)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, List, Optional, Tuple

from matching.ats_scorer import batch_raw_cosines, calibrate
from matching.semantic_matcher import semantic_scores

WEIGHTS = {"ats": 0.35, "experience": 0.25, "semantic": 0.20, "freshness": 0.20}
DEFAULT_REQUIRED_YEARS = 2
MAX_YEARS = 50

# ----------------------------------------------------------------------------- text helpers

def resume_text(resume: dict) -> str:
    resume = resume or {}
    raw = resume.get("raw_text")
    if isinstance(raw, str) and raw.strip():
        return raw
    parts: List[str] = []
    for key in ("summary", "education"):
        v = resume.get(key)
        if isinstance(v, str):
            parts.append(v)
    skills = resume.get("skills") or []
    if isinstance(skills, (list, tuple)):
        parts.append(" ".join(str(s) for s in skills))
    for e in resume.get("experience") or []:
        if isinstance(e, dict):
            for v in e.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, (list, tuple)):
                    parts.extend(str(x) for x in v)
        elif isinstance(e, str):
            parts.append(e)
    return "\n".join(p for p in parts if p)


def job_text(job: dict) -> str:
    """Job description, or title + snippet/summary (+ company) when description is missing."""
    job = job or {}
    desc = job.get("description")
    if isinstance(desc, str) and desc.strip():
        return desc
    parts = [job.get(k) for k in ("title", "snippet", "summary", "company", "tags")]
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif isinstance(p, (list, tuple)):
            out.append(" ".join(map(str, p)))
    return " ".join(out).strip()

# ----------------------------------------------------------------------------- freshness

def _to_aware_utc(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    elif isinstance(value, (int, float)):
        try:
            ts = float(value) / (1000.0 if value > 1e11 else 1.0)  # ms or s epoch
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(value, str):
        s = value.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                dt = datetime.fromisoformat(s[:10])
            except ValueError:
                return None
    else:
        return None
    if dt.tzinfo is None:  # naive -> assume UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def freshness_score(posted_date: Any, now: Optional[datetime] = None) -> float:
    """SPEC buckets: <=24h 100, <=72h 85, <=7d 70, <=14d 50, older 30; unknown 50."""
    dt = _to_aware_utc(posted_date)
    if dt is None:
        return 50.0
    now_dt = _to_aware_utc(now) if now is not None else datetime.now(timezone.utc)
    hours = (now_dt - dt).total_seconds() / 3600.0
    if hours <= 24:  # includes slightly-future timestamps (clock skew)
        return 100.0
    if hours <= 72:
        return 85.0
    if hours <= 168:
        return 70.0
    if hours <= 336:
        return 50.0
    return 30.0

# ----------------------------------------------------------------------------- experience

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_PRESENT_RE = re.compile(r"\b(present|current(?:ly)?|now|today|ongoing|date)\b", re.I)
_DATE_TOKEN_RE = re.compile(
    r"(?:(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*,?\s*)?"
    r"(?:(?P<num>\d{1,2})\s*[/.-]\s*)?(?P<year>(?:19|20)\d{2})"
    r"(?:[/.-](?P<mon2>\d{1,2})(?!\d))?", re.I)  # ISO-style "2018-06"
_REQ_YEARS_RE = re.compile(
    r"(?P<a>\d{1,2})(?:\.\d)?\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(?P<b>\d{1,2})\s*\+?\s*)?"
    r"(?:years?|yrs?)\b", re.I)
_MIN_YEARS_RE = re.compile(r"(?:at\s+least|minimum(?:\s+of)?|min\.?)\s+(?P<a>\d{1,2})\s*(?:years?|yrs?)", re.I)


def _now_months(now: Optional[datetime] = None) -> int:
    n = now or datetime.now(timezone.utc)
    return n.year * 12 + n.month


def _parse_point(value: Any, is_end: bool, now: Optional[datetime] = None) -> Optional[int]:
    """Convert a start/end value to an absolute month index (year*12 + month)."""
    if value is None or value == "":
        return _now_months(now) if is_end else None
    if isinstance(value, (datetime, date)):
        return value.year * 12 + value.month
    if isinstance(value, (int, float)) and 1900 <= value <= 2100:
        return int(value) * 12 + (12 if is_end else 1)
    s = str(value)
    if _PRESENT_RE.search(s):
        return _now_months(now)
    m = _DATE_TOKEN_RE.search(s)
    if not m:
        return None
    year = int(m.group("year"))
    month = None
    if m.group("mon"):
        month = _MONTHS.get(m.group("mon").lower()[:3])
    elif m.group("num") and 1 <= int(m.group("num")) <= 12:
        month = int(m.group("num"))
    elif m.group("mon2") and 1 <= int(m.group("mon2")) <= 12:
        month = int(m.group("mon2"))
    if month is None:
        month = 12 if is_end else 1
    return year * 12 + month


def _parse_range_text(text: str, now: Optional[datetime] = None) -> Optional[Tuple[int, int]]:
    """Parse "2021 - Present", "Jan 2019 – Mar 2021", "06/2018 to 2020"."""
    if not text:
        return None
    tokens = list(_DATE_TOKEN_RE.finditer(text))
    if not tokens:
        return None
    start = _parse_point(tokens[0].group(0), is_end=False, now=now)
    if len(tokens) >= 2:
        end = _parse_point(tokens[1].group(0), is_end=True, now=now)
    elif _PRESENT_RE.search(text[tokens[0].end():]):
        end = _now_months(now)
    else:  # a single year like "2020" -> treat as that year
        end = _parse_point(tokens[0].group(0), is_end=True, now=now)
    if start is None or end is None:
        return None
    return start, end


def _entry_interval(entry: dict, now: Optional[datetime] = None) -> Optional[Tuple[int, int]]:
    if "start" in entry and entry.get("start") not in (None, ""):
        start = _parse_point(entry.get("start"), is_end=False, now=now)
        end = _parse_point(entry.get("end"), is_end=True, now=now)
        if start is not None and end is not None:
            return start, end
    for key in ("dates", "date", "duration", "period"):
        v = entry.get(key)
        if isinstance(v, str):
            rng = _parse_range_text(v, now=now)
            if rng:
                return rng
    return None


def _years_value(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if 0 <= v <= MAX_YEARS else None
    if isinstance(v, str):
        m = re.search(r"\d+(?:\.\d+)?", v)
        if m:
            f = float(m.group(0))
            return f if f <= MAX_YEARS else None
    return None


def estimate_candidate_years(experience: Any, now: Optional[datetime] = None) -> float:
    """Estimate total years of experience from resume entries.

    Date ranges are merged so overlapping jobs are not double-counted; entries with an
    explicit "years" value are added; entries with nothing parseable count as 1 year each
    (the SPEC's original rough proxy).
    """
    if not experience or not isinstance(experience, (list, tuple)):
        return 0.0
    intervals: List[Tuple[int, int]] = []
    explicit = 0.0
    unknown = 0
    for e in experience:
        if not isinstance(e, dict):
            unknown += 1
            continue
        yrs = _years_value(e.get("years"))
        if yrs is not None:
            explicit += yrs
            continue
        rng = _entry_interval(e, now=now)
        if rng and rng[1] >= rng[0]:
            intervals.append(rng)
        else:
            unknown += 1
    merged: List[List[int]] = []
    for s, t in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], t)
        else:
            merged.append([s, t])
    months = sum(t - s + 1 for s, t in merged)
    return round(min(MAX_YEARS, months / 12.0 + explicit + unknown), 1)


def extract_required_years(text: str) -> Optional[int]:
    """Parse required experience from a JD ("3+ years", "2-4 yrs", "at least 5 years")."""
    if not text:
        return None
    m = _MIN_YEARS_RE.search(text)
    if m:
        return int(m.group("a"))
    candidates = []
    for m in _REQ_YEARS_RE.finditer(text):
        a = int(m.group("a"))
        tail = text[m.end():m.end() + 40].lower()
        head = text[max(0, m.start() - 40):m.start()].lower()
        # prefer mentions tied to "experience"; ignore "5 years ago", company age etc.
        if "old" in tail[:6] or "ago" in tail[:6]:
            continue
        if 0 < a <= 20:
            candidates.append((("experience" in tail or "exp" in tail or "experience" in head), a))
    if not candidates:
        return None
    tied = [a for tied, a in candidates if tied]
    return (tied or [a for _, a in candidates])[0]


def required_years_for(job: dict) -> Optional[int]:
    v = (job or {}).get("experience_years")
    yrs = _years_value(v)
    if yrs is not None:
        return int(round(yrs))
    return extract_required_years(job_text(job))


def experience_score(resume_exp: Any, required_years: Optional[float]) -> float:
    candidate = resume_exp if isinstance(resume_exp, (int, float)) else estimate_candidate_years(resume_exp)
    required = DEFAULT_REQUIRED_YEARS if required_years is None else required_years
    if required <= 0 or candidate >= required:
        return 100.0
    return float(max(40.0, min(100.0, candidate / required * 100.0)))

# ----------------------------------------------------------------------------- scoring

def _combine(ats: float, ats_raw: float, exp: float, sem: float, fresh: float,
             candidate_years: float, required_years: Optional[int]) -> dict:
    total = (WEIGHTS["ats"] * ats + WEIGHTS["experience"] * exp
             + WEIGHTS["semantic"] * sem + WEIGHTS["freshness"] * fresh)
    return {
        "total": round(max(0.0, min(100.0, total)), 1),
        "ats": round(ats, 1),
        "experience": round(exp, 1),
        "semantic": round(sem, 1),
        "freshness": round(fresh, 1),
        "ats_raw": round(ats_raw, 1),
        "candidate_years": candidate_years,
        "required_years": required_years,
    }


def _score_batch(resume: dict, jobs: List[dict]) -> List[dict]:
    rtext = resume_text(resume)
    jtexts = [job_text(j) for j in jobs]
    raws = batch_raw_cosines(rtext, jtexts)  # single TF-IDF fit across the batch
    sems = semantic_scores(rtext, jtexts)
    cand = estimate_candidate_years((resume or {}).get("experience"))
    out = []
    for job, raw, sem in zip(jobs, raws, sems):
        req = required_years_for(job)
        out.append(_combine(calibrate(raw), raw * 100.0, experience_score(cand, req), sem,
                            freshness_score((job or {}).get("posted_date")), cand, req))
    return out


def calculate_confidence_score(resume: dict, job: dict) -> dict:
    """Scores for one resume/job pair: total, ats, experience, semantic, freshness (+ ats_raw)."""
    return _score_batch(resume or {}, [job or {}])[0]


def score_jobs(resume: dict, jobs: Iterable[dict]) -> List[dict]:
    """Return shallow copies of jobs with a "scores" dict attached, sorted by total desc."""
    jobs = [j for j in (jobs or []) if isinstance(j, dict)]
    if not jobs:
        return []
    scores = _score_batch(resume or {}, jobs)
    result = [{**j, "scores": s} for j, s in zip(jobs, scores)]
    result.sort(key=lambda j: j["scores"]["total"], reverse=True)
    return result


__all__ = [
    "calculate_confidence_score", "score_jobs", "freshness_score", "experience_score",
    "estimate_candidate_years", "extract_required_years", "WEIGHTS",
]
