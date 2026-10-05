import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import requests

from scraper import net
from scraper import hn_scraper, remoteok_scraper, service
from scraper.normalizer import (
    extract_experience_years,
    html_to_text,
    normalize_job,
    parse_posted_date,
)

FIX = Path(__file__).parent / "fixtures"
JOB_KEYS = {"title", "company", "location", "description", "source", "url", "posted_date",
            "experience_years"}


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class _NoWait:
    def wait(self):
        pass

    async def await_turn(self):
        pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Allow all URLs, skip robots/rate-limit delays, and forbid real HTTP by default."""
    monkeypatch.setattr(net, "is_allowed_url", lambda url: True)
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": True)
    monkeypatch.setattr(net, "limiter_for", lambda url: _NoWait())

    def boom(*a, **kw):
        raise AssertionError("real network call attempted")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests, "post", boom)


# ---------------------------------------------------------------- normalizer
def test_normalize_job_contract_and_html():
    job = normalize_job({"position": "Dev", "company_name": "X", "description": "<p>Hi <b>there</b></p>",
                         "apply_url": "https://x.example/j", "epoch": 1_700_000_000}, "test")
    assert set(job) == JOB_KEYS
    assert job["title"] == "Dev" and job["company"] == "X"
    assert job["description"] == "Hi \nthere" or "<" not in job["description"]
    assert job["posted_date"] == datetime(2023, 11, 14, 22, 13, 20)
    assert job["url"] == "https://x.example/j"


def test_normalize_job_defaults_and_bad_url():
    job = normalize_job({"url": "javascript:alert(1)"}, "x")
    assert job["url"] == "" and job["title"] == "Untitled role" and job["posted_date"] is None


@pytest.mark.parametrize("text,years", [
    ("3+ years of Python", 3), ("2-4 yrs experience", 2), ("minimum of 7 years", 7),
    ("five years of experience in Go", 5), ("company founded 30 years ago", None),
    ("", None), ("Need 2+ years Java and 6+ years overall experience", 6),
])
def test_extract_experience_years(text, years):
    assert extract_experience_years(text) == years


def test_extract_experience_years_ignores_company_age():
    text = "Profitable, 18+ yrs stable, employee-owned. You: 5+ yr senior dev who has seen it all."
    assert extract_experience_years(text) == 5


def test_parse_posted_date_variants():
    now = datetime.utcnow()
    assert abs(parse_posted_date("3 days ago") - (now - timedelta(days=3))) < timedelta(minutes=1)
    assert abs(parse_posted_date("Just posted") - now) < timedelta(minutes=1)
    assert parse_posted_date("2026-09-27T12:00:00+00:00") == datetime(2026, 9, 27, 12)
    assert parse_posted_date(1_700_000_000_000) == datetime(2023, 11, 14, 22, 13, 20)
    assert parse_posted_date("gibberish") is None


def test_html_to_text():
    assert html_to_text("<ul><li>a</li><li>b &amp; c</li></ul><script>x()</script>") == "a\nb & c"


# ---------------------------------------------------------------- RemoteOK
def _remoteok_payload():
    return json.loads((FIX / "remoteok_sample.json").read_text(encoding="utf-8"))


def test_parse_remoteok_skips_legal_and_filters():
    jobs = remoteok_scraper.parse_remoteok(_remoteok_payload(), "Python Developer", 10)
    titles = [j["title"] for j in jobs]
    assert titles[0] == "Senior Python Developer"
    assert "Data Engineer" in titles          # mentions Python in description
    assert "Frontend Engineer" not in titles  # no python anywhere
    top = jobs[0]
    assert set(top) == JOB_KEYS and top["source"] == "remoteok"
    assert "<" not in top["description"] and "Tags: python" in top["description"]
    assert top["experience_years"] == 5
    assert top["url"].startswith("https://remoteok.com/")


def test_fetch_remoteok_uses_user_agent_and_caps(monkeypatch):
    calls = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.update(url=url, headers=headers, timeout=timeout)
        return FakeResp(_remoteok_payload())

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = remoteok_scraper.fetch_remoteok("react", max_jobs=1)
    assert len(jobs) == 1 and jobs[0]["company"] == "Globex"
    assert calls["url"] == "https://remoteok.com/api"
    assert "JobHuntAI" in calls["headers"]["User-Agent"]
    assert calls["timeout"]


def test_fetch_remoteok_respects_robots(monkeypatch):
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": False)
    assert remoteok_scraper.fetch_remoteok("python") == []


def test_fetch_remoteok_network_error(monkeypatch):
    def fail(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", fail)
    assert remoteok_scraper.fetch_remoteok("python") == []


# ---------------------------------------------------------------- HN
def test_fetch_hn_whos_hiring(monkeypatch):
    story = json.loads((FIX / "hn_story.json").read_text(encoding="utf-8"))
    comments = json.loads((FIX / "hn_comments.json").read_text(encoding="utf-8"))
    seen = []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append((url, dict(params or {})))
        return FakeResp(story if "search_by_date" in url else comments)

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = hn_scraper.fetch_hn_whos_hiring("Python", max_jobs=5)
    assert seen[0][1]["tags"] == "story,author_whoishiring"
    assert seen[1][1]["tags"] == "comment,story_45000000"
    assert len(jobs) == 2  # the reply comment is ignored
    acme, globex = jobs
    assert acme["company"] == "Acme Robotics"
    assert acme["title"] == "Senior Python Engineer"
    assert "REMOTE" in acme["location"]
    assert acme["experience_years"] == 4
    assert acme["url"] == "https://news.ycombinator.com/item?id=45000101"
    assert acme["source"] == "hn" and isinstance(acme["posted_date"], datetime)
    assert globex["title"] == "Machine Learning Engineer"
    assert globex["location"] == "ONSITE"


def test_fetch_hn_no_story(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **kw: FakeResp({"hits": []}))
    assert hn_scraper.fetch_hn_whos_hiring("python") == []


def test_parse_hn_comment_header_with_links_and_no_role():
    job = hn_scraper.parse_hn_comment({"objectID": "1", "created_at_i": 1790000000, "comment_text": (
        'GovStar | <a href="https:&#x2F;&#x2F;govstar.example">https:&#x2F;&#x2F;govstar.example</a> | '
        "Staff Platform Engineer | Remote (US)<p>We use Python and Go.")})
    assert (job["company"], job["title"], job["location"]) == ("GovStar", "Staff Platform Engineer", "Remote (US)")
    job = hn_scraper.parse_hn_comment({"objectID": "2", "comment_text": (
        "Solution Street | Northern Virginia - HYBRID &amp; ONSITE<p>We are a consulting company.")})
    assert job["company"] == "Solution Street" and job["title"] == "Software role"
    # A candidate's "who wants to be hired" style post is not a job.
    assert hn_scraper.parse_hn_comment({"objectID": "3", "comment_text": (
        "Location: London, UK<p>Remote: Yes<p>Willing to relocate: No<p>Technologies: Python")}) is None


# ---------------------------------------------------------------- service
def _job(title, url="", company="C", source="s"):
    return {"title": title, "company": company, "location": "", "description": "", "source": source,
            "url": url, "posted_date": None, "experience_years": None}


def test_scrape_jobs_fans_out_dedupes_and_caps(monkeypatch):
    a = [_job("A1", "https://x/1"), _job("A2", "https://x/2"), _job("A3")]
    b = [_job("B1", "https://x/1/"), _job("B2"), _job("A3")]
    fns = {"remoteok": lambda kw, loc, n: a[:n], "hn": lambda kw, loc, n: b[:n]}

    def broken(kw, loc, n):
        raise RuntimeError("boom")

    fns["themuse"] = broken
    monkeypatch.setattr(service, "_source_fn", lambda name: fns.get(name))
    jobs = service.scrape_jobs("python", "Remote", 10, ["remoteok", "hn", "themuse", "bogus"])
    assert [j["title"] for j in jobs] == ["A1", "A2", "B2", "A3"]  # interleaved, deduped

    jobs = service.scrape_jobs("python", "Remote", 2, ["remoteok", "hn"])
    assert len(jobs) == 2


def test_scrape_jobs_respects_session_cap(monkeypatch):
    monkeypatch.setenv("MAX_JOBS_PER_SESSION", "3")
    many = [_job(f"J{i}", f"https://x/{i}") for i in range(10)]
    monkeypatch.setattr(service, "_source_fn", lambda name: (lambda kw, loc, n: many[:n]))
    assert len(service.scrape_jobs("python", "Remote", 50, ["remoteok"])) == 3


def test_scrape_jobs_default_sources_end_to_end(monkeypatch):
    story = json.loads((FIX / "hn_story.json").read_text(encoding="utf-8"))
    comments = json.loads((FIX / "hn_comments.json").read_text(encoding="utf-8"))

    def fake_get(url, params=None, headers=None, timeout=None):
        if "remoteok" in url:
            return FakeResp(_remoteok_payload())
        if "themuse" in url or "arbeitnow" in url:
            return FakeResp({"results": [], "data": []})
        return FakeResp(story if "search_by_date" in url else comments)

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = service.scrape_jobs("Python", "Remote", 20)
    sources = {j["source"] for j in jobs}
    assert sources == {"remoteok", "hn"}
    assert len({j["url"] for j in jobs}) == len(jobs)
