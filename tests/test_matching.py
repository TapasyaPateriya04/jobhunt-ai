"""Tests for matching/ (run without sentence-transformers installed)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from matching import ats_scorer, semantic_matcher
from matching.ats_scorer import (
    ats_raw_score, ats_score, blended_ats, calibrate, keyword_gap, skill_coverage,
)
from matching.confidence_score import (
    WEIGHTS, calculate_confidence_score, estimate_candidate_years, experience_score,
    extract_required_years, freshness_score, required_years_for, score_jobs, seniority_years,
)
from matching.semantic_matcher import chunk_text, semantic_score, semantic_scores

PY_RESUME = {
    "raw_text": "Python backend engineer. Django, FastAPI, PostgreSQL, REST APIs, Docker, AWS, "
                "pytest, Redis, Celery. Built microservices and data pipelines.",
    "skills": ["Python", "Django", "Docker"],
    "experience": [{"title": "Backend Engineer", "dates": "2020 - Present"}],
}
PY_JOB = {"title": "Python Developer", "company": "Acme",
          "description": "Python developer with Django or FastAPI, PostgreSQL, REST API design, "
                         "Docker and AWS. 3+ years of experience.",
          "posted_date": datetime.now(timezone.utc) - timedelta(hours=3), "experience_years": None}
NURSE_JOB = {"title": "Registered Nurse", "company": "City Hospital",
             "description": "ICU registered nurse, BLS and ACLS certification, patient assessment, "
                            "medication administration, wound care. 2+ years clinical experience.",
             "posted_date": datetime.now(timezone.utc) - timedelta(hours=3), "experience_years": 2}

SCORE_KEYS = {"total", "ats", "experience", "semantic", "freshness", "ats_raw"}


# ------------------------------------------------------------------ ATS
def test_ats_ranks_relevant_job_higher():
    r = PY_RESUME["raw_text"]
    assert ats_score(r, PY_JOB["description"]) > ats_score(r, NURSE_JOB["description"])


@pytest.mark.parametrize("a,b", [("", ""), ("", "python"), ("python", ""), ("the and of", "a an the"),
                                 (None, "python"), ("!!!", "???")])
def test_ats_empty_and_stopword_text(a, b):
    assert ats_score(a, b) == 0.0
    assert ats_raw_score(a, b) == 0.0


def test_ats_bounds_and_identical_text():
    t = "python django docker kubernetes"
    assert 99.0 <= ats_score(t, t) <= 100.0
    assert 99.0 <= ats_raw_score(t, t) <= 100.0


def test_calibration_monotonic_and_bounded():
    xs = np.linspace(0, 1, 101)
    ys = [calibrate(x) for x in xs]
    assert all(b >= a for a, b in zip(ys, ys[1:]))
    assert ys[0] == 0.0 and ys[-1] <= 100.0
    assert calibrate(-1) == 0.0 and calibrate(5) <= 100.0
    # typical raw resume/JD cosine (0.2) should read as a decent score
    assert 60 <= calibrate(0.2) <= 80


def test_keyword_gap_matched_and_missing():
    gap = keyword_gap("python django docker", "python django kubernetes terraform", top_n=10)
    assert gap == {"matched": ["Python", "Django"], "missing": ["Kubernetes", "Terraform"]}
    assert keyword_gap("python", "") == {"matched": [], "missing": []}
    gap2 = keyword_gap("", "python java")
    assert gap2["matched"] == [] and set(gap2["missing"]) == {"Python", "Java"}


def test_keyword_gap_lists_skills_first_and_drops_filler():
    jd = ("Join our team! We work on great software products. https://example.com/apply "
          "You will build Spring Boot microservices and React dashboards for logistics "
          "customers, with Kafka and PostgreSQL. Logistics domain knowledge is a plus.")
    gap = keyword_gap("Java, Spring Boot, React, MongoDB. Built microservices.", jd, top_n=8)
    assert gap["matched"][:3] == ["Spring Boot", "Microservices", "React"]
    assert gap["missing"][:2] == ["Kafka", "PostgreSQL"]
    listed = [t.lower() for t in gap["matched"] + gap["missing"]]
    assert "logistics" in listed  # a real domain term still fills the remaining slots
    assert not {"team", "work", "software", "https", "products", "join"} & set(listed)
    assert len(listed) <= 8


def test_skill_coverage_and_blend():
    have = {"Java", "Spring Boot", "React"}
    assert skill_coverage(have, "Java, Spring Boot, Kafka and AWS") == 50.0
    assert skill_coverage(have, "Java and teamwork") is None  # too few skills named to judge
    assert skill_coverage(set(), "Java, Spring Boot, Kafka") == 0.0
    assert blended_ats(40.0, None) == 40.0 and blended_ats(40.0, 80.0) == 60.0
    s = calculate_confidence_score({"raw_text": "Java Spring Boot React developer"},
                                   {"title": "Java Developer", "description": "Java, Spring Boot, Kafka, AWS"})
    assert s["skill_coverage"] == 50.0


# ------------------------------------------------------------------ semantic
def test_semantic_fallback_active_and_ranks(monkeypatch):
    # Force the TF-IDF fallback even when sentence-transformers is installed locally.
    monkeypatch.setattr(semantic_matcher, "_model", None)
    monkeypatch.setattr(semantic_matcher, "_model_failed", True)
    assert semantic_matcher.get_model() is None
    r = PY_RESUME["raw_text"]
    s_py, s_nurse = semantic_score(r, PY_JOB["description"]), semantic_score(r, NURSE_JOB["description"])
    assert 0 <= s_nurse < s_py <= 100


def test_semantic_empty_inputs():
    assert semantic_score("", "python") == 0.0
    assert semantic_score("python", "") == 0.0
    assert semantic_scores("python", []) == []


def test_semantic_large_batch_uses_lsa_and_stays_bounded():
    jobs = [PY_JOB["description"], NURSE_JOB["description"]] * 12
    scores = semantic_scores(PY_RESUME["raw_text"], jobs)
    assert len(scores) == 24 and all(0 <= s <= 100 for s in scores)
    assert scores[0] > scores[1]


def test_chunk_text_windows():
    words = [f"w{i}" for i in range(600)]
    chunks = chunk_text(" ".join(words), size=256, overlap=32)
    assert len(chunks) == 3
    assert all(len(c.split()) <= 256 for c in chunks)
    assert chunks[-1].split()[-1] == "w599"  # nothing truncated
    assert chunk_text("") == []


def test_embedding_path_with_fake_model(monkeypatch):
    class FakeModel:
        calls = 0

        def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
            FakeModel.calls += 1
            vecs = np.array([[t.count("python"), t.count("nurse"), 0.1 + t.count("filler")]
                             for t in texts], float)
            return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    monkeypatch.setattr(semantic_matcher, "_model", FakeModel())
    long_resume = " ".join(["python"] * 300 + ["filler"] * 300)
    s = semantic_scores(long_resume, ["python code", "nurse care"])
    assert s[0] > s[1] and all(0 <= x <= 100 for x in s)
    assert FakeModel.calls == 3  # resume encoded once for the batch


# ------------------------------------------------------------------ freshness
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("hours,expected", [(1, 100), (24, 100), (30, 85), (72, 85), (100, 70),
                                            (168, 70), (200, 50), (336, 50), (400, 30), (-5, 100)])
def test_freshness_buckets(hours, expected):
    assert freshness_score(NOW - timedelta(hours=hours), now=NOW) == expected


def test_freshness_input_types():
    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None)
    assert freshness_score(naive, now=NOW) == 100
    ist = timezone(timedelta(hours=5, minutes=30))
    assert freshness_score((NOW - timedelta(hours=50)).astimezone(ist), now=NOW) == 85
    assert freshness_score("2026-09-27T20:00:00Z", now=NOW) == 100
    assert freshness_score("2026-09-20", now=NOW) == 50
    assert freshness_score(date(2026, 1, 1), now=NOW) == 30
    assert freshness_score((NOW - timedelta(hours=1)).timestamp(), now=NOW) == 100
    for unknown in (None, "", "yesterday-ish", object()):
        assert freshness_score(unknown, now=NOW) == 50
    assert freshness_score(datetime.utcnow() - timedelta(days=4)) == 70  # default now, naive input


# ------------------------------------------------------------------ experience
def test_candidate_years_from_entries():
    now = datetime(2026, 9, 1)
    assert estimate_candidate_years([{"dates": "2021 - Present"}], now=now) == pytest.approx(5.7, abs=0.1)
    assert estimate_candidate_years([{"dates": "Jan 2019 – Dec 2020"}]) == pytest.approx(2.0, abs=0.1)
    assert estimate_candidate_years([{"start": "2018-06", "end": "2020-05"}]) == pytest.approx(2.0, abs=0.1)
    assert estimate_candidate_years([{"years": 3}, {"years": "1.5 yrs"}]) == 4.5
    # overlapping ranges are not double-counted
    assert estimate_candidate_years([{"dates": "2018 - 2020"}, {"dates": "2019 - 2020"}]) == 3.0
    # no dates -> 1 per entry (SPEC proxy)
    assert estimate_candidate_years([{"title": "a"}, {"title": "b"}, "c"]) == 3
    assert estimate_candidate_years([]) == 0 and estimate_candidate_years(None) == 0


@pytest.mark.parametrize("text,expected", [
    ("Requires 3+ years of experience in Python", 3), ("2-4 years experience", 2),
    ("at least 5 years in backend", 5), ("minimum of 7 yrs", 7), ("5 yrs exp with AWS", 5),
    ("Founded 10 years ago. 4+ years experience needed", 4), ("No experience needed", None), ("", None),
])
def test_extract_required_years(text, expected):
    assert extract_required_years(text) == expected


def test_experience_score():
    assert experience_score(5, 3) == 100
    assert experience_score(3, 4) == 80   # 20 points per missing year
    assert experience_score(1, 4) == 40
    assert experience_score(0.7, 1) == pytest.approx(94)
    assert experience_score(0.7, 8) == 0  # far out of reach, no floor
    assert experience_score(0, 0) == 100
    assert experience_score([], None) == 70  # unknown requirement is neutral
    # A junior candidate can now tell a 1-year ask from an 8-year ask.
    assert experience_score(0.7, 1) > experience_score(0.7, 3) > experience_score(0.7, 8)


@pytest.mark.parametrize("title, description, expected", [
    ("Senior Software Engineer", "", 5), ("Sr. Backend Developer", "", 5),
    ("Lead Frontend Engineer", "", 7), ("Staff Engineer", "", 7),
    ("Principal Engineer", "", 10), ("Senior Principal AI Engineer", "", 10),
    ("Junior Frontend Engineer", "", 0), ("Software Engineering Intern", "", 0),
    ("Associate Software Engineer", "", 1), ("Werkstudent Full-Stack", "", 0),
    ("Software Engineer", "We prefer current and recent undergraduates.", 0),
    ("Software Engineer", "Build things.\n\nLevel: Mid Level", 3),
    ("Software Engineer", "Build things.\n\nLevel: Senior Level", 5),
    ("Software Engineer", "Build things with Java.", None),
    ("Leadership Coach", "", None),  # "lead" must be a whole word
])
def test_seniority_years(title, description, expected):
    assert seniority_years({"title": title, "description": description}) == expected


def test_required_years_prefers_stated_number_over_seniority():
    assert required_years_for({"title": "Senior Engineer", "description": "3+ years of experience"}) == 3
    assert required_years_for({"title": "Senior Engineer", "description": "Great team."}) == 5
    assert required_years_for({"title": "Engineer", "experience_years": 2, "description": "Senior"}) == 2
    assert required_years_for({"title": "Engineer", "description": "Great team."}) is None


def test_ranking_metrics():
    from matching.evaluation import metrics, ndcg_at_k, precision_at_k, weighted_total

    labels = [2, 0, 1, 0, 0, 2]
    assert precision_at_k(labels, 5) == 0.4 and precision_at_k(labels, 5, threshold=2) == 0.2
    assert precision_at_k([], 5) == 0.0
    assert ndcg_at_k([2, 2, 1, 0, 0, 0]) == 1.0 and 0 < ndcg_at_k(labels) < 1 and ndcg_at_k([0, 0]) == 0.0
    m = metrics([{"label": x} for x in labels])
    assert (m["n"], m["good"], m["partial"], m["p_at_5"]) == (6, 2, 1, 0.4)
    total = weighted_total({"ats": 1.0, "semantic": 1.0})
    assert total({"ats": 40, "semantic": 60, "experience": 100, "freshness": 100}) == 50


# ------------------------------------------------------------------ confidence / score_jobs
def test_confidence_keys_bounds_and_weights():
    s = calculate_confidence_score(PY_RESUME, PY_JOB)
    assert SCORE_KEYS <= set(s)
    for k in SCORE_KEYS:
        assert 0 <= s[k] <= 100
    expected = sum(WEIGHTS[k] * s[k] for k in WEIGHTS)
    assert s["total"] == pytest.approx(expected, abs=0.2)
    assert s["ats"] >= s["ats_raw"]  # calibration lifts low raw cosines
    assert s["required_years"] == 3  # parsed from description


def test_python_job_ranks_above_nurse_job():
    ranked = score_jobs(PY_RESUME, [NURSE_JOB, PY_JOB])
    assert [j["title"] for j in ranked] == ["Python Developer", "Registered Nurse"]
    assert ranked[0]["scores"]["total"] > ranked[1]["scores"]["total"]
    assert "scores" not in NURSE_JOB  # input not mutated


def test_missing_fields_do_not_crash():
    sparse_job = {"title": "Python Django Developer", "snippet": "REST APIs with Django"}
    s = calculate_confidence_score({"raw_text": "Python Django developer"}, sparse_job)
    assert s["ats"] > 0 and s["freshness"] == 50
    assert set(calculate_confidence_score({}, {})) >= SCORE_KEYS
    # resume without raw_text uses skills/summary/experience text
    s2 = calculate_confidence_score({"skills": ["python", "django"], "summary": "backend dev",
                                     "experience": [{"title": "dev", "bullets": ["built REST APIs"]}]},
                                    PY_JOB)
    assert s2["ats"] > 0
    assert score_jobs(PY_RESUME, []) == [] and score_jobs(PY_RESUME, None) == []


def test_score_jobs_sorted_desc_batch():
    jobs = [NURSE_JOB, PY_JOB, {"title": "Accountant", "description": "GAAP ledger reconciliations"}, {}]
    ranked = score_jobs(PY_RESUME, jobs)
    totals = [j["scores"]["total"] for j in ranked]
    assert totals == sorted(totals, reverse=True) and len(ranked) == 4
    assert ranked[0]["title"] == "Python Developer"


# ------------------------------------------------------------------ skill gap / suggestions
def test_skill_gap_near_misses_and_skills_to_learn():
    from matching.skill_gap import candidate_skills, is_near_miss, near_misses, skill_gap, skills_to_learn

    resume = {"raw_text": "Java, Spring Boot, React, MySQL, Git.", "extra_skills": ["docker", "Figma"]}
    have = candidate_skills(resume)
    assert {"Java", "Spring Boot", "React", "MySQL", "Git", "Docker", "Figma"} <= have

    jobs = [
        {"id": "two_short", "description": "Requirements: Java, Spring Boot, React, Kafka and AWS."},
        {"id": "one_short", "description": "We use Java, Spring Boot, MySQL and Kafka. Kubernetes is a plus."},
        {"id": "full", "description": "Java, Spring Boot, React, Docker."},
        {"id": "far", "description": "Python, Django, AWS, Kubernetes, Terraform, Kafka, Go."},
        {"id": "mostly_missing", "description": "Java, Rust, Go, Scala."},      # has 1, lacks 3
        {"id": "too_vague", "description": "Java and Kafka."},                   # too few skills to judge
    ]
    gap = skill_gap(jobs[1], have)
    assert gap["missing"] == ["Kafka"] and gap["nice_missing"] == ["Kubernetes"]
    assert gap["matched"] == ["Java", "Spring Boot", "MySQL"]
    assert is_near_miss(gap) and not is_near_miss(skill_gap(jobs[2], have))

    near = near_misses(jobs, have)
    assert [j["id"] for j in near] == ["one_short", "two_short"]  # fewest missing first
    assert near_misses(jobs, have, min_missing=2, max_missing=3)[0]["id"] == "two_short"
    todo = skills_to_learn(near)
    assert todo[0] == {"skill": "Kafka", "jobs": 2, "closes": 1}
    assert todo[1] == {"skill": "AWS", "jobs": 1, "closes": 0}
    assert skills_to_learn([]) == [] and near_misses([], have) == []


def test_hand_added_skills_raise_the_score():
    job = {"title": "Backend Developer", "description": "Java, Spring Boot, Kafka, AWS, Kubernetes."}
    resume = {"raw_text": "Java and Spring Boot developer."}
    before = calculate_confidence_score(resume, job)
    after = calculate_confidence_score({**resume, "extra_skills": ["Kafka", "AWS"]}, job)
    assert before["skill_coverage"] == 40.0 and after["skill_coverage"] == 80.0
    assert after["ats"] > before["ats"] and after["total"] > before["total"]
