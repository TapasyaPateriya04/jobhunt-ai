"""RemoteOK public JSON API (free, no auth) — the default job source.

API: GET https://remoteok.com/api -> [legal_notice, job, job, ...]
RemoteOK asks API users to link back to the job URL and credit RemoteOK as the source.
"""
from __future__ import annotations

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

API_URL = "https://remoteok.com/api"


def parse_remoteok(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize a RemoteOK API payload (pure function, used by tests)."""
    if not isinstance(payload, list):
        return []
    items = payload[1:] if payload and isinstance(payload[0], dict) and "legal" in payload[0] else payload
    # Most relevant first; API order (newest first) breaks ties.
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("position") or ""), " ".join(str(t) for t in (j.get("tags") or [])),
        html_to_text(str(j.get("description") or ""))))
    out: list[dict] = []
    for job in picked:
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
