"""Job description analysis: required skills, years of experience, top keywords."""
from __future__ import annotations

import re
from collections import Counter

from parser.skills_vocab import find_skills
from scraper.normalizer import extract_experience_years

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each etc every few
for from further had has have having he her here hers him his how i if in into is it its
itself just me more most my no nor not now of off on once only or other our ours out over own
per same she should so some such than that the their theirs them then there these they this
those through to too under until up us very via was we were what when where which while who
whom why will with within without would you your yours
able across ability apply applicant applicants based benefits best candidate candidates
company culture day days description equal employer employment environment experience
full great help ideal including job join just looking make new opportunity plus position
preferred required requirements responsibilities role salary skills strong team teams time
title work working year years yrs well want need needs must include includes like get using
use used build building within across world remote hiring hire us you'll we're you're it's
""".split())

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*(?:\.[A-Za-z0-9]+)*")


def top_keywords(text: str, top_n: int = 20) -> list[str]:
    """Most frequent non-stopword tokens (lowercase), ties broken by first appearance."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    tokens = [t for t in tokens if len(t) > 2 and t not in STOPWORDS] + \
             [t for t in tokens if t in ("c", "r", "go", "c#", "ai", "ml", "ui", "ux", "qa")]
    counts = Counter(tokens)
    first = {}
    for i, t in enumerate(tokens):
        first.setdefault(t, i)
    return [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], first[kv[0]]))[:top_n]]


def analyze_jd(text: str) -> dict:
    """Return ``{"skills", "experience_years", "keywords"}`` for a job description."""
    text = text or ""
    return {
        "skills": find_skills(text),
        "experience_years": extract_experience_years(text),
        "keywords": top_keywords(text),
    }
