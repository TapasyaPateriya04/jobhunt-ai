"""The Muse, Arbeitnow, Greenhouse and Lever sources plus the shared relevance filter.

Payloads are trimmed copies of real API responses (2026-09-30). No network is used.
"""
from __future__ import annotations

import pytest
import requests

from scraper import ats_boards, net, service
from scraper.arbeitnow_scraper import fetch_arbeitnow, parse_arbeitnow
from scraper.muse_scraper import MAX_REQUESTS, fetch_muse, muse_locations, parse_muse
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


# ---------------------------------------------------------------- The Muse
def _muse_job(id_, name, locations, level="Mid Level", contents="<p>Java and Spring Boot. Java APIs.</p>"):
    return {"id": id_, "name": name, "contents": contents, "publication_date": "2026-09-17T10:00:00Z",
            "locations": [{"name": n} for n in locations], "categories": [{"name": "Software Engineering"}],
            "levels": [{"name": level, "short_name": level.split()[0].lower()}],
            "refs": {"landing_page": f"https://www.themuse.com/jobs/acme/job-{id_}"},
            "company": {"id": 1, "short_name": "acme", "name": "Acme"}}


MUSE_PAGE = {"page": 1, "page_count": 50, "total": 1000, "results": [
    _muse_job(1, "Java Developer", ["Bangalore, India", "Chennai, India"], "Senior Level",
              "<div><p>Build <b>Java</b> services.</p><ul><li>5+ years of experience</li></ul></div>"),
    _muse_job(2, "Senior Backend Engineer (Java)", ["Flexible / Remote", "San Francisco, CA"]),
    _muse_job(3, "Account Manager", ["Bangalore, India"], contents="<p>Sell things.</p>"),
]}


def test_muse_locations():
    assert muse_locations("Remote") == muse_locations("") == muse_locations(None) == ["Flexible / Remote"]
    assert muse_locations("Bangalore, India; Gurgaon, India ;Bangalore, India") == [
        "Bangalore, India", "Gurgaon, India"]
    assert muse_locations("Pune, India; remote") == ["Pune, India", "Flexible / Remote"]


def test_muse_locations_expand_a_country_and_fix_spellings():
    assert muse_locations("Bengaluru; Gurugram, India") == ["Bangalore, India", "Gurgaon, India"]
    india = muse_locations("India")
    assert india[0] == "Bangalore, India" and "Noida, India" in india and len(india) == 7
    # With preferred cities (CANDIDATE_CITIES), only the ones The Muse knows are searched.
    assert muse_locations("india", ("Gurugram", "Gurgaon", "Noida", "Delhi", "Bangalore")) == [
        "Gurgaon, India", "Noida, India", "Bangalore, India"]
    assert muse_locations("Berlin, Germany") == ["Berlin, Germany"]  # unknown places pass through


def test_parse_muse():
    jobs = parse_muse(MUSE_PAGE, "Java Developer", 10)
    assert [j["title"] for j in jobs] == ["Java Developer", "Senior Backend Engineer (Java)"]
    job = jobs[0]
    assert set(job) == JOB_KEYS and job["source"] == "themuse" and job["company"] == "Acme"
    assert job["location"] == "Bangalore, India; Chennai, India" and job["experience_years"] == 5
    assert "<" not in job["description"] and job["description"].endswith("Level: Senior Level")
    assert job["url"] == "https://www.themuse.com/jobs/acme/job-1" and job["posted_date"].year == 2026
    assert parse_muse({"results": None}) == [] and parse_muse([]) == []


def test_fetch_muse_filters_city_and_caps_requests(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(dict(params))
        return FakeResp(MUSE_PAGE)

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = fetch_muse("Java Developer", "Bangalore, India; Gurgaon, India", max_jobs=10)
    # The API mixes remote jobs into a city search; only the city's own jobs are kept.
    assert [j["title"] for j in jobs] == ["Java Developer"]
    assert len(calls) == MAX_REQUESTS and {c["category"] for c in calls} == {"Software Engineering"}
    assert [(c["page"], c["location"]) for c in calls[:3]] == [
        (1, "Bangalore, India"), (1, "Gurgaon, India"), (2, "Bangalore, India")]

    calls.clear()
    remote = fetch_muse("Java Developer", "Remote", max_jobs=1)
    assert [j["title"] for j in remote] == ["Java Developer"] and len(calls) == 1  # stops when full
    assert calls[0]["location"] == "Flexible / Remote"


def test_no_source_is_exempt_from_robots(monkeypatch):
    monkeypatch.setattr(net, "can_fetch", lambda url, ua="": False)
    for url in ("https://www.themuse.com/api/public/jobs", "https://remoteok.com/api",
                "https://www.arbeitnow.com/api/job-board-api"):
        with pytest.raises(net.FetchBlocked):
            net.check_allowed(url)
    assert fetch_muse("java") == [] and fetch_arbeitnow("java") == []


def test_fetch_api_sources_swallow_network_errors(monkeypatch):
    def fail(*a, **kw):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "get", fail)
    assert fetch_muse("python") == [] and fetch_arbeitnow("python") == []
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
    jobs = service.scrape_jobs("python", "Remote; London", 10, ["greenhouse", "lever"])
    assert {j["source"] for j in jobs} == {"greenhouse", "lever"}
    assert urls == [
        ("https://boards-api.greenhouse.io/v1/boards/gitlab/jobs", {"content": "true"}),
        ("https://boards-api.greenhouse.io/v1/boards/unknown-co/jobs", {"content": "true"}),
        ("https://api.lever.co/v0/postings/palantir", {"mode": "json"}),
    ]  # duplicates dropped, path-traversal slug never requested, a 404 board is skipped


def test_board_jobs_are_filtered_by_the_search_location():
    gh = {"jobs": [
        {**GREENHOUSE["jobs"][0], "id": 21, "location": {"name": "Bengaluru, India"},
         "absolute_url": "https://job-boards.greenhouse.io/x/jobs/21"},
        {**GREENHOUSE["jobs"][0], "id": 22, "location": {"name": "San Francisco, CA"},
         "absolute_url": "https://job-boards.greenhouse.io/x/jobs/22"},
        {**GREENHOUSE["jobs"][0], "id": 23, "location": {"name": "Gurugram, Haryana"},
         "absolute_url": "https://job-boards.greenhouse.io/x/jobs/23"},
    ]}
    pick = lambda loc: [j["location"] for j in ats_boards.parse_greenhouse(gh, "x", "python", 10, loc)]  # noqa: E731
    assert pick("Bangalore, India") == ["Bengaluru, India"]          # "Bangalore" finds "Bengaluru"
    assert pick("Gurgaon; Bangalore") == ["Bengaluru, India", "Gurugram, Haryana"]
    assert pick("") == ["Bengaluru, India", "San Francisco, CA", "Gurugram, Haryana"]
    assert pick("Indiana") == []                                      # whole words only
    lever = [{**LEVER[0], "categories": {"location": "Toronto", "allLocations": ["Toronto", "Pune, India"]}}]
    assert len(ats_boards.parse_lever(lever, "x", "python", 10, "India")) == 1


def test_one_big_board_cannot_take_the_whole_quota(monkeypatch):
    def board(name, n):
        return {"jobs": [{**GREENHOUSE["jobs"][0], "id": i, "company_name": name,
                          "absolute_url": f"https://job-boards.greenhouse.io/{name}/jobs/{i}"} for i in range(n)]}

    monkeypatch.setattr(requests, "get", lambda url, **k: FakeResp(board("big", 30) if "/big/" in url else board("small", 3)))
    jobs = ats_boards.fetch_greenhouse("python", max_jobs=6, boards=["big", "small"])
    assert [j["company"] for j in jobs] == ["big", "small"] * 3


def test_fetch_boards_without_config_returns_empty():
    # requests.get raises in this module, so an empty result proves no request was made.
    assert ats_boards.fetch_greenhouse("python") == []
    assert ats_boards.fetch_lever("python") == []


# ---------------------------------------------------------------- service
def test_source_lists_are_consistent():
    assert set(service.DEFAULT_SOURCES).isdisjoint(service.BOARD_SOURCES)
    assert not {"indeed", "linkedin", "naukri"} & set(service.ALL_SOURCES)  # sites that block bots
    assert all(service._source_fn(name) is not None for name in service.ALL_SOURCES)
    assert service._source_fn("bogus") is None


# ---------------------------------------------------------------- Himalayas
HIMALAYAS = {"totalCount": 3, "offset": 0, "limit": 20, "jobs": [
    {"title": "SDE I - Backend", "companyName": "Sun King", "locationRestrictions": ["India"],
     "seniority": ["Entry-level"], "categories": ["Backend-Developer"],
     "description": "<p>Build <b>Java</b> and Spring Boot services. 1+ years of experience.</p>",
     "pubDate": 1791000000, "applicationLink": "https://himalayas.app/companies/sun-king/jobs/sde-i-backend-1",
     "guid": "https://himalayas.app/companies/sun-king/jobs/sde-i-backend-1"},
    {"title": "Java Developer", "companyName": "gravity9", "locationRestrictions": [], "seniority": ["Senior"],
     "description": "<p>Java microservices.</p>", "pubDate": "1791000000",
     "guid": "https://himalayas.app/companies/gravity9/jobs/java-developer-2"},
    {"title": "Account Executive", "companyName": "Sun King", "locationRestrictions": ["India"],
     "description": "<p>Sell solar.</p>", "pubDate": 1791000000,
     "guid": "https://himalayas.app/companies/sun-king/jobs/ae-3"},
]}


def test_parse_himalayas_marks_remote_scope_and_seniority():
    from scraper.himalayas_scraper import parse_himalayas

    jobs = parse_himalayas(HIMALAYAS, "Java Developer", 10)
    assert [j["title"] for j in jobs] == ["Java Developer", "SDE I - Backend"]  # sales role dropped
    sde = jobs[1]
    assert set(sde) == JOB_KEYS and sde["source"] == "himalayas"
    assert (sde["company"], sde["location"]) == ("Sun King", "Remote (India)")
    assert "Seniority: Entry-level" in sde["description"] and "<" not in sde["description"]
    assert sde["url"].endswith("sde-i-backend-1") and sde["posted_date"].year == 2026
    assert jobs[0]["location"] == "Remote (worldwide)"
    assert parse_himalayas({"jobs": None}) == [] and parse_himalayas(None) == []


def test_fetch_himalayas_asks_for_the_country_in_one_request(monkeypatch):
    from scraper.himalayas_scraper import country_for, fetch_himalayas

    assert [country_for(x) for x in ("Bangalore, India", "Gurgaon", "Remote", "", "Atlantis")] == [
        "India", "India", "", "", ""]
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, dict(params)))
        return FakeResp(HIMALAYAS)

    monkeypatch.setattr(requests, "get", fake_get)
    jobs = fetch_himalayas("Java Developer", "Bangalore, India", max_jobs=10)
    assert len(jobs) == 2 and calls == [
        ("https://himalayas.app/jobs/api/search", {"q": "Java Developer", "country": "India"})]  # no page=
    calls.clear()
    fetch_himalayas("Java Developer", "Remote", max_jobs=10)
    assert calls[0][1] == {"q": "Java Developer"}  # worldwide
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    assert fetch_himalayas("java", "Remote") == []


def test_arbeitnow_country_sites_map_to_one_url():
    from scraper.arbeitnow_scraper import canonical_url

    urls = ["https://www.arbeitnow.fr/jobs/companies/x/role-1", "https://www.arbeitnow.ch/jobs/companies/x/role-1",
            "https://arbeitnow.co.uk/jobs/companies/x/role-1", "https://www.arbeitnow.com/jobs/companies/x/role-1"]
    assert {canonical_url(u) for u in urls} == {"https://www.arbeitnow.com/jobs/companies/x/role-1"}
    assert canonical_url("https://evil.example/arbeitnow.fr/x") == "https://evil.example/arbeitnow.fr/x"
