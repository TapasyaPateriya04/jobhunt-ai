"""Flag sentences in a generated draft that the resume does not back up.

Small local models embellish: they call an intern "seasoned", add years of experience,
invent percentages or name a degree the candidate does not have. These rule-based checks
point at such sentences so the candidate can fix them before sending. They are hints, not
proof: every flag says why, and a clean result does not mean the draft is accurate.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from matching.confidence_score import estimate_candidate_years
from parser.skills_vocab import find_skills

MAX_FLAGS = 8
SENIOR_WORDS = re.compile(
    r"\b(seasoned|veteran|senior|expert|extensive experience|wealth of experience|proven track record|"
    r"decade|many years|years of experience in the industry|industry veteran)\b", re.I)
YEARS_CLAIM = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b", re.I)
PERCENT = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
DEGREES = {
    "master's degree": r"\bmaster'?s\b|\bm\.?\s?tech\b|\bm\.?\s?s\.?\b(?= in)|\bmsc\b",
    "MBA": r"\bmba\b",
    "PhD": r"\bph\.?\s?d\b|\bdoctorate\b",
}
FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I am|my|me)\b", re.I)
EMPLOYER = re.compile(r"\b(?:worked|working|interned|interning|employed|served|my (?:time|role|work|internship))"
                      r"\s+(?:as an? [\w -]{2,40}?\s+)?(?:at|with|for)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", str(text or ""))
    return [" ".join(p.split()) for p in parts if len(p.split()) >= 3]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%.+ ]+", " ", str(text or "").lower()).split())


def candidate_years(resume: dict) -> float:
    try:
        return float(estimate_candidate_years((resume or {}).get("experience") or []))
    except Exception:
        return 0.0


def experience_level(resume: dict) -> str:
    """One sentence on the candidate's real experience, for the prompt."""
    years = candidate_years(resume)
    if years < 1:
        return ("The candidate is early in their career, with under a year of professional experience "
                "(internships). Never describe them as senior, seasoned or an expert.")
    if years < 3:
        return (f"The candidate has about {years:.0f} year{'s' if round(years) != 1 else ''} of professional "
                "experience. Never describe them as senior, seasoned or an expert.")
    return f"The candidate has about {years:.0f} years of professional experience; do not overstate it."


def check_draft(text: str, resume: dict, job: Optional[dict] = None) -> list[dict]:
    """``[{"sentence": ..., "why": ...}]`` for sentences that claim more than the resume shows."""
    resume = resume or {}
    job = job or {}
    source = _norm(" ".join([str(resume.get("raw_text") or ""), str(resume.get("education") or ""),
                             " ".join(map(str, resume.get("skills") or [])),
                             " ".join(map(str, resume.get("extra_skills") or []))]))
    target = _norm(" ".join([str(job.get("company") or ""), str(job.get("title") or ""),
                             str(job.get("description") or "")]))
    have = {s.lower() for s in find_skills(" ".join([str(resume.get("raw_text") or ""),
                                                     " ".join(map(str, resume.get("skills") or [])),
                                                     " ".join(map(str, resume.get("extra_skills") or []))]))}
    have |= {str(s).lower() for s in (resume.get("skills") or []) + (resume.get("extra_skills") or [])}
    years = candidate_years(resume)
    flags: list[dict] = []

    def flag(sentence: str, why: str) -> None:
        for f in flags:
            if f["sentence"] == sentence:
                if why not in f["why"]:
                    f["why"] += " " + why
                return
        if len(flags) < MAX_FLAGS:
            flags.append({"sentence": sentence, "why": why})

    for sentence in _sentences(text):
        first_person = bool(FIRST_PERSON.search(sentence))
        low = sentence.lower()
        senior = SENIOR_WORDS.search(sentence)
        if senior and years < 3 and first_person:
            flag(sentence, f'Says "{senior.group(0)}", but your resume shows about {years:.1f} years of experience.')
        for match in YEARS_CLAIM.finditer(sentence):
            claimed = float(match.group(1))
            if first_person and claimed > years + 0.5 and not re.search(r"\b(?:you|your|the role|requires?)\b", low):
                flag(sentence, f"Claims {match.group(0)}, but your resume shows about {years:.1f} years.")
        for match in PERCENT.finditer(sentence):
            figure = _norm(match.group(0)).replace(" ", "")
            if figure not in source.replace(" ", ""):
                flag(sentence, f"The figure {match.group(0)} is not on your resume.")
        for degree, pattern in DEGREES.items():
            if first_person and re.search(pattern, low) and not re.search(pattern, source):
                flag(sentence, f"Mentions a {degree}, which your resume does not list.")
        for match in EMPLOYER.finditer(sentence):
            words = match.group(1).rstrip(".,;:'").split()
            while len(words) > 1 and words[-1] in {"I", "We", "My", "Our", "The", "And", "As", "In", "On"}:
                words.pop()  # "at Cars24 I built..." names Cars24, not "Cars24 I"
            shown = " ".join(words)
            name = _norm(shown)
            if name and name not in source and name not in target:
                flag(sentence, f'Names "{shown}" as an employer, but it is not on your resume.')
        if first_person and re.search(r"\b(experience|expertise|proficien|skilled|worked|built|used)\w*", low):
            invented = [s for s in find_skills(sentence) if s.lower() not in have]
            if invented:
                flag(sentence, f"Claims experience with {', '.join(invented[:3])}, which your resume does not mention.")
    return flags


__all__ = ["check_draft", "experience_level", "candidate_years"]
