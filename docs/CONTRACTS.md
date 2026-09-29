# Module contracts (shared by all contributors)

Python 3.10+. Package root is the repo root; run the app with `streamlit run ui/app.py`
(ui/app.py inserts the repo root onto sys.path). Heavy/optional deps (spacy,
sentence-transformers, playwright, google-genai) MUST be imported lazily and the
code MUST degrade gracefully when they are missing (tests run without them).

## config.py (owner: security)
- `get_settings() -> Settings` dataclass loaded from env/.env via python-dotenv:
  `database_url` (default `sqlite:///jobhunt.db`), `use_ollama` (bool, default True),
  `ollama_base_url` (default `http://localhost:11434`), `ollama_model` (default `mistral`),
  `gemini_api_key` (Optional[str]), `gemini_model` (default `gemini-3.8-flash`),
  `docs_dir` (default `~/jobhunt_docs`), `scrape_delay_seconds` (default 3.0),
  `max_jobs_per_session` (default 50), `upload_max_bytes` (default 2_000_000).

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
  `get_engine(url=None)`, `init_db(engine=None)`, `get_session()` context manager.
- `db/repository.py`: `save_resume(parsed: dict, file_path: str) -> int`, `get_resume(id) -> dict|None`,
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
- `scraper/indeed_scraper.py`, `linkedin_scraper.py`, `naukri_scraper.py`: async Playwright+BS4 scrapers per SPEC §5.2,
  each checks robots via `security.robots.can_fetch` and uses RateLimiter; fail gracefully (return []) when playwright missing.
- `scraper/__init__.py` or `scraper/service.py`: `scrape_jobs(keywords, location, max_jobs, sources: list[str]) -> list[dict]`.
- `parser/resume_parser.py`: `parse_resume_text(text) -> dict`, `parse_latex_resume(path) -> dict`,
  `parse_resume_bytes(filename, data) -> dict` (.tex/.txt/.md; .pdf optional) returning
  `{"raw_text","skills": list[str],"experience": list[dict],"education": str,"summary": str}`.
- `parser/jd_analyzer.py`: `analyze_jd(text) -> {"skills": list[str], "experience_years": int|None, "keywords": list[str]}`.
- `generator/llm.py`: `call_llm(prompt) -> str` (Ollama then Gemini fallback; raises `LLMUnavailable` with a helpful message).
- `generator/cover_letter.py`: `generate_cover_letter(resume: dict, job: dict) -> str`.
- `generator/resume_optimizer.py`: `suggest_resume_edits(resume: dict, job: dict) -> str`.
- `generator/documents.py`: `save_generated_doc(match_id, doc_type, content) -> str` (writes into docs_dir with safe_join, stores via repository).

## matching/ (owner: ML)
- `matching/ats_scorer.py`: `ats_score(resume_text, jd_text) -> float` (0-100), `keyword_gap(resume_text, jd_text, top_n=15) -> dict` (`matched`, `missing`).
- `matching/semantic_matcher.py`: `semantic_score(resume_text, jd_text) -> float`; lazy-loads `all-MiniLM-L6-v2`;
  falls back to TF-IDF char n-gram / LSA similarity when sentence-transformers unavailable.
- `matching/confidence_score.py`: `calculate_confidence_score(resume: dict, job: dict) -> dict` with keys
  `total, ats, experience, semantic, freshness` using weights 0.35/0.25/0.20/0.20; plus `score_jobs(resume, jobs) -> list[dict]`.

## ui/ (owner: frontend)
- `ui/app.py` Streamlit with the four tabs from SPEC §7 (Resume, Scrape Jobs, Matches, Generate Docs), wired to the
  functions above; persists to SQLite via db.repository; never shows raw exceptions/secrets.
