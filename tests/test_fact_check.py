"""Checks that point at draft sentences claiming more than the resume shows."""
from __future__ import annotations

from generator import cover_letter, resume_optimizer
from generator.fact_check import check_draft, experience_level

RESUME = {
    "raw_text": ("Jane Doe. B.Tech in Computer Science, 2025. Cars24, Java + React intern, Oct 2025 - Apr 2026. "
                 "Built Spring Boot services with 6-role RBAC for 49+ clients; cut onboarding errors by 30%."),
    "skills": ["Java", "Spring Boot", "React", "SQL"],
    "experience": [{"title": "Java Intern", "company": "Cars24", "start": "2025-10", "end": "2026-04", "years": 0.5}],
    "education": "B.Tech in Computer Science, 2025",
}
JOB = {"company": "Celonis", "title": "Associate Software Engineer - Java",
       "description": "Java, Spring Boot, Hibernate and Kubernetes. 2+ years preferred."}


def _why(draft: str) -> str:
    return " ".join(f["why"] for f in check_draft(draft, RESUME, JOB))


def test_honest_draft_has_no_flags():
    draft = ("Dear Hiring Manager,\n\nI am applying for the Associate Software Engineer role at Celonis. "
             "During my internship at Cars24 I built Spring Boot services with 6-role RBAC for 49+ clients "
             "and cut onboarding errors by 30%. The role asks for 2+ years of Java and Kubernetes, "
             "which I am keen to grow into. I hold a B.Tech in Computer Science.")
    assert check_draft(draft, RESUME, JOB) == []


def test_embellishments_are_flagged_with_a_reason():
    assert "seasoned" in _why("As a seasoned engineer, I deliver.")
    assert "Claims 4 years" in _why("I bring 4 years of experience in Java.")
    assert "45%" in _why("I cut costs by 45% in my last role.")
    assert "master's degree" in _why("I hold a Master's degree in Computer Science.")
    assert '"Infosys"' in _why("I worked at Infosys on payments.")
    assert "Kubernetes" in _why("My expertise in Java and Kubernetes will help your team.")


def test_one_sentence_collects_every_reason():
    (flag,) = check_draft("With 3+ years of experience, I cut errors by 50% while I worked at Wipro.", RESUME, JOB)
    assert "3+ years" in flag["why"] and "50%" in flag["why"] and "Wipro" in flag["why"]


def test_talk_about_the_job_is_not_a_claim():
    # Years, skills and the company named for the job are fine when the letter talks about the role.
    assert check_draft("Your team asks for 2+ years of Kubernetes experience at Celonis.", RESUME, JOB) == []


def test_prompts_state_the_real_experience_level():
    assert "under a year" in experience_level(RESUME) and "seasoned" in experience_level(RESUME)
    senior = {**RESUME, "experience": [{"title": "Engineer", "years": 6}]}
    assert "about 6 years" in experience_level(senior)
    assert experience_level(RESUME) in cover_letter.build_cover_letter_prompt(RESUME, JOB)
    assert experience_level(RESUME) in resume_optimizer.build_resume_prompt(RESUME, JOB)
