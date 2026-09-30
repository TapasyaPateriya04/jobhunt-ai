"""Indeed search results via Playwright + BeautifulSoup (SPEC §5.2, corrected Python).

Experimental: scraping Indeed may violate its ToS and the site sits behind bot protection.
``fetch_rendered_html`` checks robots.txt first and we return [] when disallowed or
blocked; never try to get around a block. Prefer the API sources.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

from scraper.browser import fetch_rendered_html, select_attr, select_text
from scraper.normalizer import normalize_job

BASE_URL = "https://www.indeed.com"


def build_url(keywords: str, location: str) -> str:
    return f"{BASE_URL}/jobs?{urlencode({'q': keywords or '', 'l': location or ''})}"


def parse_indeed_html(html: str, max_jobs: int = 20) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()
    # The two selectors can match the same job twice (a beacon nested in a result), and
    # each job has several tracking URLs, so dedupe on the job key (``jk``).
    for card in soup.select(".job_seen_beacon, .jobsearch-ResultsList .result"):
        if len(jobs) >= max_jobs:
            break
        href = select_attr(card, "href", "a.jcs-JobTitle", "h2.jobTitle a", ".jobTitle a")
        jk = select_attr(card, "data-jk", "a[data-jk]") or "".join(
            parse_qs(urlsplit(href).query).get("jk", [])[:1])
        if jk:
            href = f"/viewjob?{urlencode({'jk': jk})}"
        key = jk or href or select_text(card, ".jobTitle", "h2 a")
        if key in seen:
            continue
        seen.add(key)
        raw = {
            "title": select_text(card, "h2.jobTitle span[title]", ".jobTitle", "h2 a"),
            "company": select_text(card, "[data-testid=company-name]", ".companyName"),
            "location": select_text(card, "[data-testid=text-location]", ".companyLocation"),
            "description": select_text(card, ".job-snippet", "[data-testid=jobsnippet_footer]",
                                       ".underShelfFooter"),
            "posted_date": select_text(card, "[data-testid=myJobsStateDate]", ".date"),
            "url": urljoin(BASE_URL, href) if href else "",
        }
        if raw["title"]:
            jobs.append(normalize_job(raw, "indeed"))
    return jobs


async def scrape_indeed(keywords: str, location: str, max_jobs: int = 20) -> list[dict]:
    html = await fetch_rendered_html(build_url(keywords, location), "Indeed", ".job_seen_beacon")
    return parse_indeed_html(html, max_jobs) if html else []
