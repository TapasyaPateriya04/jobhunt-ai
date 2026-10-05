# Module contracts (shared by all contributors)

Python 3.10+. Package root is the repo root; run the app with `streamlit run ui/app.py`
(ui/app.py inserts the repo root onto sys.path). Heavy/optional deps (spacy,
sentence-transformers, google-genai) MUST be imported lazily and the
code MUST degrade gracefully when they are missing (tests run without them).

## config.py (owner: security)
- `get_settings() -> Settings` dataclass loaded from env/.env via python-dotenv:
  `database_url` (default `sqlite:///jobhunt.db`), `use_ollama` (bool, default True),
  `ollama_base_url` (default `http://localhost:11434`), `ollama_model` (default `mistral`),
  `gemini_api_key` (Optional[str]), `gemini_model` (default `gemini-3.8-flash`),
  `docs_dir` (default `~/jobhunt_docs`), `scrape_delay_seconds` (default 3.0),
  `max_jobs_per_session` (default 50), `upload_max_bytes` (default 2_000_000),
  `greenhouse_boards` / `lever_companies` (tuples of company slugs from comma-separated env, default empty),
  `candidate_country` (default `""` = ignore location), `candidate_cities` (tuple).

## security/ (owner: security)
- `security/sanitize.py`: `sanitize_text(s: str, max_len: int = 20000) -> str` (strip control chars, limit length),
  `safe_filename(name: str) -> str`, `safe_join(base: Path, name: str) -> Path` (raise ValueError on traversal),
  `validate_upload(filename: str, data: bytes, allowed_ext: set[str], max_bytes: int) -> None` (raise ValueError).
- `security/url_guard.py`: `is_allowed_url(url: str) -> bool` (http/https only, allowlisted job hosts),
  `validate_llm_endpoint(url: str) -> str` (only localhost/127.0.0.1 unless explicitly allowed).
- `security/robots.py`: `can_fetch(url: str, user_agent: str = "JobHuntAI-Learner") -> bool` (cached robots.txt check; fail closed).
- `security/rate_limit.py`: `class RateLimiter(min_interval: float)` with `wait()` and `async await_turn()`.
- `security/prompt_guard.py`: `wrap_untrusted(label: str, text: str) -> str` delimiting scraped/resume text in prompts.
- `security/logging_setup.py`: `setup_logging()` using loguru, with a filter that redacts API keys.

## db/ (owner: database)
- `db/database.py`: SQLAlchemy 2.0 models `Resume, Job, Match, Document` exactly per the ERD in SPEC §6
  (Job also has `location`, `posted_date`, `experience_years` nullable int, and a UNIQUE `url` / dedupe hash;
  Match has `experience_score`, `freshness_score`, `status` default "new", `calculated_at`).
  `get_engine(url=None)`, `init_db(engine=None)` (also adds nullable columns introduced later, e.g.
  `resumes.extra_skills_json`, to an existing database), `get_session()` context manager.
- `db/repository.py`: `save_resume(parsed: dict, file_path: str) -> int` (same resume text reuses its row),
  `list_resumes(limit=50)`, `set_extra_skills(resume_id, skills) -> list[str]` (skills typed in by the user; resume dicts
  carry them as `extra_skills` and merged into `skills`), `get_resume(id) -> dict|None`,
  `latest_resume() -> dict|None`, `upsert_jobs(jobs: list[dict]) -> int` (returns new count; dedupe on url or
  title+company+location hash), `list_jobs(limit=50) -> list[dict]`, `get_job(id) -> dict|None`,
  `save_match(resume_id, job_id, scores: dict) -> int`, `list_matches(resume_id, limit=50) -> list[dict]`
  (joined with job fields, sorted by confidence desc), `update_match_status(match_id, status)`,
  `save_document(match_id, doc_type, content, file_path) -> int`, `list_documents(match_id) -> list[dict]`.
  All functions accept an optional `session=` kwarg for tests. Dicts use plain keys (no SQLAlchemy objects leak).

## Normalized job dict (produced by scraper/normalizer.py, consumed everywhere)
`{"title","company","location","description","source","url","posted_date": datetime|None,"experience_years": int|None}`

## scraper/ (owner: backend)
- `scraper/normalizer.py`: `normalize_job(raw: dict, source: str) -> dict`, `extract_experience_years(text) -> int|None`.
- `scraper/remoteok_scraper.py`: `fetch_remoteok(keywords, max_jobs=20) -> list[dict]` (free public JSON API; default source).
- `scraper/hn_scraper.py`: `fetch_hn_whos_hiring(keywords, max_jobs=20) -> list[dict]` (HN Algolia API).
- `scraper/relevance.py`: `relevance(keywords, title, tags="", description="") -> int` (0 = off-topic) and
  `select_relevant(items, keywords, max_jobs, fields)`; every API source filters through it.
- `scraper/muse_scraper.py`: `fetch_muse(keywords, location="Remote", max_jobs=20)`; `scraper/arbeitnow_scraper.py`:
  `fetch_arbeitnow(keywords, max_jobs=20)` (free public JSON APIs; default sources).
- `scraper/ats_boards.py`: `fetch_greenhouse(keywords, max_jobs=20, boards=None)`, `fetch_lever(keywords, max_jobs=20,
  companies=None)` (public job-board APIs for the company slugs in settings; [] when none configured).
- `scraper/himalayas_scraper.py`: `fetch_himalayas(keywords, location, max_jobs)`, remote jobs from the free
  Himalayas API filtered to the location's country; returns [] on failure.
- `scraper/__init__.py` or `scraper/service.py`: `scrape_jobs(keywords, location, max_jobs, sources: list[str]) -> list[dict]`;
  `DEFAULT_SOURCES` (remoteok, hn, themuse, arbeitnow, himalayas), `BOARD_SOURCES` (greenhouse, lever), `ALL_SOURCES`.
- `parser/resume_parser.py`: `parse_resume_text(text) -> dict`, `parse_latex_resume(path) -> dict`,
  `parse_resume_bytes(filename, data) -> dict` (.tex/.txt/.md; .pdf optional) returning
  `{"raw_text","skills": list[str],"experience": list[dict],"education": str,"summary": str}`.
- `parser/jd_analyzer.py`: `analyze_jd(text) -> {"skills": list[str], "experience_years": int|None, "keywords": list[str]}`.
- `generator/llm.py`: `call_llm(prompt) -> str` (Ollama then Gemini fallback; raises `LLMUnavailable` with a helpful message).
- `generator/cover_letter.py`: `generate_cover_letter(resume: dict, job: dict) -> str`.
- `generator/resume_optimizer.py`: `suggest_resume_edits(resume: dict, job: dict) -> str`.
- `generator/jd_insights.py`: `split_requirements(jd_text) -> {"must_have", "nice_to_have", "source"}` (rules, instant),
  `analyze_requirements_llm(job) -> same` (LLM; only skills present in the posting are kept).
- `generator/documents.py`: `save_generated_doc(match_id, doc_type, content) -> str` (writes into docs_dir with safe_join, stores via repository).

## matching/ (owner: ML)
- `matching/ats_scorer.py`: `ats_score(resume_text, jd_text) -> float` (0-100), `keyword_gap(resume_text, jd_text, top_n=15) -> dict` (`matched`, `missing`; known skills first, canonical names).
- `matching/semantic_matcher.py`: `semantic_score(resume_text, jd_text) -> float`; lazy-loads `all-MiniLM-L6-v2`;
  falls back to TF-IDF char n-gram / LSA similarity when sentence-transformers unavailable.
- `matching/confidence_score.py`: `calculate_confidence_score(resume: dict, job: dict) -> dict` with keys
  `total, ats, experience, semantic, freshness` using weights 0.35/0.30/0.25/0.10 (plus `ats_raw`, `skill_coverage`,
  `candidate_years`, `required_years`); `score_jobs(resume, jobs) -> list[dict]`; `required_years_for(job)`,
  `seniority_years(job)`. `ats` = half calibrated TF-IDF, half `ats_scorer.skill_coverage`.
- `matching/location.py`: `location_fit(job, country, cities=()) -> {"status", "score", "reason"}` with status
  `local | remote_open | remote | unknown | restricted | elsewhere`; `location_factor(score)` multiplies the total
  (1.0 .. 0.4). `score_jobs` / `calculate_confidence_score` take optional `country`, `cities` (default: settings
  `candidate_country`, `candidate_cities`; `""` disables) and add `base_total`, `location_status`, `location_score`,
  `location_reason` to the scores.
- `matching/skill_gap.py`: `candidate_skills(resume) -> set`, `skill_gap(job, have) -> {"required", "matched",
  "missing", "nice_missing"}`, `is_near_miss(gap)`, `near_misses(jobs, have, min_missing=1, max_missing=3)`,
  `skills_to_learn(near) -> [{"skill", "jobs", "closes"}]`.
- `matching/evaluation.py`: `precision_at_k`, `ndcg_at_k`, `rank`, `metrics` for `scripts/evaluate_matching.py`
  (labels in `eval/labeled_jobs.json`: 2 good, 1 partial, 0 bad).

## ui/ (owner: frontend)
- `ui/app.py` Streamlit with the four tabs from SPEC §7 (named Resume, Find jobs, Matches, Documents), wired to the
  functions above; persists to SQLite via db.repository; never shows raw exceptions/secrets.
