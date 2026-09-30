"""Hacker News "Ask HN: Who is hiring?" via the free HN Algolia API.

1. Find the latest monthly story posted by the ``whoishiring`` account.
2. Search that story's comments for the keywords; top-level comments are job posts.
"""
from __future__ import annotations

import re

import requests
from loguru import logger

from scraper import net
from scraper.normalizer import html_to_text, normalize_job

SEARCH_BY_DATE = "https://hn.algolia.com/api/v1/search_by_date"
SEARCH = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://news.ycombinator.com/item?id={}"

_LOCATION_HINT = re.compile(r"\b(remote|onsite|on-site|hybrid|in[- ]office|relocation)\b", re.I)
_ROLE_HINT = re.compile(
    r"\b(engineer|developer|scientist|designer|manager|analyst|architect|devops|sre|lead|"
    r"intern|founding|programmer|researcher|head of|director|full[- ]?stack|backend|frontend)\b", re.I)
_URL_HINT = re.compile(r"https?://|www\.|\.(com|io|ai|dev|co)\b", re.I)


def find_latest_hiring_story() -> dict | None:
    """Return ``{"id", "title", "created_at_i"}`` of the latest "Who is hiring?" thread."""
    data = net.polite_get_json(SEARCH_BY_DATE, params={
        "tags": "story,author_whoishiring", "query": "who is hiring", "hitsPerPage": 10,
    })
    for hit in (data or {}).get("hits", []):
        title = str(hit.get("title") or "")
        if re.search(r"who\s+is\s+hiring", title, re.I):
            return {"id": str(hit.get("objectID") or hit.get("story_id")), "title": title,
                    "created_at_i": hit.get("created_at_i")}
    return None


def parse_hn_comment(hit: dict) -> dict | None:
    """Turn one Algolia comment hit into a normalized job dict (None if not a job post)."""
    html = str(hit.get("comment_text") or "")
    if not html.strip():
        return None
    text = html_to_text(html)
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    parts = [p.strip() for p in re.split(r"\s+\|\s+|\s+\|\s*|\s*\|\s+", first_line) if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", first_line) if p.strip()]
    if not parts:
        return None
    company = re.sub(r"\s*\(.*?\)\s*$", "", parts[0])[:120]
    rest = parts[1:]
    title = next((p for p in rest if _ROLE_HINT.search(p) and not _URL_HINT.search(p)), "")
    if not title:
        title = next((p for p in rest if not _LOCATION_HINT.search(p) and not _URL_HINT.search(p)
                      and not re.search(r"\$|€|£|\d+k", p, re.I)), "Software role")
    location = next((p for p in rest if _LOCATION_HINT.search(p) and p != title), "")
    if not location:
        location = next((p for p in rest if p not in (title,) and not _URL_HINT.search(p)
                         and re.match(r"^[A-Z][A-Za-z .,/()-]{1,60}$", p) and p != company), "")
    raw = {
        "title": title[:200],
        "company": company or str(hit.get("author") or "HN poster"),
        "location": location[:200],
        "description": text,
        "url": ITEM_URL.format(hit.get("objectID")),
        "posted_date": hit.get("created_at_i") or hit.get("created_at"),
    }
    return normalize_job(raw, "hn")


def fetch_hn_whos_hiring(keywords, max_jobs: int = 20) -> list[dict]:
    """Search the latest "Who is hiring?" thread for ``keywords``. Returns [] on failure."""
    try:
        story = find_latest_hiring_story()
        if not story:
            logger.warning("HN: could not find a 'Who is hiring?' story")
            return []
        story_id = story["id"]
        queries = [(keywords or "").strip()]
        terms = net.keyword_terms(keywords)
        if terms and " ".join(terms) != queries[0]:
            queries.append(" ".join(terms))
        queries += [t for t in terms if t not in queries]
        jobs: list[dict] = []
        seen: set[str] = set()
        for q in queries:
            if len(jobs) >= max_jobs:
                break
            data = net.polite_get_json(SEARCH, params={
                "tags": f"comment,story_{story_id}", "query": q,
                "hitsPerPage": min(100, max(20, max_jobs * 2)),
            })
            for hit in (data or {}).get("hits", []):
                # Only top-level comments are job postings; replies are discussion.
                if str(hit.get("parent_id")) != str(story_id):
                    continue
                oid = str(hit.get("objectID"))
                if oid in seen:
                    continue
                job = parse_hn_comment(hit)
                if job:
                    seen.add(oid)
                    jobs.append(job)
                if len(jobs) >= max_jobs:
                    break
            if len(queries) > 1 and q == queries[0] and len(jobs) >= max_jobs // 2:
                break
        logger.info("HN Who's Hiring ({}): {} jobs", story.get("title"), len(jobs))
        return jobs[:max_jobs]
    except net.FetchBlocked as exc:
        logger.warning("HN skipped: {}", exc)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.warning("HN request failed: {}", type(exc).__name__)
    return []
