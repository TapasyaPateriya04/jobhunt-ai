"""Himalayas remote-jobs API (free, no key needed).

API: GET https://himalayas.app/jobs/api/search?q=<keywords>&country=<country>
     -> {"jobs": [...], "totalCount": ..., "limit": 20}

What the API does (checked live, 2026-10-04):
- Every job is remote. ``locationRestrictions`` lists the countries a job is open to; an
  empty list means worldwide. ``country=India`` returns jobs open to people in India,
  including worldwide ones (552 for "java" that day).
- ``q`` is a keyword search; the shared relevance filter still drops off-topic roles.
- ``seniority`` ("Entry-level", "Mid-level", "Senior", ...) comes with each job and is added
  to the description so the experience score can use it.
- robots.txt allows /jobs/api but disallows ``page=`` URLs, and search ignores ``offset``, so
  one search returns at most 20 jobs (the most relevant). Use more specific keywords for more.
"""
from __future__ import annotations

import re

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

API_URL = "https://himalayas.app/jobs/api/search"
PAGE_SIZE = 20  # one search request; paging would need page=, which robots.txt disallows
_REMOTE_WORDS = {"", "remote", "anywhere", "worldwide", "flexible"}


def country_for(location: str) -> str:
    """The country to ask Himalayas for: "Bangalore, India" -> "India"; remote or empty -> ""."""
    try:
        from matching.location import normalize_country, PLACES
    except Exception:  # matching is optional for scraping
        return ""
    for part in reversed(re.split(r"[;,|/]", location or "")):
        part = part.strip()
        if part.lower() in _REMOTE_WORDS:
            continue
        country = normalize_country(part)
        if country in PLACES:
            return country
    return ""


def _strings(value) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def parse_himalayas(payload, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize one Himalayas search page (pure function, used by tests)."""
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    items = [j for j in items if isinstance(j, dict)]
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("title") or ""), " ".join(_strings(j.get("categories"))),
        html_to_text(str(j.get("description") or ""))))
    out: list[dict] = []
    for job in picked:
        countries = _strings(job.get("locationRestrictions"))
        where = f"Remote ({', '.join(countries[:3])}{', ...' if len(countries) > 3 else ''})" if countries \
            else "Remote (worldwide)"
        desc = html_to_text(str(job.get("description") or ""))
        seniority = ", ".join(_strings(job.get("seniority")))
        if seniority:
            desc = f"{desc}\n\nSeniority: {seniority}".strip()
        out.append(normalize_job({
            "title": job.get("title"),
            "company": job.get("companyName"),
            "location": where,
            "description": desc,
            "url": job.get("applicationLink") or job.get("guid") or "",
            "posted_date": job.get("pubDate"),
        }, "himalayas"))
    return out


def fetch_himalayas(keywords, location: str = "Remote", max_jobs: int = 20) -> list[dict]:
    """Remote jobs matching ``keywords`` that people in ``location``'s country can take.
    Returns [] on any failure."""
    country = country_for(location)
    params = {"q": str(keywords or "").strip()}
    if country:
        params["country"] = country
    try:
        found = parse_himalayas(net.polite_get_json(API_URL, params=params), keywords, max_jobs)
    except net.FetchBlocked as exc:
        logger.warning("Himalayas skipped: {}", exc)
        return []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Himalayas request failed: {}", type(exc).__name__)
        return []
    logger.info("Himalayas ({}): {} matching jobs", country or "worldwide", len(found))
    return found
