"""Remotive public JSON API (free, no auth): remote jobs.

API: GET https://remotive.com/api/remote-jobs?search=... -> {"jobs": [...]}
Remotive asks API users to link back to the job URL, credit Remotive as the source and
keep to a few requests a day (listings are delayed 24 hours).
"""
from __future__ import annotations

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

API_URL = "https://remotive.com/api/remote-jobs"


def _tags(job: dict) -> list[str]:
    return [str(t) for t in (job.get("tags") or [])]


def parse_remotive(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize a Remotive API payload (pure function, used by tests)."""
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("title") or ""), " ".join(_tags(j) + [str(j.get("category") or "")]),
        html_to_text(str(j.get("description") or ""))))
    out: list[dict] = []
    for job in picked:
        desc = html_to_text(str(job.get("description") or ""))
        if _tags(job):
            desc = f"{desc}\n\nTags: {', '.join(_tags(job))}".strip()
        if job.get("salary"):
            desc += f"\nSalary: {job['salary']}"
        out.append(normalize_job({
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": job.get("candidate_required_location") or "Remote",
            "description": desc,
            "url": job.get("url") or "",
            "posted_date": job.get("publication_date"),
        }, "remotive"))
    return out


def fetch_remotive(keywords, max_jobs: int = 20) -> list[dict]:
    """Fetch jobs from Remotive matching ``keywords``. Returns [] on any failure."""
    search = " ".join(net.keyword_terms(keywords))
    try:
        payload = net.polite_get_json(API_URL, params={"search": search} if search else None)
    except net.FetchBlocked as exc:
        logger.warning("Remotive skipped: {}", exc)
        return []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Remotive request failed: {}", type(exc).__name__)
        return []
    jobs = parse_remotive(payload, keywords, max_jobs)
    logger.info("Remotive: {} matching jobs", len(jobs))
    return jobs
