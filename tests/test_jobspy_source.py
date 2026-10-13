"""LinkedIn and Naukri via JobSpy: off by default, at most once per refresh interval."""
import sys
import types
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest

from config import Settings
from scraper import jobspy_source as js


@pytest.fixture
def fake_jobspy(monkeypatch):
    calls = []

    def scrape_jobs(**kw):
        calls.append(kw)
        return pd.DataFrame([{
            "site": kw["site_name"][0], "title": "Java Developer", "company": "Acme",
            "location": "Bengaluru, KA, IN", "date_posted": date(2026, 10, 11),
            "job_url": "https://in.linkedin.com/jobs/view/java-developer-at-acme-4012345678?trk=x",
            "job_url_direct": None, "description": "Java, Spring Boot, React. 0-1 years.",
        }, {
            "site": kw["site_name"][0], "title": "React Developer", "company": float("nan"),
            "location": None, "date_posted": pd.NaT, "job_url": "https://www.naukri.com/job-listings-1",
            "job_url_direct": None, "description": float("nan"),
        }])

    monkeypatch.setitem(sys.modules, "jobspy", types.SimpleNamespace(scrape_jobs=scrape_jobs))
    return calls


def _settings(tmp_path, **kw):
    base = Settings(docs_dir=tmp_path, jobspy_sites=("linkedin", "naukri"), candidate_country="India",
                    candidate_cities=("Bangalore",))
    return replace(base, **kw)


def test_off_unless_listed(tmp_path, fake_jobspy):
    s = _settings(tmp_path, jobspy_sites=())
    assert js.fetch_jobspy("linkedin", "java", "India", settings=s) == []
    assert fake_jobspy == []


def test_maps_rows_to_jobs(tmp_path, fake_jobspy):
    jobs = js.fetch_jobspy("linkedin", "java developer", "India", 10, settings=_settings(tmp_path))
    assert [j["source"] for j in jobs] == ["linkedin", "linkedin"]
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert jobs[0]["company"] == "Acme" and jobs[0]["posted_date"] is not None
    assert jobs[1]["company"] == "Unknown company" and jobs[1]["description"] == ""
    kw = fake_jobspy[0]
    assert kw["site_name"] == ["linkedin"] and kw["location"] == "India"
    assert kw["hours_old"] == 72 and kw["results_wanted"] == 10
    assert "proxies" not in kw


def test_waits_between_searches_even_across_restarts(tmp_path, fake_jobspy):
    s = _settings(tmp_path)
    assert js.fetch_jobspy("linkedin", "java", "India", settings=s, now=1000.0)
    assert js.fetch_jobspy("linkedin", "java", "India", settings=s, now=1000.0 + 59 * 60) == []
    assert js.wait_seconds("linkedin", s, now=1000.0 + 59 * 60) == pytest.approx(60)
    assert len(fake_jobspy) == 1
    # A second process reads the same file.
    assert js.fetch_jobspy("linkedin", "java", "India", settings=s, now=1000.0 + 60 * 60)
    assert len(fake_jobspy) == 2
    # Each site has its own wait.
    assert js.fetch_jobspy("naukri", "java", "India", settings=s, now=1000.0 + 60)


def test_failed_search_still_waits(tmp_path, monkeypatch):
    def boom(**kw):
        raise RuntimeError("429")

    monkeypatch.setitem(sys.modules, "jobspy", types.SimpleNamespace(scrape_jobs=boom))
    s = _settings(tmp_path)
    assert js.fetch_jobspy("linkedin", "java", "India", settings=s) == []
    assert js.wait_seconds("linkedin", s) > 0


def test_naukri_gets_a_city(tmp_path, fake_jobspy):
    js.fetch_jobspy("naukri", "java", "India", settings=_settings(tmp_path))
    js.fetch_jobspy("naukri", "java", "Pune", settings=_settings(tmp_path / "b"))
    assert [k["location"] for k in fake_jobspy] == ["Bangalore", "Pune"]


def test_refresh_interval_has_a_floor(monkeypatch, tmp_path):
    from config import get_settings

    monkeypatch.setenv("JOBSPY_REFRESH_MINUTES", "1")
    monkeypatch.setenv("JOBSPY_SITES", "LinkedIn, naukri, indeed")
    s = get_settings(env_file=tmp_path / "none.env")
    assert s.jobspy_refresh_minutes == 30
    assert js.enabled_sites(s) == ("linkedin", "naukri")
