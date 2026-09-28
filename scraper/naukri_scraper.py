"""Naukri.com search results via Playwright + BeautifulSoup (scrape slowly; robots checked first)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.browser import fetch_rendered_html, select_attr, select_text
from scraper.normalizer import extract_experience_years, normalize_job

BASE_URL = "https://www.naukri.com"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def build_url(keywords: str, location: str) -> str:
    kw = _slug(keywords) or "software-developer"
    loc = _slug(location)
    if loc and loc not in ("remote", "anywhere", "worldwide"):
        return f"{BASE_URL}/{kw}-jobs-in-{loc}"
    return f"{BASE_URL}/{kw}-jobs"


def parse_naukri_html(html: str, max_jobs: int = 20) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[dict] = []
    for card in soup.select(".srp-jobtuple-wrapper, article.jobTuple, .cust-job-tuple")[:max_jobs]:
        href = select_attr(card, "href", "a.title", ".title a", "a")
        exp_text = select_text(card, ".expwdth", ".exp-wrap", ".experience")
        m = re.search(r"(\d{1,2})\s*(?:-\s*\d{1,2})?\s*Yrs?", exp_text, re.I)
        raw = {
            "title": select_text(card, "a.title", ".title"),
            "company": select_text(card, "a.comp-name", ".comp-name", ".subTitle"),
            "location": select_text(card, ".locWdth", ".loc-wrap", ".location", ".loc"),
            "description": select_text(card, ".job-desc", ".job-description", ".ellipsis"),
            "posted_date": select_text(card, ".job-post-day", ".type br + span", ".jobTupleFooter .type"),
            "url": urljoin(BASE_URL, href) if href else "",
            "experience_years": int(m.group(1)) if m else extract_experience_years(exp_text),
        }
        if raw["title"]:
            jobs.append(normalize_job(raw, "naukri"))
    return jobs


async def scrape_naukri(keywords: str, location: str, max_jobs: int = 20) -> list[dict]:
    html = await fetch_rendered_html(build_url(keywords, location), "Naukri", ".srp-jobtuple-wrapper")
    return parse_naukri_html(html, max_jobs) if html else []
