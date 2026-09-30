"""Keyword relevance shared by the API sources, so off-topic roles are dropped.

A keyword term counts when it is in the job title, or is mentioned at least twice in the
description. Tags only add to the ranking: job boards tag generously, and a tag plus one
passing mention in a long description is what let unrelated roles through before. When
the description is only a snippet, one mention or a tag is enough.
"""
from __future__ import annotations

import math
import re
from typing import Callable, Iterable

from scraper import net

TITLE_WEIGHT, TAG_WEIGHT, DESC_WEIGHT = 3, 2, 1
PHRASE_BONUS = 100
MIN_DESC_MENTIONS = 2
SHORT_DESC_CHARS = 400  # below this the description is a snippet, so trust the tags
_DEV_WORDS = {"developer", "engineer", "programmer"}
_DEV_TITLE_RE = re.compile(r"\b(developers?|engineers?|programmers?|dev|swe|sde|full[- ]?stack|"
                           r"backend|back[- ]end|frontend|front[- ]end)\b")


def _count(term: str, text: str) -> int:
    return len(re.findall(rf"(?<![a-z0-9+#]){re.escape(term)}(?![a-z0-9+#])", text))


def relevance(keywords: str, title: str, tags: str = "", description: str = "") -> int:
    """Score a job against ``keywords``; 0 means off-topic. No keywords => everything is 1."""
    terms = net.keyword_terms(keywords)
    if not terms:
        return 1
    title_l, tags_l, desc_l = (title or "").lower(), (tags or "").lower(), (description or "").lower()
    short = len(desc_l) < SHORT_DESC_CHARS
    # "python developer" asks for a developer: a job that only mentions python in its
    # description must at least have a developer/engineer title.
    wants_dev = any(w in _DEV_WORDS for w in (keywords or "").lower().split())
    role_ok = not wants_dev or _DEV_TITLE_RE.search(title_l) is not None
    score = matched = 0
    for term in terms:
        in_title = bool(_count(term, title_l))
        in_tags = bool(_count(term, tags_l))
        in_desc = _count(term, desc_l) >= (1 if short else MIN_DESC_MENTIONS)
        if not (in_title or ((in_desc or (in_tags and short)) and role_ok)):
            continue
        matched += 1
        score += TITLE_WEIGHT * in_title + TAG_WEIGHT * in_tags + DESC_WEIGHT * in_desc
    # One or two terms must all match; longer queries tolerate a miss.
    required = len(terms) if len(terms) <= 2 else math.ceil(len(terms) * 2 / 3)
    if matched < required:
        return 0
    phrase = " ".join((keywords or "").lower().split())
    if phrase and net.contains_term(phrase, title_l):
        score += PHRASE_BONUS
    return score


def select_relevant(items: Iterable, keywords: str, max_jobs: int,
                    fields: Callable[[dict], tuple[str, str, str]]) -> list:
    """Keep relevant ``items`` (most relevant first, source order breaks ties), capped at
    ``max_jobs``. ``fields(item)`` returns ``(title, tags, description)`` as plain text."""
    scored = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        title, tags, desc = fields(item)
        if not title:
            continue
        score = relevance(keywords, title, tags, desc)
        if score > 0:
            scored.append((score, idx, item))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [item for _, _, item in scored[:max(0, int(max_jobs))]]
