"""Location fit: can a candidate in a given country take this job?

Cases are trimmed from real postings (HN Who's Hiring, RemoteOK, Arbeitnow, The Muse).
"""
from __future__ import annotations

import pytest

from matching.confidence_score import calculate_confidence_score, score_jobs
from matching.location import (
    ELSEWHERE, LOCAL, MIN_FACTOR, REMOTE, REMOTE_OPEN, RESTRICTED, UNKNOWN, location_factor,
    location_fit, normalize_country,
)


def _job(location="", description="", title="Software Engineer", source="hn"):
    return {"title": title, "location": location, "description": description, "source": source}


@pytest.mark.parametrize("job, status, reason_part", [
    # --- in the candidate's country
    (_job("Bangalore, India"), LOCAL, "India"),
    (_job("Bengaluru"), LOCAL, "India"),
    (_job("Gurgaon, India; Flexible / Remote"), LOCAL, "India"),
    (_job("ONSITE", "Stpkr Technologies | Noida, India (Delhi NCR) | ONSITE | Multiple roles"), LOCAL, "India"),
    # --- remote and open
    (_job("Remote(Everywhere)"), REMOTE_OPEN, "worldwide"),
    (_job("REMOTE (worldwide)"), REMOTE_OPEN, "worldwide"),
    (_job("REMOTE", "Crossref | Head of Infrastructure | REMOTE | We hire anywhere in the world."), REMOTE_OPEN, "worldwide"),
    (_job("Northern America, LATAM, Europe, APAC", "A remote job for developers."), REMOTE_OPEN, "region"),
    (_job("REMOTE", "Acme | Engineer | REMOTE | Full-time. We build tools."), REMOTE, "no restriction"),
    (_job("", "We build tools.", source="remoteok"), REMOTE, "no restriction"),
    # --- remote but restricted
    (_job("REMOTE (US)"), RESTRICTED, "United States"),
    (_job("REMOTE (US-Based Only)"), RESTRICTED, "United States"),
    (_job("Remote, USA"), RESTRICTED, "United States"),
    (_job("REMOTE (US time zones)"), RESTRICTED, "United States"),
    (_job("Remote, PT/ET hours preferred"), RESTRICTED, "United States"),
    (_job("REMOTE", "Apex | Full-Stack Developer | REMOTE | Must reside in the US and be "
                    "authorized to work in the US without sponsorship."), RESTRICTED, "United States"),
    (_job("Fully REMOTE (Poland or Romanian residents only)"), RESTRICTED, "Poland"),
    (_job("REMOTE (AMER or EMEA time zones)"), RESTRICTED, "AMER"),
    (_job("Ireland", "Build the web app.", source="remoteok"), RESTRICTED, "Ireland"),
    (_job("Flexible / Remote; London, United Kingdom", "This role is available remotely anywhere in the UK."),
     RESTRICTED, "United Kingdom"),
    # --- another country
    (_job("London"), ELSEWHERE, "United Kingdom"),
    (_job("New York, NY"), ELSEWHERE, "United States"),
    (_job("HYBRID", "Justworks | Associate Software Engineer | Toronto, Canada | HYBRID"), ELSEWHERE, "Canada"),
    (_job("Berlin, Germany", "We are an international team. English is our working language."), ELSEWHERE, "Germany"),
    # --- language
    (_job("Munich (Remote)", "Wir sind eine Agentur und entwickeln mit dir die Plattform für unsere "
                             "Kunden und Partner. Du arbeitest mit React und Node. Wir bieten dir "
                             "flexible Arbeitszeiten und ein Team, das für die Sache brennt und mit dir wächst.",
          title="Werkstudent Full-Stack Entwicklung (m/w/d)"), RESTRICTED, "German"),
    (_job("Berlin", "Backend work. Requirements: good German and English."), RESTRICTED, "German"),
    # --- nothing to go on
    (_job("", "We build developer tools."), UNKNOWN, "not stated"),
])
def test_location_fit_for_candidate_in_india(job, status, reason_part):
    fit = location_fit(job, "India")
    assert fit["status"] == status, fit
    assert reason_part.lower() in fit["reason"].lower(), fit


def test_location_fit_depends_on_the_candidate():
    us_only = _job("REMOTE (US)")
    assert location_fit(us_only, "United States")["status"] == LOCAL
    assert location_fit(us_only, "USA")["status"] == LOCAL          # aliases are normalised
    assert location_fit(_job("Berlin"), "germany")["status"] == LOCAL
    assert location_fit(_job("Remote (EU)", "Must be based in the EU."), "Germany")["status"] != RESTRICTED
    assert location_fit(_job("Remote (EU)", "Must be based in the EU."), "India")["status"] == RESTRICTED
    # the pronoun "us" is not the country
    assert location_fit(_job("REMOTE", "Acme | REMOTE | Join us and help us grow."), "India")["status"] == REMOTE


def test_preferred_city_is_named():
    fit = location_fit(_job("Bangalore, India"), "India", ["Gurugram", "Bangalore"])
    assert fit == {"status": LOCAL, "score": 100.0, "reason": "In Bangalore"}


def test_no_home_country_means_no_effect():
    fit = location_fit(_job("REMOTE (US)"), "")
    assert fit["score"] == 100.0 and location_factor(fit["score"]) == 1.0
    assert normalize_country("  ") == "" and normalize_country("bengaluru") == "India"
    assert location_factor(0) == MIN_FACTOR and location_factor(None) == 1.0


def test_location_changes_the_ranking():
    resume = {"raw_text": "Java Spring Boot React developer", "experience": [{"years": 1}]}
    desc = "Java, Spring Boot, React, REST APIs. 1+ years of experience."
    india = {"title": "Java Developer", "location": "Bangalore, India", "description": desc, "url": "a"}
    us = {"title": "Java Developer", "location": "REMOTE (US only)", "description": desc, "url": "b"}
    # Without a country the two identical postings tie; with one, the reachable job wins.
    plain = score_jobs(resume, [us, india], country="")
    assert plain[0]["scores"]["total"] == plain[1]["scores"]["total"]
    ranked = score_jobs(resume, [us, india], country="India")
    assert [j["url"] for j in ranked] == ["a", "b"]
    local, blocked = ranked[0]["scores"], ranked[1]["scores"]
    assert local["total"] == local["base_total"] and local["location_status"] == LOCAL
    assert blocked["total"] == pytest.approx(blocked["base_total"] * MIN_FACTOR, abs=0.1)
    assert blocked["location_status"] == RESTRICTED and "United States" in blocked["location_reason"]


def test_home_country_comes_from_settings(monkeypatch):
    job = {"title": "Java Developer", "location": "London", "description": "Java."}
    assert calculate_confidence_score({"raw_text": "Java"}, job)["location_status"] == UNKNOWN
    monkeypatch.setenv("CANDIDATE_COUNTRY", "India")
    assert calculate_confidence_score({"raw_text": "Java"}, job)["location_status"] == ELSEWHERE
    # An explicit "" still switches it off.
    assert calculate_confidence_score({"raw_text": "Java"}, job, country="")["location_score"] == 100.0
