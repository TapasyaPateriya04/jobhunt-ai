"""Fan out a scrape across sources, dedupe and cap the result."""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import re
from typing import Callable, Iterable

from loguru import logger

from config import get_settings

DEFAULT_SOURCES = ["remoteok", "hn", "themuse", "arbeitnow"]
# Browser scrapers of sites that restrict automated access (robots.txt, bot protection,
# Terms of Service). Never on by default; they usually return nothing.
EXPERIMENTAL_SOURCES = ["indeed", "linkedin", "naukri"]
ALL_SOURCES = DEFAULT_SOURCES + ["greenhouse", "lever"] + EXPERIMENTAL_SOURCES


def _run_async(coro):
    """Run a coroutine from sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _source_fn(name: str) -> Callable[[str, str, int], list[dict]] | None:
    # Imported lazily so an optional scraper never breaks the others.
    if name == "remoteok":
        from scraper.remoteok_scraper import fetch_remoteok
        return lambda kw, loc, n: fetch_remoteok(kw, max_jobs=n)
    if name == "hn":
        from scraper.hn_scraper import fetch_hn_whos_hiring
        return lambda kw, loc, n: fetch_hn_whos_hiring(kw, max_jobs=n)
    if name == "themuse":
        from scraper.muse_scraper import fetch_muse
        return lambda kw, loc, n: fetch_muse(kw, loc, max_jobs=n)
    if name == "arbeitnow":
        from scraper.arbeitnow_scraper import fetch_arbeitnow
        return lambda kw, loc, n: fetch_arbeitnow(kw, max_jobs=n)
    if name == "greenhouse":
        from scraper.ats_boards import fetch_greenhouse
        return lambda kw, loc, n: fetch_greenhouse(kw, max_jobs=n, location=loc)
    if name == "lever":
        from scraper.ats_boards import fetch_lever
        return lambda kw, loc, n: fetch_lever(kw, max_jobs=n, location=loc)
    if name == "indeed":
        from scraper.indeed_scraper import scrape_indeed
        return lambda kw, loc, n: _run_async(scrape_indeed(kw, loc, n))
    if name == "linkedin":
        from scraper.linkedin_scraper import scrape_linkedin
        return lambda kw, loc, n: _run_async(scrape_linkedin(kw, loc, n))
    if name == "naukri":
        from scraper.naukri_scraper import scrape_naukri
        return lambda kw, loc, n: _run_async(scrape_naukri(kw, loc, n))
    return None


def job_key(job: dict) -> str:
    """Dedupe key: URL when present, else a hash of title+company+location."""
    url = (job.get("url") or "").strip().lower().rstrip("/")
    if url:
        return "url:" + url
    basis = "|".join(re.sub(r"\s+", " ", str(job.get(k) or "")).strip().lower()
                     for k in ("title", "company", "location"))
    return "h:" + hashlib.sha256(basis.encode()).hexdigest()


def dedupe_jobs(jobs: Iterable[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for j in jobs:
        k = job_key(j)
        if k not in seen:
            seen.add(k)
            out.append(j)
    return out


def _interleave(lists: list[list[dict]]) -> list[dict]:
    out, i = [], 0
    while any(i < len(lst) for lst in lists):
        for lst in lists:
            if i < len(lst):
                out.append(lst[i])
        i += 1
    return out


def scrape_jobs(keywords: str, location: str = "Remote", max_jobs: int = 20,
                sources: list[str] | None = None) -> list[dict]:
    """Scrape ``sources`` for ``keywords`` and return up to ``max_jobs`` normalized, deduped
    jobs (never more than ``settings.max_jobs_per_session``). A failing source is logged
    and skipped."""
    settings = get_settings()
    cap = max(1, min(int(max_jobs or 1), settings.max_jobs_per_session))
    names = [s.strip().lower() for s in (sources or DEFAULT_SOURCES) if s and s.strip()]
    per_source: list[list[dict]] = []
    for name in dict.fromkeys(names):
        fn = _source_fn(name)
        if fn is None:
            logger.warning("Unknown job source '{}' (choose from {})", name, ", ".join(ALL_SOURCES))
            continue
        if name in EXPERIMENTAL_SOURCES:
            logger.warning("Source {} is experimental: the site restricts automated access, "
                           "so expect few or no results. Personal, low-volume use only.", name)
        try:
            found = fn(keywords, location, cap) or []
        except Exception as exc:  # one bad source must not sink the whole scrape
            logger.warning("Source {} failed: {}", name, type(exc).__name__)
            found = []
        logger.info("{}: {} jobs", name, len(found))
        per_source.append(found)
    jobs = dedupe_jobs(_interleave(per_source))[:cap]
    logger.info("Scraped {} unique jobs (cap {})", len(jobs), cap)
    return jobs
