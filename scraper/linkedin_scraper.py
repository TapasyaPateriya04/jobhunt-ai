"""LinkedIn public (logged-out) job search via Playwright + BeautifulSoup.

LinkedIn's robots.txt disallows most crawling for generic user agents, so in practice this
returns [] with a logged warning unless robots.txt permits the request. Never log in or
bypass that check.
"""
from __future__ import annotations

from urllib.parse import urlencode

from bs4 import BeautifulSoup

from scraper.browser import fetch_rendered_html, select_attr, select_text
from scraper.normalizer import normalize_job

BASE_URL = "https://www.linkedin.com"


def build_url(keywords: str, location: str) -> str:
    return f"{BASE_URL}/jobs/search?{urlencode({'keywords': keywords or '', 'location': location or ''})}"


def parse_linkedin_html(html: str, max_jobs: int = 20) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[dict] = []
    for card in soup.select(".base-search-card, .base-card, .job-search-card")[:max_jobs]:
        href = select_attr(card, "href", "a.base-card__full-link", "a")
        raw = {
            "title": select_text(card, ".base-search-card__title", "h3"),
            "company": select_text(card, ".base-search-card__subtitle", "h4"),
            "location": select_text(card, ".job-search-card__location"),
            "description": select_text(card, ".job-search-card__snippet", ".base-search-card__metadata"),
            "posted_date": select_attr(card, "datetime", "time")
            or select_text(card, "time", ".job-search-card__listdate"),
            "url": href.split("?")[0] if href else "",
        }
        if raw["title"]:
            jobs.append(normalize_job(raw, "linkedin"))
    return jobs


async def scrape_linkedin(keywords: str, location: str, max_jobs: int = 20) -> list[dict]:
    html = await fetch_rendered_html(build_url(keywords, location), "LinkedIn", ".base-search-card")
    return parse_linkedin_html(html, max_jobs) if html else []
