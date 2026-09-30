"""Remotive, Arbeitnow, Greenhouse and Lever sources plus the shared relevance filter.

Payloads are trimmed copies of real API responses (2026-09-30). No network is used.
"""
from __future__ import annotations

import pytest
import requests

from scraper import ats_boards, net, service
from scraper.arbeitnow_scraper import fetch_arbeitnow, parse_arbeitnow
from scraper.remotive_scraper import fetch_remotive, parse_remotive
from scraper.relevance import relevance, select_relevant

JOB_KEYS = {"title", "company", "location", "description", "source", "url", "posted_date",
            "experience_years"}
LONG = " We build products for customers all over the world and care about quality." * 8


class FakeResp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.content = payload, status, b"{}"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class _NoWait:
    def wait(self):
        pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": True)
    monkeypatch.setattr(net, "limiter_for", lambda url: _NoWait())

    def boom(*a, **kw):
        raise AssertionError("real network call attempted")

    monkeypatch.setattr(requests, "get", boom)
    for name in ("GREENHOUSE_BOARDS", "LEVER_COMPANIES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: False, raising=False)


# ---------------------------------------------------------------- relevance
@pytest.mark.parametrize("title, tags, desc, relevant", [
    ("Senior Python Developer", "", "", True),                           # title hit
    ("Backend Engineer", "", "Python services." + LONG + " More Python.", True),  # 2 mentions
    ("Sr Solutions Architect", "python", "Some Python scripting." + LONG, False),  # tag + 1 mention
    ("Data Analyst", "python sql", "Nice to have: Python." + LONG, False),
    ("Data Engineer", "spark", "Build pipelines in Python and Spark.", True),    # short snippet
    ("Software Engineer", "python", "", True),                            # no description: trust tags
    ("Office Assistant", "", "Python python python." + LONG, False),      # not a developer title
    ("Frontend Engineer", "react", "React and TypeScript." + LONG, False),
])
def test_relevance_python_developer(title, tags, desc, relevant):
    assert (relevance("Python Developer", title, tags, desc) > 0) is relevant


def test_relevance_ranking_and_multi_term():
    exact = relevance("Python Developer", "Python Developer", "python", "")
    title = relevance("Python Developer", "Python Engineer", "python", "")
    body = relevance("Python Developer", "Backend Engineer", "", "python python" + LONG)
    assert exact > title > body > 0
    assert relevance("", "Anything", "", "") == 1
    # Two specific terms must both match; three tolerate one miss.
    assert relevance("python django", "Python Developer", "", "") == 0
    assert relevance("python django", "Python Developer", "", "django django" + LONG) > 0
    assert relevance("python django aws", "Python Django Developer", "", "") > 0
    # No word-prefix false positives, and symbols work.
    assert relevance("java", "JavaScript Developer", "", "") == 0
    assert relevance("c++", "C++ Engineer", "", "") > 0


def test_select_relevant_orders_and_caps():
    items = [{"t": "Backend Engineer", "d": "python python" + LONG}, {"t": "Chef", "d": ""},
             {"t": "Python Developer", "d": ""}, "junk", {"t": "", "d": "python"},
             {"t": "Python Engineer", "d": ""}]
    picked = select_relevant(items, "Python Developer", 2, lambda j: (j["t"], "", j["d"]))
    assert [j["t"] for j in picked] == ["Python Developer", "Python Engineer"]


# ---------------------------------------------------------------- Remotive
REMOTIVE = {"0-legal-notice": "Remotive API Legal Notice", "job-count": 3, "jobs": [
    {"id": 1, "url": "https://remotive.com/remote-jobs/software-dev/python-developer-1",
     "title": "Python Developer", "company_name": "KoboToolbox", "category": "Software Development",
     "tags": ["django", "python"], "job_type": "full_time",
     "publication_date": "2026-09-18T16:43:22", "candidate_required_location": "USA, Canada",
     "salary": "$80k - $100k", "description": "<p>Build <b>Django</b> APIs. 3+ years of experience.</p>"},
    {"id": 2, "url": "https://remotive.com/remote-jobs/software-dev/net-developer-2",
     "title": "Senior .NET Developer", "company_name": "Lemon.io", "category": "Software Development",
     "tags": ["python", "C#"], "publication_date": "2026-09-17T13:22:05",
     "candidate_required_location": "", "description": "<p>C# work, maybe some Python.</p>" + LONG},
    {"id": 3, "url": "https://remotive.com/remote-jobs/support/office-assistant-3",
     "title": "Remote Office Assistant", "company_name": "Acme", "category": "Customer Service",
     "tags": [], "publication_date": "2026-09-16T12:35:28", "description": "<p>Calendars.</p>"},
]}


def test_parse_remotive():
    (job,) = parse_remotive(REMOTIVE, "Python Developer", 10)
    assert set(job) == JOB_KEYS
    assert (job["title"], job["company"], job["source"]) == ("Python Developer", "KoboToolbox", "remotive")
    assert job["location"] == "USA, Canada" and job["experience_years"] == 3
    assert job["posted_date"].year == 2026 and job["url"].startswith("https://remotive.com/")
    assert "<" not in job["description"] and "Tags: django, python" in job["description"]
    assert "Salary: $80k - $100k" in job["description"]
    assert parse_remotive({"jobs": None}) == [] and parse_remotive([]) == []
    assert len(parse_remotive(REMOTIVE, "", 10)) == 3  # no keywords: everything


def test_fetch_remotive_searches_specific_terms_and_skips_robots(monkeypatch):
    calls = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.update(url=url, params=params)
        return FakeResp(REMOTIVE)

    monkeypatch.setattr(requests, "get", fake_get)
    # Remotive serves robots.txt behind a bot challenge; its documented API is exempt.
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": False)
    assert len(fetch_remotive("Python Developer", 5)) == 1
    assert calls == {"url": "https://remotive.com/api/remote-jobs", "params": {"search": "python"}}


def test_robots_exemption_is_only_the_api_prefix(monkeypatch):
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": False)
    net.check_allowed("https://remotive.com/api/remote-jobs")
    for url in ("https://remotive.com/remote-jobs", "https://remoteok.com/api",
                "https://remotive.com.evil.example/api/x"):
        with pytest.raises(net.FetchBlocked):
            net.check_allowed(url)


def test_fetch_api_sources_swallow_network_errors(monkeypatch):
    def fail(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", fail)
    assert fetch_remotive("python") == [] and fetch_arbeitnow("python") == []
    assert ats_boards.fetch_greenhouse("python", boards=["gitlab"]) == []
    assert ats_boards.fetch_lever("python", companies=["palantir"]) == []


# ---------------------------------------------------------------- Arbeitnow
ARBEITNOW = {"data": [
    {"slug": "python-software-engineer-imc-1", "company_name": "IMC", "title": "Python Software Engineer",
     "description": "<p>Trading systems in Python.</p><ul><li>2+ years experience</li></ul>",
     "remote": True, "url": "https://www.arbeitnow.com/jobs/companies/imc/python-software-engineer-1",
     "tags": ["IT", "Python"], "job_types": ["Full time"], "location": "Zug", "created_at": 1790607307},
    {"slug": "vertrieb-2", "company_name": "Beispiel GmbH", "title": "Vertriebsmitarbeiter (m/w/d)",
     "description": "<p>Vertrieb im Außendienst.</p>", "remote": False,
     "url": "https://www.arbeitnow.com/jobs/companies/beispiel/vertrieb-2", "tags": ["Sales"],
     "location": "Berlin", "created_at": 1790600000},
], "links": {}, "meta": {}}


def test_parse_arbeitnow():
    (job,) = parse_arbeitnow(ARBEITNOW, "python", 10)
    assert set(job) == JOB_KEYS and job["source"] == "arbeitnow"
    assert (job["title"], job["company"], job["location"]) == ("Python Software Engineer", "IMC", "Zug (Remote)")
    assert job["experience_years"] == 2 and job["posted_date"].year == 2026
    assert parse_arbeitnow({"data": "nope"}) == [] and parse_arbeitnow(None) == []


# ---------------------------------------------------------------- Greenhouse / Lever
GREENHOUSE = {"jobs": [
    {"id": 11, "title": "Senior Backend Engineer (Python)", "company_name": "GitLab",
     "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/11", "location": {"name": "Remote, Canada"},
     "first_published": "2026-08-19T09:38:27-04:00", "updated_at": "2026-09-01T09:00:00-04:00",
     "departments": [{"id": 1, "name": "Engineering"}], "offices": [],
     "content": "&lt;p&gt;Build agents in &lt;strong&gt;Python&lt;/strong&gt;.&lt;/p&gt;&lt;p&gt;5+ years of experience.&lt;/p&gt;"},
    {"id": 12, "title": "Account Executive", "company_name": "GitLab",
     "absolute_url": "https://job-boards.greenhouse.io/gitlab/jobs/12", "location": {"name": "Remote, US"},
     "first_published": "2026-08-20T09:00:00-04:00", "departments": [{"name": "Sales"}],
     "content": "&lt;p&gt;Sell.&lt;/p&gt;"},
], "meta": {"total": 2}}

LEVER = [
    {"id": "a1", "text": "Backend Software Engineer", "hostedUrl": "https://jobs.lever.co/palantir/a1",
     "applyUrl": "https://jobs.lever.co/palantir/a1/apply", "createdAt": 1790000000000,
     "categories": {"commitment": "Full-time", "location": "London, United Kingdom", "team": "Dev"},
     "workplaceType": "onsite", "descriptionPlain": "Work on Python and Java services.",
     "lists": [{"text": "What we value", "content": "<li>Python experience</li><li>4+ years of experience</li>"}],
     "additionalPlain": "Salary: competitive."},
    {"id": "b2", "text": "Recruiter", "hostedUrl": "https://jobs.lever.co/palantir/b2",
     "createdAt": 1790000000000, "categories": {"location": "New York, NY"}, "descriptionPlain": "Hire."},
]


def test_parse_greenhouse_unescapes_content():
    (job,) = ats_boards.parse_greenhouse(GREENHOUSE, "gitlab", "Python Developer", 10)
    assert set(job) == JOB_KEYS and job["source"] == "greenhouse"
    assert (job["title"], job["company"], job["location"]) == (
        "Senior Backend Engineer (Python)", "GitLab", "Remote, Canada")
    assert "Build agents in" in job["description"] and "<" not in job["description"]
    assert "&lt;" not in job["description"] and job["experience_years"] == 5
    assert job["posted_date"].year == 2026 and job["url"].endswith("/gitlab/jobs/11")
    assert ats_boards.parse_greenhouse({"jobs": None}, "gitlab") == []


def test_parse_lever_joins_sections_and_names_company():
    (job,) = ats_boards.parse_lever(LEVER, "palantir", "python", 10)
    assert set(job) == JOB_KEYS and job["source"] == "lever"
    assert (job["title"], job["company"], job["location"]) == (
        "Backend Software Engineer", "Palantir", "London, United Kingdom")
    assert "What we value" in job["description"] and "Salary: competitive." in job["description"]
    assert job["experience_years"] == 4 and job["posted_date"].year == 2026
    assert ats_boards.parse_lever({"not": "a list"}, "palantir") == []


def test_fetch_boards_reads_each_configured_company(monkeypatch):
    urls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        urls.append((url, params))
        if "unknown-co" in url:
            return FakeResp({}, status=404)
        return FakeResp(GREENHOUSE if "greenhouse" in url else LEVER)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setenv("GREENHOUSE_BOARDS", "gitlab, unknown-co, gitlab, ../etc/passwd")
    monkeypatch.setenv("LEVER_COMPANIES", "palantir")
    jobs = service.scrape_jobs("python", "Remote", 10, ["greenhouse", "lever"])
    assert {j["source"] for j in jobs} == {"greenhouse", "lever"}
    assert urls == [
        ("https://boards-api.greenhouse.io/v1/boards/gitlab/jobs", {"content": "true"}),
        ("https://boards-api.greenhouse.io/v1/boards/unknown-co/jobs", {"content": "true"}),
        ("https://api.lever.co/v0/postings/palantir", {"mode": "json"}),
    ]  # duplicates dropped, path-traversal slug never requested, a 404 board is skipped


def test_fetch_boards_without_config_returns_empty():
    # requests.get raises in this module, so an empty result proves no request was made.
    assert ats_boards.fetch_greenhouse("python") == []
    assert ats_boards.fetch_lever("python") == []


# ---------------------------------------------------------------- service
def test_source_lists_are_consistent():
    assert set(service.DEFAULT_SOURCES).isdisjoint(service.EXPERIMENTAL_SOURCES)
    assert service.EXPERIMENTAL_SOURCES == ["indeed", "linkedin", "naukri"]
    assert all(service._source_fn(name) is not None for name in service.ALL_SOURCES)
    assert service._source_fn("bogus") is None
