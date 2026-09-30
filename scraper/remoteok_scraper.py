"""RemoteOK public JSON API (free, no auth) — the default job source.

API: GET https://remoteok.com/api -> [legal_notice, job, job, ...]
RemoteOK asks API users to link back to the job URL and credit RemoteOK as the source.
"""
from __future__ import annotations

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job

API_URL = "https://remoteok.com/api"


def _matches(job: dict, terms: list[str], phrase: str) -> int:
    """Relevance: 3 for an exact phrase hit in the title, else number of matching terms."""
    title = str(job.get("position") or "").lower()
    tags = " ".join(str(t) for t in (job.get("tags") or [])).lower()
    desc = html_to_text(str(job.get("description") or "")).lower()
    hay = f"{title} {tags} {desc}"
    if phrase and net.contains_term(phrase, title):
        return 100
    in_title = sum(2 for t in terms if net.contains_term(t, f"{title} {tags}"))
    return in_title + sum(1 for t in terms if net.contains_term(t, hay))


def parse_remoteok(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize a RemoteOK API payload (pure function, used by tests)."""
    if not isinstance(payload, list):
        return []
    items = payload[1:] if payload and isinstance(payload[0], dict) and "legal" in payload[0] else payload
    terms = net.keyword_terms(keywords)
    phrase = (keywords or "").strip().lower()
    scored = []
    for idx, job in enumerate(items):
        if not isinstance(job, dict) or not job.get("position"):
            continue
        score = _matches(job, terms, phrase) if terms else 1
        if score <= 0:
            continue
        scored.append((score, idx, job))
    # Most relevant first; API order (newest first) breaks ties.
    scored.sort(key=lambda t: (-t[0], t[1]))
    out: list[dict] = []
    for _, _, job in scored[:max_jobs]:
        raw = dict(job)
        tags = [str(t) for t in (job.get("tags") or [])]
        desc = html_to_text(str(job.get("description") or ""))
        if tags:
            desc = f"{desc}\n\nTags: {', '.join(tags)}".strip()
        salary = ""
        if job.get("salary_min") and job.get("salary_max"):
            salary = f"\nSalary: ${int(job['salary_min']):,} - ${int(job['salary_max']):,}"
        raw["description"] = desc + salary
        raw["title"] = job.get("position")
        raw["location"] = job.get("location") or "Remote"
        raw["url"] = job.get("url") or job.get("apply_url") or ""
        raw["posted_date"] = job.get("epoch") or job.get("date")
        out.append(normalize_job(raw, "remoteok"))
    return out


def fetch_remoteok(keywords, max_jobs: int = 20) -> list[dict]:
    """Fetch jobs from RemoteOK matching ``keywords``. Returns [] on any failure."""
    try:
        payload = net.polite_get_json(API_URL)
    except net.FetchBlocked as exc:
        logger.warning("RemoteOK skipped: {}", exc)
        return []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("RemoteOK request failed: {}", type(exc).__name__)
        return []
    jobs = parse_remoteok(payload, keywords, max_jobs)
    logger.info("RemoteOK: {} matching jobs", len(jobs))
    return jobs
