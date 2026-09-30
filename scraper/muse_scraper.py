"""The Muse public jobs API (free, no key needed): large company job listings worldwide,
including India.

API: GET https://www.themuse.com/api/public/jobs?page=N&category=...&location=...
     -> {"results": [...], "page_count": ..., "total": ...}   (20 jobs per page)

What the API can and cannot do (checked live, 2026-09-30):
- There is no keyword search, so we read a few pages and filter them ourselves.
- ``location`` must be spelled exactly as The Muse does ("Bangalore, India", not "India"
  or "Bengaluru"). Any location filter also returns "Flexible / Remote" jobs, and an
  unknown location returns only those.
- ``level`` works ("Entry Level", "Internship", ...) but entry-level software jobs in
  Indian cities are nearly absent, so it is not applied; the experience score ranks
  junior-friendly roles higher instead.
- Without a key the limit is 500 requests an hour. We make at most ``MAX_REQUESTS``.
"""
from __future__ import annotations

import re

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

API_URL = "https://www.themuse.com/api/public/jobs"
CATEGORY = "Software Engineering"
REMOTE_LOCATION = "Flexible / Remote"
MAX_REQUESTS = 12
_REMOTE_WORDS = {"", "remote", "anywhere", "worldwide", "flexible", "flexible / remote"}


def muse_locations(location: str) -> list[str]:
    """Split a user location such as "Bangalore, India; Gurgaon, India" into Muse location
    names. Remote-like or empty input becomes "Flexible / Remote"."""
    out: list[str] = []
    for part in re.split(r"\s*[;|]\s*", location or ""):
        name = REMOTE_LOCATION if part.strip().lower() in _REMOTE_WORDS else part.strip()
        if name not in out:
            out.append(name)
    return out or [REMOTE_LOCATION]


def _names(items) -> list[str]:
    return [str(i.get("name") or "") for i in (items or []) if isinstance(i, dict) and i.get("name")]


def parse_muse(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize one Muse API page (pure function, used by tests)."""
    items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("name") or ""), " ".join(_names(j.get("categories"))),
        html_to_text(str(j.get("contents") or ""))))
    out: list[dict] = []
    for job in picked:
        desc = html_to_text(str(job.get("contents") or ""))
        levels = _names(job.get("levels"))
        if levels:
            desc = f"{desc}\n\nLevel: {', '.join(levels)}".strip()
        company = job.get("company") if isinstance(job.get("company"), dict) else {}
        refs = job.get("refs") if isinstance(job.get("refs"), dict) else {}
        out.append(normalize_job({
            "title": job.get("name"),
            "company": company.get("name"),
            "location": "; ".join(_names(job.get("locations"))[:4]),
            "description": desc,
            "url": refs.get("landing_page") or "",
            "posted_date": job.get("publication_date"),
        }, "themuse"))
    return out


def fetch_muse(keywords, location: str = "Remote", max_jobs: int = 20) -> list[dict]:
    """Jobs matching ``keywords`` in ``location`` from The Muse. Returns [] on any failure."""
    locations = muse_locations(location)
    pages = max(1, MAX_REQUESTS // len(locations))
    jobs: dict[str, dict] = {}
    requests_made = 0
    try:
        for page in range(1, pages + 1):
            for loc in locations:
                if requests_made >= MAX_REQUESTS or len(jobs) >= max_jobs:
                    break
                payload = net.polite_get_json(API_URL, params=[
                    ("page", page), ("category", CATEGORY), ("location", loc)])
                requests_made += 1
                if loc != REMOTE_LOCATION and isinstance(payload, dict):
                    # The API mixes remote jobs into every location search; keep the city's.
                    payload = {"results": [j for j in payload.get("results") or []
                                           if isinstance(j, dict) and loc in _names(j.get("locations"))]}
                for job in parse_muse(payload, keywords, max_jobs):
                    jobs.setdefault(job["url"] or f"{job['title']}|{job['company']}", job)
    except net.FetchBlocked as exc:
        logger.warning("The Muse skipped: {}", exc)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("The Muse request failed: {}", type(exc).__name__)
    found = list(jobs.values())[:max_jobs]
    logger.info("The Muse ({}): {} matching jobs from {} requests", "; ".join(locations),
                len(found), requests_made)
    return found
