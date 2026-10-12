"""Jobs pasted in by the user (LinkedIn or any site): parsed locally, never fetched."""
import pytest

from scraper import manual_job

LINKEDIN_PASTE = """Java Developer (Fresher)
Acme Software · Bengaluru, Karnataka, India · 2 days ago · 87 applicants
Hybrid  Full-time  Entry level
Apply  Save

About the job
We are hiring freshers with Java, Spring Boot and React. 0-1 years experience.
"""


def test_guess_fields_reads_a_linkedin_posting():
    got = manual_job.guess_fields(LINKEDIN_PASTE)
    assert got["title"] == "Java Developer (Fresher)"
    assert got["company"] == "Acme Software"
    assert got["location"] == "Bengaluru, Karnataka, India"
    assert got["description"].startswith("We are hiring freshers")


def test_guess_fields_without_layout_keeps_whole_text():
    got = manual_job.guess_fields("Backend Engineer\nGreat team, Java and SQL.")
    assert got["title"] == "Backend Engineer"
    assert got["company"] == "" and got["location"] == ""
    assert "Java and SQL" in got["description"]


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/4012345678/?trackingId=abc&refId=x",
    "https://in.linkedin.com/jobs/view/java-developer-at-acme-4012345678",
    "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=java",
])
def test_linkedin_links_are_made_canonical(url):
    assert manual_job.canonical_linkedin_url(url) == "https://www.linkedin.com/jobs/view/4012345678/"


def test_other_links_are_kept():
    url = "https://boards.greenhouse.io/acme/jobs/123"
    assert manual_job.canonical_linkedin_url(url) == url
    assert not manual_job.is_linkedin_url("https://linkedin.com.evil.example/jobs/view/1")


def test_manual_job_typed_fields_win_and_source_is_set():
    job = manual_job.manual_job(LINKEDIN_PASTE, "https://www.linkedin.com/jobs/view/4012345678/?x=1",
                                title="", company="Acme", location="")
    assert job["source"] == "linkedin"
    assert job["company"] == "Acme"
    assert job["title"] == "Java Developer (Fresher)"
    assert job["url"] == "https://www.linkedin.com/jobs/view/4012345678/"
    assert manual_job.manual_job("Some role\ntext")["source"] == "manual"


def test_manual_job_never_touches_the_network(monkeypatch):
    import requests

    def boom(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests.Session, "request", boom)
    manual_job.manual_job(LINKEDIN_PASTE, "https://www.linkedin.com/jobs/view/4012345678/")


def test_search_link_encodes_keywords():
    url = manual_job.linkedin_search_url("Java Developer", "Bangalore, India")
    assert url == ("https://www.linkedin.com/jobs/search/?keywords=Java+Developer"
                   "&location=Bangalore%2C+India")
