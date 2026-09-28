"""Sanity-check matching on a tiny labeled toy set.

Run: python3 scripts/evaluate_matching.py
Prints per-resume rankings and checks that the job labeled relevant ranks first.
Exit code 1 if any resume's top job isn't one labeled relevant.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from matching.confidence_score import score_jobs  # noqa: E402
from matching.semantic_matcher import backend_name  # noqa: E402

NOW = datetime.now(timezone.utc)

RESUMES = {
    "python_dev": {
        "raw_text": (
            "Backend software engineer with 5 years building Python web services. "
            "Skills: Python, Django, Flask, FastAPI, PostgreSQL, REST APIs, Docker, AWS, "
            "CI/CD, unit testing with pytest, Redis, Celery. Designed microservices and "
            "data pipelines; mentored junior developers."
        ),
        "experience": [
            {"title": "Senior Backend Engineer", "dates": "2021 - Present"},
            {"title": "Software Engineer", "dates": "Jun 2019 – Dec 2020"},
        ],
    },
    "nurse": {
        "raw_text": (
            "Registered nurse (RN) with 6 years of clinical experience in ICU and emergency "
            "departments. Patient assessment, medication administration, BLS/ACLS certified, "
            "electronic health records (Epic), wound care, patient and family education."
        ),
        "experience": [{"title": "ICU Nurse", "start": "2019-03", "end": None},
                       {"title": "ER Nurse", "years": 1}],
    },
    "data_scientist": {
        "raw_text": (
            "Data scientist experienced in machine learning, Python, pandas, scikit-learn, "
            "SQL, statistics, A/B testing, NLP and deep learning with PyTorch. Built "
            "recommendation and churn prediction models; communicated insights to stakeholders."
        ),
        "experience": [{"title": "Data Scientist", "dates": "2022 - Present"}],
    },
}

JOBS = [
    {"id": "py_backend", "title": "Python Backend Developer", "posted_date": NOW - timedelta(hours=5),
     "description": "We need a Python developer with 3+ years of experience in Django or FastAPI, "
                    "PostgreSQL, REST API design, Docker and AWS. Experience with Celery and Redis a plus."},
    {"id": "icu_nurse", "title": "ICU Registered Nurse", "posted_date": (NOW - timedelta(days=2)).isoformat(),
     "description": "Hospital seeks ICU registered nurse, 2+ years acute care experience, BLS and ACLS "
                    "certification, patient assessment and medication administration, Epic EHR."},
    {"id": "ml_engineer", "title": "Machine Learning Scientist", "posted_date": NOW - timedelta(days=10),
     "description": "Build machine learning models with Python, scikit-learn and PyTorch. Strong statistics, "
                    "SQL and experimentation (A/B testing). 2+ years experience in data science and NLP."},
    {"id": "accountant", "title": "Staff Accountant", "posted_date": None,
     "description": "Staff accountant for general ledger, reconciliations, accounts payable, month-end "
                    "close, GAAP, Excel. CPA preferred, 4+ years accounting experience."},
    {"id": "snippet_only", "title": "Junior Django Developer", "snippet": "Python Django REST junior role"},
]

LABELS = {"python_dev": {"py_backend", "snippet_only"}, "nurse": {"icu_nurse"},
          "data_scientist": {"ml_engineer"}}


def main() -> int:
    print(f"semantic backend: {backend_name()}\n")
    failures = 0
    for name, resume in RESUMES.items():
        ranked = score_jobs(resume, JOBS)
        print(f"== {name} ==")
        print(f"  {'job':<14}{'total':>7}{'ats':>7}{'raw':>7}{'exp':>7}{'sem':>7}{'fresh':>7}")
        for j in ranked:
            s = j["scores"]
            mark = "*" if j["id"] in LABELS[name] else " "
            print(f" {mark}{j['id']:<14}{s['total']:>7}{s['ats']:>7}{s['ats_raw']:>7}"
                  f"{s['experience']:>7}{s['semantic']:>7}{s['freshness']:>7}")
        ok = ranked[0]["id"] in LABELS[name]
        failures += not ok
        print(f"  top-1 relevant: {'OK' if ok else 'FAIL'}\n")
    print("ALL OK" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
