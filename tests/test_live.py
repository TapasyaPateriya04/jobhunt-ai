"""Opt-in smoke tests against the real job sources. Never run by default or in CI.

    python -m pytest -m live -v

They make a handful of polite requests (robots.txt checked, rate limited) and only assert
the shape of what comes back, so a quiet day on a job board does not fail them. A failure
here usually means a site changed its API or started blocking us.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from scraper import net
from scraper.arbeitnow_scraper import fetch_arbeitnow
from scraper.ats_boards import fetch_greenhouse, fetch_lever
from scraper.hn_scraper import fetch_hn_whos_hiring
from scraper.muse_scraper import fetch_muse
from scraper.remoteok_scraper import fetch_remoteok

pytestmark = pytest.mark.live

JOB_KEYS = {"title", "company", "location", "description", "source", "url", "posted_date",
            "experience_years"}
# Broad keyword so every board has something to return.
KEYWORDS = "engineer"


def _check(jobs: list[dict], source: str) -> None:
    assert jobs, f"{source} returned no jobs for '{KEYWORDS}'"
    assert len(jobs) <= 5
    for job in jobs:
        assert set(job) == JOB_KEYS
        assert job["source"] == source
        assert job["title"] and job["title"] != "Untitled role"
        assert job["url"].startswith("https://")
        assert len(job["description"]) > 50
        assert job["posted_date"] is None or isinstance(job["posted_date"], datetime)


@pytest.mark.parametrize("source, fetch", [
    ("remoteok", lambda: fetch_remoteok(KEYWORDS, max_jobs=5)),
    ("hn", lambda: fetch_hn_whos_hiring(KEYWORDS, max_jobs=5)),
    ("themuse", lambda: fetch_muse(KEYWORDS, "Bangalore, India", max_jobs=5)),
    ("arbeitnow", lambda: fetch_arbeitnow(KEYWORDS, max_jobs=5)),
    ("greenhouse", lambda: fetch_greenhouse(KEYWORDS, max_jobs=5, boards=["gitlab"])),
    ("lever", lambda: fetch_lever(KEYWORDS, max_jobs=5, companies=["palantir"])),
])
def test_api_source_returns_normalized_jobs(source, fetch):
    _check(fetch(), source)


@pytest.mark.parametrize("url", [
    "https://remoteok.com/api",
    "https://hn.algolia.com/api/v1/search",
    "https://www.arbeitnow.com/api/job-board-api",
    "https://www.themuse.com/api/public/jobs",
    "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs",
    "https://api.lever.co/v0/postings/palantir",
    "https://himalayas.app/jobs/api/search?q=java&country=India",
])
def test_api_source_still_allowed_by_robots(url):
    net.check_allowed(url)  # raises FetchBlocked if the site now disallows us
