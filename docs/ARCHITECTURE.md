# Architecture: how the system works

> Keep this current. A new module, source, setting or data flow updates this file in the
> same commit; `tests/test_docs.py` fails when a job source or setting is missing here.
> Function-level signatures live in [CONTRACTS.md](CONTRACTS.md). Last reviewed: 2026-10-13.

## Shape

A local Python app with two front ends over one backend. Streamlit (`ui/app.py`) and the
React app in `web/` show the same data; `pipeline.py` runs the same flow from the command
line. React talks to `api/`, a thin FastAPI layer that only calls the functions below and
listens on 127.0.0.1. Everything is local: a SQLite file, a docs folder, and optionally an
Ollama server on localhost.

```
 resume file ──► parser/ ──────────────┐
                                       ▼
 job sources ──► scraper/ ──► db/ (SQLite) ◄──► matching/ ──► scores
                                       │
                                       ▼
                           generator/ (Ollama / Gemini) ──► docs_dir (.docx/.pdf)
        ui/app.py (Streamlit) and api/ -> web/ (React) drive all of it;
        security/ wraps every boundary
```

## Packages

| Package | Job |
| --- | --- |
| `config.py` | `get_settings()` reads env / `.env` into a frozen `Settings` dataclass |
| `security/` | Input sanitising, URL allowlist, robots.txt check, rate limiter, prompt fencing, log redaction |
| `parser/` | Resume parsing (`resume_parser`), skill vocabulary (`skills_vocab`), job-description analysis (`jd_analyzer`) |
| `scraper/` | One module per source, `normalizer` (raw record to job dict), `relevance` (keyword filter), `service.scrape_jobs` (fan out, dedupe, cap), `manual_job` (pasted postings) |
| `db/` | SQLAlchemy models (`database`), all reads/writes (`repository`), backups and clean-up (`housekeeping`), Alembic `migrations/` |
| `matching/` | ATS keyword score, semantic score, location fit, skill gap, the weighted `confidence_score`, `evaluation` metrics |
| `generator/` | `llm.call_llm` (Ollama, then Gemini), cover letter, resume suggestions, requirement split, `fact_check`, document saving |
| `ui/` | `app.py` (tabs and flows), `components.py` (CSS, cards, helpers, source names), `export.py` (Word/PDF), `pages/privacy.py` and `pages/terms.py` (linked from the footer), `static/` (bundled fonts, favicon) |
| `api/` | The local HTTP layer for React: `main.py` (app, routes, serves `web/dist`), `server.py` (uvicorn on 127.0.0.1), `core.py` (settings, lazy imports), `catalog.py` (names and wording), `matching_view.py` (match annotation), `routes_*.py` (meta, resume, jobs, matches, documents). Read and call only: no source, score or prompt of its own |
| `web/` | React + Vite + TypeScript app: `src/state.tsx` (resume, country, model), `src/api.ts` (every call), `src/theme.css` (tokens), `src/tabs/` (the five tabs), `src/pages/` (privacy, terms), `public/` (favicon, bundled Geist) |
| `scripts/` | `init_db`, `housekeeping`, `evaluate_matching`, `record_demo` |

## Job sources

Every source returns normalized job dicts (`scraper/normalizer.normalize_job`). `service.scrape_jobs`
interleaves sources, dedupes on URL (else title+company+location) and caps at
`MAX_JOBS_PER_SESSION`. A failing source is logged and skipped.

| Key | Module | Kind | Default |
| --- | --- | --- | --- |
| `remoteok` | `remoteok_scraper` | Public JSON API | on |
| `hn` | `hn_scraper` | HN "Who's Hiring" via Algolia API | on |
| `themuse` | `muse_scraper` | Public API; "India" expanded to cities | on |
| `arbeitnow` | `arbeitnow_scraper` | Public API, mostly Europe | on |
| `himalayas` | `himalayas_scraper` | Public API, remote jobs filtered to the user's country | on |
| `greenhouse` | `ats_boards` | Company boards in `GREENHOUSE_BOARDS` | when configured |
| `lever` | `ats_boards` | Company boards in `LEVER_COMPANIES` | when configured |
| `linkedin` | `jobspy_source` | JobSpy library; robots.txt exception | only if in `JOBSPY_SITES` |
| `naukri` | `jobspy_source` | JobSpy library; robots.txt exception | only if in `JOBSPY_SITES` |
| `manual` / `linkedin` | `manual_job` | Posting pasted by the user; never fetched | always available |

API sources go through `scraper/net.py` (`polite_get_json`): allowlist check, robots.txt
check (fail closed), per-host rate limiter. JobSpy sources skip that path and are limited
instead by a per-site wait of `JOBSPY_REFRESH_MINUTES` stored in
`DOCS_DIR/.jobspy_last_run.json` (see SECURITY.md).

## Main flows

1. **Resume upload** (Resume tab): validate upload, parse, `repository.save_resume`, then
   score all stored jobs against it.
2. **Find jobs**: `scrape_jobs` for the picked sources, `upsert_jobs`, then score. While the
   page is open, a Streamlit fragment (`st.fragment(run_every=...)`) searches the JobSpy
   sites again when their wait is over.
3. **Scoring** (`ui/app._score_and_save`, `matching.confidence_score.score_jobs`):
   `total = 0.35 ATS + 0.30 experience + 0.25 semantic + 0.10 freshness`, multiplied by a
   location factor (1.0 to 0.4) when `CANDIDATE_COUNTRY` is set. Saved as `matches` rows.
4. **React**: the browser loads `web/dist` (or Vite's dev server, which proxies `/api`), reads
   `/api/catalog` and `/api/status` once, then calls the same functions as above through
   `api/routes_*.py`. Drafts stream from `/api/documents/draft` as the model writes them.
5. **Documents**: prompt built with resume and job text fenced by `prompt_guard`, sent to
   `stream_llm` (Ollama with `think: false` so thinking models such as qwen3.5 answer directly,
   then Gemini), shown as it is written with `st.write_stream`, checked by `fact_check`, saved to `docs_dir`
   and the `documents` table, exported by `ui/export.py`.

## Settings (`.env`, all optional)

| Variable | Default | Effect |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///jobhunt.db` | Database |
| `USE_OLLAMA`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | true, localhost:11434, mistral | Local LLM |
| `ALLOW_REMOTE_LLM` | false | Allow a non-local Ollama URL |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | empty, gemini-3.8-flash | Gemini fallback |
| `DOCS_DIR` | `~/jobhunt_docs` | Generated documents, backups, JobSpy run times |
| `SCRAPE_DELAY_SECONDS` | 3.0 | Minimum gap between requests to one host |
| `MAX_JOBS_PER_SESSION` | 50 | Cap per search |
| `UPLOAD_MAX_BYTES` | 2000000 | Resume upload limit |
| `GREENHOUSE_BOARDS`, `LEVER_COMPANIES` | empty | Company boards to read |
| `CANDIDATE_COUNTRY`, `CANDIDATE_CITIES` | empty | Location fit in scoring |
| `JOBSPY_SITES` | empty | `linkedin`, `naukri` to opt in |
| `JOBSPY_REFRESH_MINUTES` | 60 (min 30) | Wait between searches of one JobSpy site |
| `JOBSPY_HOURS_OLD`, `JOBSPY_RESULTS_PER_SITE` | 72, 15 | JobSpy result limits |
| `JOBSPY_AUTO_REFRESH` | true | Show the auto-refresh toggle |
| `JOBHUNT_API_PORT` | 8787 | Port of the local API for the React front end (127.0.0.1 only) |
| `LOG_LEVEL` | INFO | Log verbosity |

## Degrading gracefully

Heavy or optional libraries (spaCy, sentence-transformers, google-genai, JobSpy) are
imported lazily. Without them: skills come from the vocabulary only, semantic score uses
TF-IDF, Gemini is off, JobSpy sources return nothing. Streamlit loads modules through
`components.load` and the API through `api.core.load`; both turn a missing library into a
sentence (the API answers 503 with it) instead of crashing.
