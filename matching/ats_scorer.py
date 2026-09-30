"""ATS-style keyword scoring (TF-IDF cosine) — no API, pure scikit-learn.

Calibration
-----------
Raw TF-IDF cosine between a full resume and a job description is almost always
low (roughly 0.05-0.35) even for a strong match, because both documents contain
many terms the other doesn't. Reporting ``cosine * 100`` directly would make a
great match look like "22/100". We therefore apply a monotonic saturating rescale

    calibrated = 100 * (1 - exp(-K * raw_cosine)),  K = 6.0

which preserves ranking (strictly increasing) and maps typical values to an
intuitive range: raw 0.05 -> ~26, 0.10 -> ~45, 0.20 -> ~70, 0.30 -> ~83,
0.50 -> ~95, 0 -> 0, 1 -> ~100. The raw value (``cosine * 100``) is still
available via :func:`ats_raw_score` / ``calibrate=False`` and is reported by
``confidence_score`` under ``"ats_raw"``.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from parser.skills_vocab import find_skills

CALIBRATION_K = 6.0
# A posting must name at least this many known skills before coverage is meaningful.
MIN_JD_SKILLS = 3
# Words that are frequent in postings but say nothing about fit (keyword gap padding).
_GAP_NOISE = frozenset("""
work team teams software product products build building development developer developers engineer
engineers engineering apply senior customers customer applications application business
including solutions ability roles role use using people strong features production employees
make company best process global develop real looking working day modern like opportunity
https http www com und der die mit für wir sie du ll ve re don experience years year skills
job jobs hiring benefits applicants candidates new world join help across well time based
""".split())

# Keep tokens like "c++", "c#", "node.js", "ci/cd" reasonably intact.
_TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z0-9+#./-]*[a-zA-Z0-9+#]|\b[a-zA-Z]\b"


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if x is None or not math.isfinite(x):
        return lo
    return max(lo, min(hi, float(x)))


def calibrate(raw_cosine: float) -> float:
    """Monotonic rescale of a raw cosine in [0, 1] to an intuitive 0-100 score."""
    r = max(0.0, min(1.0, float(raw_cosine or 0.0)))
    return _clamp(100.0 * (1.0 - math.exp(-CALIBRATION_K * r)))


def make_vectorizer(**overrides) -> TfidfVectorizer:
    params = dict(
        stop_words="english",
        ngram_range=(1, 2),
        lowercase=True,
        sublinear_tf=True,
        token_pattern=_TOKEN_PATTERN,
    )
    params.update(overrides)
    return TfidfVectorizer(**params)


def _has_text(s: Optional[str]) -> bool:
    return bool(s and re.search(r"[A-Za-z0-9]", s))


def batch_raw_cosines(resume_text: str, jd_texts: Sequence[str]) -> List[float]:
    """Fit ONE vectorizer on resume + all JDs; return raw cosine (0-1) per JD."""
    jd_texts = [t or "" for t in jd_texts]
    if not jd_texts:
        return []
    if not _has_text(resume_text):
        return [0.0] * len(jd_texts)
    docs = [resume_text] + jd_texts
    try:
        matrix = make_vectorizer().fit_transform(docs)
    except ValueError:  # empty vocabulary (only stop words / punctuation)
        return [0.0] * len(jd_texts)
    sims = cosine_similarity(matrix[0], matrix[1:])[0]
    return [float(np.clip(s, 0.0, 1.0)) if _has_text(t) else 0.0
            for s, t in zip(sims, jd_texts)]


def ats_raw_score(resume_text: str, jd_text: str) -> float:
    """Uncalibrated TF-IDF cosine * 100, clamped to 0-100."""
    return _clamp(batch_raw_cosines(resume_text, [jd_text])[0] * 100.0)


def ats_score(resume_text: str, jd_text: str, calibrate_score: bool = True) -> float:
    """ATS keyword-overlap score 0-100 (calibrated by default; see module docstring)."""
    raw = batch_raw_cosines(resume_text, [jd_text])[0]
    return calibrate(raw) if calibrate_score else _clamp(raw * 100.0)


def skill_coverage(resume_skills: Iterable[str], jd_text: str) -> Optional[float]:
    """Share (0-100) of the known skills a posting names that the resume also has.
    ``None`` when the posting names fewer than ``MIN_JD_SKILLS`` skills."""
    jd_skills = find_skills(jd_text or "")
    if len(jd_skills) < MIN_JD_SKILLS:
        return None
    have = set(resume_skills or ())
    return 100.0 * sum(1 for s in jd_skills if s in have) / len(jd_skills)


def blended_ats(keyword_score: float, coverage: Optional[float]) -> float:
    """ATS score: half TF-IDF keyword overlap, half skill coverage (when it is known)."""
    return _clamp(keyword_score if coverage is None else 0.5 * keyword_score + 0.5 * coverage)


def keyword_gap(resume_text: str, jd_text: str, top_n: int = 15) -> dict:
    """What the posting asks for, split into matched / missing in the resume.

    Known skills come first, in the order the posting mentions them (canonical names such
    as "Spring Boot"). Remaining slots are filled with the posting's heaviest TF-IDF terms,
    skipping filler words ("team", "work", "https").
    """
    if not _has_text(jd_text):
        return {"matched": [], "missing": []}
    have = set(find_skills(resume_text or ""))
    matched, missing = [], []
    for skill in find_skills(jd_text)[:top_n]:
        (matched if skill in have else missing).append(skill)
    if len(matched) + len(missing) >= top_n:
        return {"matched": matched, "missing": missing}
    try:
        vec = make_vectorizer()
        matrix = vec.fit_transform([resume_text or "", jd_text])
    except ValueError:
        return {"matched": matched, "missing": missing}
    terms = vec.get_feature_names_out()
    jd_row = matrix[1].toarray()[0]
    res_row = matrix[0].toarray()[0]
    order = np.argsort(-jd_row, kind="stable")
    # words already represented by a listed term with the same status
    # (avoids "python" + "python django" noise in the same list)
    skill_words = {w for s in matched + missing for w in s.lower().split()}
    covered = {True: set(skill_words), False: set(skill_words)}
    for idx in order:
        if jd_row[idx] <= 0 or len(matched) + len(missing) >= top_n:
            break
        term = terms[idx]
        words = term.split()
        if any(w in _GAP_NOISE or len(w) < 3 for w in words) or find_skills(term):
            continue
        is_matched = bool(res_row[idx] > 0)
        if all(w in covered[is_matched] for w in words):
            continue
        (matched if is_matched else missing).append(term)
        covered[is_matched].update(words)
    return {"matched": matched, "missing": missing}


__all__: Iterable[str] = [
    "ats_score", "ats_raw_score", "keyword_gap", "calibrate", "batch_raw_cosines", "make_vectorizer",
    "skill_coverage", "blended_ats",
]
