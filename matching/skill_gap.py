"""Which skills stand between a candidate and a job, and which are worth learning.

``skill_gap`` splits a posting's must-have skills into matched and missing.
``near_misses`` keeps the jobs that are only a few skills short, and
``skills_to_learn`` counts which missing skills would close the most of them.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, List

from generator.jd_insights import split_requirements
from matching.confidence_score import job_text, resume_text
from parser.skills_vocab import canonicalize, find_skills

MIN_MISSING, MAX_MISSING = 1, 3
# Below this many must-have skills a posting says too little to call a job "nearly there".
MIN_REQUIRED_SKILLS = 3
# Vocabulary entries that real postings use as buzzwords or that are false hits ("Series C",
# "excel at"), so they are not counted as something to learn. Seen on 165 real postings,
# where "AI" alone was "missing" from 24 of 47.
NOT_A_GAP = frozenset({"ai", "saas", "c", "r", "excel"})


def candidate_skills(resume: dict) -> set[str]:
    """Known skills found in the resume text plus the ones the candidate added by hand."""
    have = set(find_skills(resume_text(resume or {})))
    for skill in (resume or {}).get("extra_skills") or []:
        s = str(skill).strip()
        if s:
            have.add(canonicalize(s) or s)
    return have


def skill_gap(job: dict, have: Iterable[str]) -> dict:
    """``{"required", "matched", "missing", "nice_missing"}`` for one job.

    Required skills are the posting's must-haves; when the rule-based split finds none,
    every known skill in the posting counts as required."""
    have_low = {str(s).lower() for s in have}
    req = split_requirements(job_text(job or {}))
    must = [s for s in req["must_have"] if s.lower() not in NOT_A_GAP]
    optional = [s for s in req["nice_to_have"] if s.lower() not in NOT_A_GAP]
    required = must or optional
    nice = optional if must else []
    return {
        "required": required,
        "matched": [s for s in required if s.lower() in have_low],
        "missing": [s for s in required if s.lower() not in have_low],
        "nice_missing": [s for s in nice if s.lower() not in have_low],
    }


def is_near_miss(gap: dict, min_missing: int = MIN_MISSING, max_missing: int = MAX_MISSING) -> bool:
    """A job is "nearly there" when it names enough skills to judge, the candidate is only
    a few short, and they already have at least as many as they lack."""
    missing, matched = len(gap["missing"]), len(gap["matched"])
    return (len(gap["required"]) >= MIN_REQUIRED_SKILLS and min_missing <= missing <= max_missing
            and matched >= missing)


def near_misses(jobs: Iterable[dict], have: Iterable[str], min_missing: int = MIN_MISSING,
                max_missing: int = MAX_MISSING) -> List[dict]:
    """Jobs that are ``min_missing``..``max_missing`` skills short, each copied with a
    ``gap`` dict attached; fewest missing first, input order otherwise."""
    have = set(have)
    out = []
    for idx, job in enumerate(jobs or []):
        gap = skill_gap(job, have)
        if is_near_miss(gap, min_missing, max_missing):
            out.append((len(gap["missing"]), idx, {**job, "gap": gap}))
    return [job for _, _, job in sorted(out, key=lambda t: (t[0], t[1]))]


def skills_to_learn(near: Iterable[dict], top_n: int = 8) -> List[dict]:
    """Missing skills ranked by how many nearly-there jobs ask for them:
    ``[{"skill", "jobs", "closes"}]`` where ``closes`` counts jobs this skill alone completes."""
    wanted: Counter = Counter()
    closes: Counter = Counter()
    for job in near or []:
        missing = job["gap"]["missing"]
        for skill in missing:
            wanted[skill] += 1
            if len(missing) == 1:
                closes[skill] += 1
    ranked = sorted(wanted.items(), key=lambda kv: (-kv[1], -closes[kv[0]], kv[0].lower()))
    return [{"skill": s, "jobs": n, "closes": closes[s]} for s, n in ranked[:top_n]]


__all__ = ["candidate_skills", "skill_gap", "is_near_miss", "near_misses", "skills_to_learn",
           "MIN_MISSING", "MAX_MISSING"]
