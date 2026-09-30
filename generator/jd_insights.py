"""Split a job posting's skills into must-have and nice-to-have.

``split_requirements`` is instant and needs no model: skills mentioned after a
"nice to have / preferred / bonus" cue are nice-to-have, the rest must-have.
``analyze_requirements_llm`` asks the LLM for the same split (slow on a local model) and
keeps only skills that really appear in the posting, so the model cannot invent any.
Both return ``{"must_have": [...], "nice_to_have": [...], "source": "rules" | "llm"}``.
"""
from __future__ import annotations

import json
import re

from generator.llm import call_llm
from parser.skills_vocab import canonicalize, find_skills
from security.prompt_guard import wrap_untrusted

JD_CHARS = 4000
MAX_SKILLS = 25

# A line or sentence that starts the optional part of a posting.
_NICE_CUE_RE = re.compile(
    r"nice[- ]to[- ]haves?|good[- ]to[- ]have|bonus(?: points)?|preferred(?: qualifications| skills)?|"
    r"(?:is|are|would be|as) (?:a |an )?(?:big |strong |huge )?plus\b|\ba plus\b|desirable|"
    r"not required|optional(?:ly)?|extra credit|ideally|it would be great|what would be great", re.I)
# A heading that returns to the mandatory part.
_MUST_CUE_RE = re.compile(
    r"^\W*(requirements?|required|must[- ]haves?|what you(?:'ll| will)? (?:need|bring|do)|"
    r"qualifications|minimum qualifications|responsibilities|what we(?:'re| are) looking for|"
    r"about you|who you are|your profile|skills)\b.{0,30}$", re.I)


def split_requirements(jd_text: str) -> dict:
    """Rule-based must-have / nice-to-have split of the known skills in ``jd_text``."""
    must: list[str] = []
    nice: list[str] = []
    optional_block = False
    for raw in re.split(r"\n+", jd_text or ""):
        line = raw.strip()
        if not line:
            continue
        heading = len(line) <= 60 and not line.endswith(".")
        if heading and _MUST_CUE_RE.match(line) and not _NICE_CUE_RE.search(line):
            optional_block = False
        elif heading and _NICE_CUE_RE.search(line):
            optional_block = True
            continue
        # A long line is judged sentence by sentence; a cue covers the rest of its sentence.
        for sentence in re.split(r"(?<=[.;!?])\s+", line):
            m = None if optional_block else _NICE_CUE_RE.search(sentence)
            # "Kafka is a plus": the cue follows the skills it describes.
            trailing = bool(m and re.search(r"plus\b|desirable|not required|optional", m.group(0), re.I))
            for skill in find_skills(sentence):
                pos = sentence.lower().find(skill.lower())
                is_nice = optional_block or bool(m and (trailing or pos < 0 or pos >= m.start()))
                target, other = (nice, must) if is_nice else (must, nice)
                if skill not in target and skill not in other:
                    target.append(skill)
    return {"must_have": must[:MAX_SKILLS], "nice_to_have": nice[:MAX_SKILLS], "source": "rules"}


def build_requirements_prompt(job: dict) -> str:
    return (
        "You analyse job postings. From the posting below, list the technical skills it asks for.\n"
        '"must_have": skills the posting requires. "nice_to_have": skills it calls optional, '
        "preferred, a bonus or a plus.\n"
        "Use short skill names exactly as written in the posting. Do not add skills it does not mention.\n"
        'Answer with JSON only, in this shape: {"must_have": ["..."], "nice_to_have": ["..."]}\n\n'
        f"{wrap_untrusted('job title', str(job.get('title') or ''), max_len=300)}\n\n"
        f"{wrap_untrusted('job description', str(job.get('description') or '')[:JD_CHARS])}\n"
    )


def _parse_llm_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _grounded(items, jd_text: str, seen: set[str]) -> list[str]:
    """Keep only short strings that actually occur in the posting (canonical name when known)."""
    out: list[str] = []
    low = jd_text.lower()
    for item in items if isinstance(items, list) else []:
        s = re.sub(r"\s+", " ", str(item)).strip(" .-")
        if not (1 < len(s) <= 40) or s.lower() not in low:
            continue
        known = canonicalize(s)
        if not known and len(s.split()) > 2:
            continue  # unknown phrases longer than two words are sentences, not skills
        name = known or s
        if name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out[:MAX_SKILLS]


def analyze_requirements_llm(job: dict) -> dict:
    """LLM split of must-have vs nice-to-have skills. Falls back to the rule-based split
    when the model's answer is not usable. Raises ``LLMUnavailable`` when no model runs."""
    job = job or {}
    jd_text = str(job.get("description") or "")
    data = _parse_llm_json(call_llm(build_requirements_prompt(job)))
    if data is None:
        return split_requirements(jd_text)
    seen: set[str] = set()
    must = _grounded(data.get("must_have"), jd_text, seen)
    nice = _grounded(data.get("nice_to_have"), jd_text, seen)
    if not must and not nice:
        return split_requirements(jd_text)
    return {"must_have": must, "nice_to_have": nice, "source": "llm"}


__all__ = ["split_requirements", "analyze_requirements_llm", "build_requirements_prompt"]
