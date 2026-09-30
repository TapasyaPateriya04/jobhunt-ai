"""Semantic similarity between a resume and a job description.

Primary backend: sentence-transformers ``all-MiniLM-L6-v2`` (lazy-loaded once,
cached at module level). Long texts are split into ~256-word windows (with
overlap) instead of being truncated; for every JD chunk we take its best-matching
resume chunk (max), then average over JD chunks (mean) — i.e. "how well is each
part of the job covered by some part of the resume".

Fallback backend (sentence-transformers missing or model load fails): character
n-gram TF-IDF cosine (robust to morphology: "developer"/"development"), blended
with word-level LSA (TF-IDF + TruncatedSVD) when scoring a batch large enough
for SVD to be meaningful. The fallback is logged once.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import List, Optional, Sequence

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
CHUNK_WORDS = 256
CHUNK_OVERLAP = 32
# LSA on a handful of docs is ~one-topic-per-doc and gives extreme (0 or ~1) sims;
# only blend it in for batches large enough to learn shared latent topics.
LSA_MIN_DOCS = 20
LSA_WEIGHT = 0.3

# Fallback raw cosines sit in a compressed band (char n-grams share a lot of
# generic English); linearly rescale [LOW, HIGH] -> [0, 100] (monotonic, clamped).
FALLBACK_LOW = 0.05
FALLBACK_HIGH = 0.55
# Calibrated on 156 real postings against a real resume (2026-09-30, see
# scripts/evaluate_matching.py): unrelated jobs (nurse, accountant, cook) score 0.10-0.25,
# real software jobs 0.13-0.63 (median 0.35), a hand-written ideal posting 0.67.
# Long postings score lower than short ones because company boilerplate dilutes them.
EMBED_LOW = 0.20
EMBED_HIGH = 0.60

_model = None
_model_failed = False
_fallback_logged = False
_lock = threading.Lock()


def _rescale(x: float, lo: float, hi: float) -> float:
    if x is None or not math.isfinite(x):
        return 0.0
    return float(max(0.0, min(100.0, (x - lo) / (hi - lo) * 100.0)))


def _log_fallback_once(reason: str) -> None:
    global _fallback_logged
    if not _fallback_logged:
        _fallback_logged = True
        logger.warning("Semantic matcher using TF-IDF fallback (%s).", reason)


def get_model():
    """Return the cached SentenceTransformer, or None if unavailable. Loads at most once."""
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    with _lock:
        if _model is not None or _model_failed:
            return _model
        try:
            from sentence_transformers import SentenceTransformer  # lazy, heavy
        except Exception as exc:  # ImportError, or torch import errors
            _model_failed = True
            _log_fallback_once(f"sentence-transformers not importable: {type(exc).__name__}")
            return None
        try:
            _model = SentenceTransformer(MODEL_NAME)
        except Exception as exc:  # download/network/corrupt cache
            _model_failed = True
            _log_fallback_once(f"could not load {MODEL_NAME}: {type(exc).__name__}")
            return None
    return _model


def backend_name() -> str:
    return "embedding" if get_model() is not None else "tfidf-fallback"


def chunk_text(text: str, size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    step = max(1, size - overlap)
    chunks = []
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return chunks


def _has_text(s: Optional[str]) -> bool:
    return bool(s and any(c.isalnum() for c in s))


# --------------------------------------------------------------------------- embedding path
def _embed_chunks(model, text: str) -> np.ndarray:
    chunks = chunk_text(text)
    return np.asarray(model.encode(chunks, normalize_embeddings=True, show_progress_bar=False))


def _chunk_similarity(res_emb: np.ndarray, jd_emb: np.ndarray) -> float:
    sims = cosine_similarity(jd_emb, res_emb)  # (jd_chunks, resume_chunks)
    return float(sims.max(axis=1).mean())


def _embedding_scores(model, resume_text: str, jd_texts: Sequence[str]) -> List[float]:
    res_emb = _embed_chunks(model, resume_text)
    out = []
    for jd in jd_texts:
        if not _has_text(jd):
            out.append(0.0)
            continue
        out.append(_rescale(_chunk_similarity(res_emb, _embed_chunks(model, jd)), EMBED_LOW, EMBED_HIGH))
    return out


# --------------------------------------------------------------------------- fallback path
def _fallback_scores(resume_text: str, jd_texts: Sequence[str]) -> List[float]:
    docs = [resume_text] + list(jd_texts)
    try:
        char_m = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True,
                                 sublinear_tf=True).fit_transform(docs)
        char_sims = cosine_similarity(char_m[0], char_m[1:])[0]
    except ValueError:
        return [0.0] * len(jd_texts)
    sims = np.asarray(char_sims, dtype=float)

    if len(docs) >= LSA_MIN_DOCS:
        try:
            word_m = TfidfVectorizer(stop_words="english", sublinear_tf=True).fit_transform(docs)
            n_comp = min(100, len(docs) // 2, word_m.shape[1] - 1)
            if n_comp >= 2:
                lsa = TruncatedSVD(n_components=n_comp, random_state=0).fit_transform(word_m)
                lsa_sims = np.clip(cosine_similarity(lsa[:1], lsa[1:])[0], 0.0, 1.0)
                sims = (1 - LSA_WEIGHT) * sims + LSA_WEIGHT * lsa_sims
        except ValueError:
            pass
    return [_rescale(s, FALLBACK_LOW, FALLBACK_HIGH) if _has_text(t) else 0.0
            for s, t in zip(sims, jd_texts)]


# --------------------------------------------------------------------------- public API
def semantic_scores(resume_text: str, jd_texts: Sequence[str]) -> List[float]:
    """Batch version: one resume vs many JDs; scores 0-100. Resume is encoded once."""
    jd_texts = [t or "" for t in jd_texts]
    if not jd_texts:
        return []
    if not _has_text(resume_text):
        return [0.0] * len(jd_texts)
    model = get_model()
    if model is not None:
        try:
            return _embedding_scores(model, resume_text, jd_texts)
        except Exception as exc:  # encoding failure at runtime -> degrade, don't crash
            _log_fallback_once(f"encoding failed: {type(exc).__name__}")
    return _fallback_scores(resume_text, jd_texts)


def semantic_score(resume_text: str, jd_text: str) -> float:
    """Semantic similarity 0-100 between a resume and one job description."""
    return semantic_scores(resume_text, [jd_text])[0]


__all__ = ["semantic_score", "semantic_scores", "chunk_text", "get_model", "backend_name"]
