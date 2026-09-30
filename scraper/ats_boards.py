"""Company career pages hosted on Greenhouse and Lever, via their public job-board APIs.

Greenhouse: GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
Lever:      GET https://api.lever.co/v0/postings/{company}?mode=json

Both are free, need no key and are meant for listing a company's open roles. Which
companies to read comes from ``GREENHOUSE_BOARDS`` / ``LEVER_COMPANIES`` in ``.env``: the
slug is the last part of the company's careers URL, e.g. ``boards.greenhouse.io/gitlab``
or ``jobs.lever.co/palantir``.
"""
from __future__ import annotations

import html
import re
from typing import Iterable

import requests
from loguru import logger

from config import get_settings
from scraper import net
from scraper.normalizer import html_to_text, normalize_job
from scraper.relevance import select_relevant

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/{}"
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$")


def _valid_slugs(slugs: Iterable[str], source: str) -> list[str]:
    out = []
    for slug in dict.fromkeys(s.strip() for s in (slugs or []) if s and s.strip()):
        if _SLUG_RE.match(slug):
            out.append(slug)
        else:
            logger.warning("{}: ignoring invalid company slug", source)
    return out


def _company_name(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).title()


def _names(items) -> str:
    return " ".join(str(i.get("name") or "") for i in (items or []) if isinstance(i, dict))


# ----------------------------------------------------------------------------- Greenhouse

def _greenhouse_text(job: dict) -> str:
    # ``content`` is HTML that arrives entity-escaped.
    return html_to_text(html.unescape(str(job.get("content") or "")))


def parse_greenhouse(payload, board: str, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize one Greenhouse board payload (pure function, used by tests)."""
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    picked = select_relevant(items, keywords, max_jobs, lambda j: (
        str(j.get("title") or ""), _names(j.get("departments")), _greenhouse_text(j)))
    out: list[dict] = []
    for job in picked:
        location = job.get("location")
        out.append(normalize_job({
            "title": job.get("title"),
            "company": job.get("company_name") or _company_name(board),
            "location": location.get("name") if isinstance(location, dict) else location,
            "description": _greenhouse_text(job),
            "url": job.get("absolute_url") or "",
            "posted_date": job.get("first_published") or job.get("updated_at"),
        }, "greenhouse"))
    return out


# ----------------------------------------------------------------------------- Lever

def _lever_text(job: dict) -> str:
    parts = [str(job.get("descriptionPlain") or "") or html_to_text(str(job.get("description") or ""))]
    for section in job.get("lists") or []:
        if isinstance(section, dict):
            parts.append(f"{section.get('text') or ''}\n{html_to_text(str(section.get('content') or ''))}")
    parts.append(str(job.get("additionalPlain") or ""))
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _lever_categories(job: dict) -> dict:
    return job.get("categories") if isinstance(job.get("categories"), dict) else {}


def parse_lever(payload, company: str, keywords: str = "", max_jobs: int = 20) -> list[dict]:
    """Filter + normalize one Lever postings payload (pure function, used by tests)."""
    if not isinstance(payload, list):
        return []
    picked = select_relevant(payload, keywords, max_jobs, lambda j: (
        str(j.get("text") or ""),
        " ".join(str(_lever_categories(j).get(k) or "") for k in ("team", "department")),
        _lever_text(j)))
    out: list[dict] = []
    for job in picked:
        out.append(normalize_job({
            "title": job.get("text"),
            "company": _company_name(company),
            "location": _lever_categories(job).get("location") or job.get("workplaceType") or "",
            "description": _lever_text(job),
            "url": job.get("hostedUrl") or job.get("applyUrl") or "",
            "posted_date": job.get("createdAt"),
        }, "lever"))
    return out


# ----------------------------------------------------------------------------- fetch

def _fetch_boards(source: str, slugs: list[str], url_tpl: str, params: dict, parse,
                  keywords: str, max_jobs: int, env_name: str) -> list[dict]:
    if not slugs:
        logger.warning("{}: no companies configured; set {} in .env (comma-separated slugs)",
                       source, env_name)
        return []
    jobs: list[dict] = []
    for slug in slugs:
        try:
            payload = net.polite_get_json(url_tpl.format(slug), params=params)
        except net.FetchBlocked as exc:
            logger.warning("{} skipped: {}", source, exc)
            break
        except (requests.RequestException, ValueError) as exc:
            logger.warning("{} request for '{}' failed: {}", source, slug, type(exc).__name__)
            continue
        found = parse(payload, slug, keywords, max_jobs)
        logger.info("{} {}: {} matching jobs", source, slug, len(found))
        jobs.extend(found)
    return jobs[:max_jobs]


def fetch_greenhouse(keywords, max_jobs: int = 20, boards: Iterable[str] | None = None) -> list[dict]:
    """Jobs matching ``keywords`` from the configured Greenhouse boards. [] on failure."""
    slugs = _valid_slugs(get_settings().greenhouse_boards if boards is None else boards, "Greenhouse")
    return _fetch_boards("Greenhouse", slugs, GREENHOUSE_URL, {"content": "true"}, parse_greenhouse,
                         keywords, max_jobs, "GREENHOUSE_BOARDS")


def fetch_lever(keywords, max_jobs: int = 20, companies: Iterable[str] | None = None) -> list[dict]:
    """Jobs matching ``keywords`` from the configured Lever companies. [] on failure."""
    slugs = _valid_slugs(get_settings().lever_companies if companies is None else companies, "Lever")
    return _fetch_boards("Lever", slugs, LEVER_URL, {"mode": "json"}, parse_lever,
                         keywords, max_jobs, "LEVER_COMPANIES")
