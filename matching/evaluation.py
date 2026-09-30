"""Ranking metrics for a labeled set of jobs (used by scripts/evaluate_matching.py).

Labels are graded: 2 = good fit, 1 = partial fit, 0 = bad fit.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence

from matching.confidence_score import WEIGHTS, score_jobs
from matching.location import location_factor

GOOD, PARTIAL, BAD = 2, 1, 0


def precision_at_k(labels: Sequence[int], k: int = 5, threshold: int = PARTIAL) -> float:
    """Share of the top ``k`` ranked labels that are at least ``threshold``."""
    top = list(labels)[:k]
    return sum(1 for x in top if x >= threshold) / len(top) if top else 0.0


def ndcg_at_k(labels: Sequence[int], k: int = 10) -> float:
    """Normalised discounted cumulative gain with gains 2^label - 1 (1.0 = ideal order)."""
    def dcg(xs: Sequence[int]) -> float:
        return sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(xs[:k]))

    ideal = dcg(sorted(labels, reverse=True))
    return dcg(list(labels)) / ideal if ideal > 0 else 0.0


def job_key(job: dict) -> str:
    return (job.get("url") or "").strip().lower().rstrip("/")


def rank(resume: dict, jobs: List[dict], label_by_url: Dict[str, int],
         total: Optional[Callable[[dict], float]] = None, country: str = "") -> List[dict]:
    """Score ``jobs`` and return them best first, each with ``scores`` and ``label``.
    ``total`` optionally recomputes the ranking score from the component scores.
    ``country`` is the candidate's home country ("" = ignore location)."""
    ranked = [{**j, "label": label_by_url[job_key(j)]} for j in score_jobs(resume, jobs, country=country)
              if job_key(j) in label_by_url]
    if total is not None:
        ranked.sort(key=lambda j: total(j["scores"]), reverse=True)
    return ranked


def metrics(ranked: List[dict]) -> dict:
    labels = [j["label"] for j in ranked]
    return {
        "n": len(labels),
        "good": labels.count(GOOD),
        "partial": labels.count(PARTIAL),
        "p_at_5": precision_at_k(labels, 5, PARTIAL),
        "p_at_5_good": precision_at_k(labels, 5, GOOD),
        "p_at_10": precision_at_k(labels, 10, PARTIAL),
        "ndcg_at_10": ndcg_at_k(labels, 10),
    }


def weighted_total(weights: Dict[str, float]) -> Callable[[dict], float]:
    """Ranking function for trying a different weight mix without touching WEIGHTS."""
    norm = sum(weights.values()) or 1.0
    return lambda s: (sum(weights.get(k, 0.0) * float(s.get(k) or 0.0) for k in WEIGHTS) / norm
                      * location_factor(s.get("location_score")))


__all__ = ["GOOD", "PARTIAL", "BAD", "precision_at_k", "ndcg_at_k", "rank", "metrics",
           "weighted_total", "job_key"]
