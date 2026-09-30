#!/usr/bin/env python3
"""End-to-end JobHunt AI workflow from the command line.

    python pipeline.py --resume resume.tex --keywords "Python Developer" \
        --location Remote --max-jobs 20 --sources remoteok,hn,remotive,arbeitnow

Steps: parse resume -> scrape jobs -> store jobs -> score matches -> save matches -> print table.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402

RESUME_EXTENSIONS = {".tex", ".txt", ".md", ".pdf"}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="JobHunt AI: parse your resume, scrape jobs and rank matches.")
    p.add_argument("--resume", required=True, help="Path to resume (.tex, .txt, .md; .pdf if pypdf is installed)")
    p.add_argument("--keywords", default="Python Developer", help='Search keywords, e.g. "Python Developer"')
    p.add_argument("--location", default="Remote", help="Location (only used by the experimental Indeed/LinkedIn/Naukri scrapers)")
    p.add_argument("--max-jobs", type=int, default=20, help="Max jobs to scrape (capped by MAX_JOBS_PER_SESSION)")
    p.add_argument("--sources", default="remoteok,hn,remotive,arbeitnow",
                   help="Comma-separated sources: remoteok,hn,remotive,arbeitnow,greenhouse,lever "
                        "(greenhouse/lever need GREENHOUSE_BOARDS/LEVER_COMPANIES in .env); "
                        "experimental, usually blocked: indeed,linkedin,naukri")
    p.add_argument("--top", type=int, default=20, help="Rows to show in the results table")
    p.add_argument("--db", default=None, help="Database URL override (default: DATABASE_URL or sqlite:///jobhunt.db)")
    p.add_argument("--no-save", action="store_true", help="Score only; don't write resume/jobs/matches to the DB")
    p.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    return p


def load_resume(path_str: str) -> dict:
    from config import get_settings
    from parser.resume_parser import parse_resume_bytes
    from security.sanitize import validate_upload

    path = Path(path_str).expanduser()
    if not path.is_file():
        raise SystemExit(f"Resume not found: {path}")
    data = path.read_bytes()
    try:
        validate_upload(path.name, data, RESUME_EXTENSIONS, get_settings().upload_max_bytes)
        return parse_resume_bytes(path.name, data)
    except ValueError as exc:
        raise SystemExit(f"Could not read resume: {exc}")


def _fmt(v) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return "-"


def print_table(scored: list[dict], top: int) -> None:
    rows = []
    for i, job in enumerate(scored[:top], 1):
        s = job.get("scores") or {}
        rows.append([str(i), _fmt(s.get("total")), _fmt(s.get("ats")), _fmt(s.get("semantic")),
                     _fmt(s.get("experience")), _fmt(s.get("freshness")),
                     str(job.get("title") or "")[:45], str(job.get("company") or "")[:25],
                     str(job.get("source") or "")])
    headers = ["#", "Score", "ATS", "Sem", "Exp", "Fresh", "Title", "Company", "Source"]
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Top job matches")
        for h in headers:
            table.add_column(h, justify="right" if h in ("#", "Score", "ATS", "Sem", "Exp", "Fresh") else "left")
        for r in rows:
            table.add_row(*r)
        Console().print(table)
        return
    except ImportError:
        pass
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def run(args: argparse.Namespace) -> list[dict]:
    if args.db:
        os.environ["DATABASE_URL"] = args.db
    from security.logging_setup import setup_logging

    setup_logging("DEBUG" if args.verbose else "INFO")

    from matching.confidence_score import score_jobs
    from scraper.service import scrape_jobs

    # 1. Parse resume
    resume = load_resume(args.resume)
    logger.info("Parsed resume: {} skills, {} experience entries",
                len(resume["skills"]), len(resume["experience"]))

    # 2. Scrape
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    jobs = scrape_jobs(args.keywords, args.location, args.max_jobs, sources)
    if not jobs:
        print("No jobs found. Check your network connection, keywords or --sources.")
        return []

    # 3. Store
    resume_id = None
    ids_by_hash: dict[str, int] = {}
    if not args.no_save:
        from db import repository as repo
        from db.database import init_db

        init_db()
        resume_id = repo.save_resume(resume, str(Path(args.resume).expanduser().resolve()))
        new = repo.upsert_jobs(jobs)
        logger.info("Stored jobs: {} new, {} already known", new, len(jobs) - new)
        ids_by_hash = {j["dedupe_hash"]: j["id"] for j in repo.list_jobs(limit=1000) if j.get("dedupe_hash")}

    # 4. Score
    scored = score_jobs(resume, jobs)

    # 5. Save matches
    if not args.no_save and resume_id is not None:
        from db import repository as repo

        saved = 0
        for job in scored:
            job_id = ids_by_hash.get(repo.compute_dedupe_hash(job))
            if job_id is not None:
                job["job_id"] = job_id
                job["match_id"] = repo.save_match(resume_id, job_id, job["scores"])
                saved += 1
        logger.info("Saved {} matches for resume #{}", saved, resume_id)

    # 6. Show
    print_table(scored, args.top)
    return scored


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        run(args)
    except KeyboardInterrupt:
        print("Interrupted.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
