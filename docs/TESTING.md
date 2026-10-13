# Testing: how we know it works

> Keep this current. New test files, markers or CI steps update this file in the same commit.
> Last reviewed: 2026-10-12.

## Run

```bash
python -m pytest -q                 # everything that runs offline (about 1 080 tests, ~30 s)
python -m pytest -m live -v         # also hit the real job APIs (needs network)
python -m pytest -m localdata       # also check your own jobhunt.db postings
python scripts/evaluate_matching.py # matching quality on the labelled jobs
```

Behind a proxy that breaks SSL to huggingface.co (the office network), set
`HF_HUB_OFFLINE=1`, or the UI tests time out while the embedding model retries.

## Layout

| File | Covers |
| --- | --- |
| `tests/test_config.py` | Settings parsing and defaults |
| `tests/test_security.py` | Sanitising, uploads, path traversal, URL allowlist, robots, rate limiter, log redaction |
| `tests/test_prompt_injection.py` | Real postings stay fenced in every prompt |
| `tests/test_parser.py` | Resume and job-description parsing |
| `tests/test_scraper.py`, `tests/test_api_sources.py` | Normalizer, relevance filter, each API source with recorded responses, `service` |
| `tests/test_jobspy_source.py` | JobSpy source: off by default, field mapping, the per-site wait (also across restarts and failures) |
| `tests/test_manual_job.py` | Pasted postings: field guessing, LinkedIn link clean-up, no network |
| `tests/test_location.py`, `tests/test_matching.py` | Location fit, scores, skill gaps |
| `tests/test_db.py`, `tests/test_housekeeping.py` | Repository, migrations, backups, clean-up |
| `tests/test_generator.py`, `tests/test_fact_check.py` | LLM calls (mocked), documents, claim checks |
| `tests/test_ui.py` | Streamlit `AppTest` smoke tests of every tab and main flow |
| `tests/test_legal_pages.py` | Privacy and terms pages render and are linked; UI code keeps the design rules (no em dashes, emoji, pill shapes or gradients) |
| `tests/test_docs.py` | The docs in `docs/` name every job source, setting, table and column |
| `tests/test_live.py` | `live` marker: real network calls |

Fixtures live in `tests/fixtures/` (recorded API responses, sample resumes, real job
descriptions).

## Rules

- **No network in default tests.** Mock HTTP (`monkeypatch` on `requests` or the source
  function); fake optional libraries with `monkeypatch.setitem(sys.modules, ...)`. The
  autouse fixture in `tests/conftest.py` blanks `CANDIDATE_COUNTRY`, `CANDIDATE_CITIES` and
  `JOBSPY_SITES`, so a developer's `.env` never changes results or reaches LinkedIn/Naukri.
- **Isolated database**: use `db_session` / `tmp_db_url`, or `ui_env` for UI tests; never the
  real `jobhunt.db` (except `localdata` tests).
- **Every bug fix gets a test** that fails before the fix. Every new source, setting or UI
  flow gets at least one test.
- **Tests run without heavy libraries**: CI installs only `requirements-dev.txt` (no torch,
  spaCy model or JobSpy), so code must degrade and tests must not import them directly.

## CI (`.github/workflows`)

- `test`: Ubuntu and Windows, Python 3.11, `pip install -r requirements-dev.txt`,
  `python -m pytest -q`.
- `audit`: `pip-audit` on both requirement files and the installed test environment;
  also runs every Monday.

## Before asking for a commit

1. `python -m pytest -q` passes.
2. For UI changes: start the app (`python -m streamlit run ui/app.py`) and click through the
   changed screen, including an empty and an error state.
3. For matching changes: `scripts/evaluate_matching.py` does not get worse.
