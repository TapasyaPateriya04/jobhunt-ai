"""Measure matching quality on real, hand-labeled jobs.

    python scripts/evaluate_matching.py            # metrics + ranked list
    python scripts/evaluate_matching.py --weights  # also compare weight mixes
    python scripts/evaluate_matching.py --snapshot # refresh the local job/resume snapshot

Inputs
- eval/labeled_jobs.json   (committed) job URL + label: 2 good, 1 partial, 0 bad fit.
- eval/jobs_snapshot.json  (local, gitignored) the labeled jobs' full text, copied from
  your jobhunt.db so later scrapes or a wiped database don't change the numbers.
- eval/resume_snapshot.json (local, gitignored) the resume the labels were made for.

Headline number: precision@5 = how many of the top 5 ranked jobs are a good or partial
fit. Re-run after any change to matching/ and compare.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(ROOT))

from matching import evaluation as ev  # noqa: E402
from matching.confidence_score import WEIGHTS  # noqa: E402
from matching.semantic_matcher import backend_name  # noqa: E402

EVAL_DIR = ROOT / "eval"
LABELS_FILE = EVAL_DIR / "labeled_jobs.json"
JOBS_FILE = EVAL_DIR / "jobs_snapshot.json"
RESUME_FILE = EVAL_DIR / "resume_snapshot.json"
JOB_FIELDS = ("title", "company", "location", "description", "source", "url", "posted_date",
              "experience_years")

# Weight mixes compared by --weights (ats, experience, semantic, freshness).
WEIGHT_MIXES = {
    "spec 35/25/20/20": {"ats": 0.35, "experience": 0.25, "semantic": 0.20, "freshness": 0.20},
    "no freshness": {"ats": 0.40, "experience": 0.35, "semantic": 0.25, "freshness": 0.0},
    "experience-heavy": {"ats": 0.30, "experience": 0.40, "semantic": 0.20, "freshness": 0.10},
    "semantic-heavy": {"ats": 0.25, "experience": 0.30, "semantic": 0.35, "freshness": 0.10},
    "ats only": {"ats": 1.0}, "semantic only": {"semantic": 1.0}, "experience only": {"experience": 1.0},
}


def load_labels() -> tuple[dict[str, int], str]:
    """Labels by job URL, and the home country the labels were made for."""
    doc = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
    return ({ev.job_key(j): int(j["label"]) for j in doc["jobs"] if j.get("url")},
            str(doc.get("candidate_country") or ""))


def write_snapshot(labels: dict[str, int]) -> None:
    """Copy the labeled jobs and the latest resume from the database into eval/."""
    from db import repository as repo
    from db.database import init_db

    init_db()
    jobs = [{k: j.get(k) for k in JOB_FIELDS} for j in repo.list_jobs(limit=5000)
            if ev.job_key(j) in labels]
    resume = repo.latest_resume()
    if not jobs or not resume:
        raise SystemExit("Nothing to snapshot: the database has no labeled jobs or no resume.")
    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, default=str), encoding="utf-8")
    RESUME_FILE.write_text(json.dumps({k: resume.get(k) for k in (
        "raw_text", "skills", "experience", "education", "summary")}, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"Snapshot written: {len(jobs)} of {len(labels)} labeled jobs, resume #{resume.get('id')}.")


def load_inputs(resume_path: str | None) -> tuple[dict, list[dict]]:
    if not JOBS_FILE.exists() or not RESUME_FILE.exists():
        raise SystemExit("No local snapshot yet. Run: python scripts/evaluate_matching.py --snapshot")
    jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    if resume_path:
        from parser.resume_parser import parse_resume_bytes

        path = Path(resume_path).expanduser()
        resume = parse_resume_bytes(path.name, path.read_bytes())
    else:
        resume = json.loads(RESUME_FILE.read_text(encoding="utf-8"))
    return resume, jobs


def show_metrics(name: str, m: dict) -> None:
    print(f"{name:<22} P@5 {m['p_at_5']:.2f}   P@5 good-only {m['p_at_5_good']:.2f}   "
          f"P@10 {m['p_at_10']:.2f}   nDCG@10 {m['ndcg_at_10']:.2f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", action="store_true", help="refresh eval/ snapshots from the database")
    ap.add_argument("--weights", action="store_true", help="compare alternative weight mixes")
    ap.add_argument("--resume", help="score with this resume file instead of the snapshot")
    ap.add_argument("--top", type=int, default=15, help="rows of the ranking to print")
    ap.add_argument("--no-location", action="store_true", help="ignore the candidate's home country")
    args = ap.parse_args(argv)

    labels, country = load_labels()
    if args.no_location:
        country = ""
    if args.snapshot:
        write_snapshot(labels)
        return 0
    resume, jobs = load_inputs(args.resume)
    ranked = ev.rank(resume, jobs, labels, country=country)
    m = ev.metrics(ranked)
    print(f"semantic backend: {backend_name()}   labeled jobs scored: {m['n']} "
          f"({m['good']} good, {m['partial']} partial)   weights: {WEIGHTS}   "
          f"home country: {country or 'not used'}\n")
    show_metrics("current", m)
    if country:
        show_metrics("without location", ev.metrics(ev.rank(resume, jobs, labels)))

    print(f"\n{'#':>2}  {'fit':<7} {'total':>5} {'ats':>5} {'sem':>5} {'exp':>5} {'fresh':>5}  req  location     job")
    names = {ev.GOOD: "GOOD", ev.PARTIAL: "partial", ev.BAD: "-"}
    for i, j in enumerate(ranked[:args.top], 1):
        s = j["scores"]
        req = "?" if s.get("required_years") is None else s["required_years"]
        print(f"{i:>2}  {names[j['label']]:<7} {s['total']:>5} {s['ats']:>5} {s['semantic']:>5} "
              f"{s['experience']:>5} {s['freshness']:>5}  {str(req):>3}  {s['location_status']:<11}  "
              f"{str(j.get('title'))[:40]} @ {str(j.get('company'))[:16]}")
    missed = [(i, j) for i, j in enumerate(ranked, 1) if j["label"] >= ev.PARTIAL and i > args.top]
    for i, j in missed:
        print(f"{i:>2}  {names[j['label']]:<7} {j['scores']['total']:>5}  (below the cut)  "
              f"{str(j.get('title'))[:44]} @ {str(j.get('company'))[:18]}")

    if args.weights:
        print("\nWeight mixes (same component scores, different blend):")
        for name, w in WEIGHT_MIXES.items():
            show_metrics(name, ev.metrics(ev.rank(resume, jobs, labels, ev.weighted_total(w), country)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
