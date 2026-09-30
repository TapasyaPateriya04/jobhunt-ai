"""Arbeitnow public job board API (free, no auth): mostly Europe, many remote roles.

API: GET https://www.arbeitnow.com/api/job-board-api -> {"data": [...], "links": ..., "meta": ...}
"""
from __future__ import annotations

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

API_URL = "https://www.arbeitnow.com/api/job-board-api"


def _tags(job: dict) -> list[str]:
    return [str(t) for t in (job.get("tags") or [])]


def parse_arbeitnow(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize an Arbeitnow API payload (pure function, used by tests)."""
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("title") or ""), " ".join(_tags(j)), html_to_text(str(j.get("description") or ""))))
    out: list[dict] = []
    for job in picked:
        desc = html_to_text(str(job.get("description") or ""))
        if _tags(job):
            desc = f"{desc}\n\nTags: {', '.join(_tags(job))}".strip()
        location = str(job.get("location") or "")
        if job.get("remote"):
            location = f"{location} (Remote)".strip() if location else "Remote"
        out.append(normalize_job({
            "title": job.get("title"),
            "company": job.get("company_name"),
            "location": location,
            "description": desc,
            "url": job.get("url") or "",
            "posted_date": job.get("created_at"),
        }, "arbeitnow"))
    return out


def fetch_arbeitnow(keywords, max_jobs: int = 20) -> list[dict]:
    """Fetch jobs from Arbeitnow matching ``keywords``. Returns [] on any failure."""
    try:
        payload = net.polite_get_json(API_URL)
    except net.FetchBlocked as exc:
        logger.warning("Arbeitnow skipped: {}", exc)
        return []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Arbeitnow request failed: {}", type(exc).__name__)
        return []
    jobs = parse_arbeitnow(payload, keywords, max_jobs)
    logger.info("Arbeitnow: {} matching jobs", len(jobs))
    return jobs
