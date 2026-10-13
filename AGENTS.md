# AGENTS.md: how an AI coding agent should work here

> Read this first. Keep it current: when the owner states a new rule or preference, add it
> here in the same session. Last reviewed: 2026-10-13.

## Project in one line

JobHunt AI is a personal, local-first app that collects jobs, scores them against the owner's
resume and drafts cover letters. It has two front ends: the Streamlit app (`ui/`) and a React
app (`web/`) over a local read-and-call API (`api/`). Owner: Arpit, an India-based fresher looking
for Java / React roles. Repo: `TapasyaPateriya04/jobhunt-ai`.

## Read before changing code

| Doc | Question it answers |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | What are we building? |
| [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | What should it look and feel like? |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How should the system work? |
| [docs/DATABASE.md](docs/DATABASE.md) | What data exists and how does it relate? |
| [SECURITY.md](SECURITY.md) | What must be protected and how? |
| [docs/CODE_STYLE.md](docs/CODE_STYLE.md) | How should code be written? |
| [docs/TESTING.md](docs/TESTING.md) | How will we know it works? |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | Function signatures each module promises |

## Keep the docs current (required)

Every change updates the docs it affects **in the same commit**:

| You changed | Update |
| --- | --- |
| A feature the user sees | PRD.md feature table, README.md "Using the app" |
| Theme, CSS tokens, a UI pattern | DESIGN_SYSTEM.md |
| A module, job source, setting or flow | ARCHITECTURE.md, CONTRACTS.md, `.env.example`, README.md |
| A model, column or migration | DATABASE.md |
| Anything touching untrusted input, secrets, network or scraping rules | SECURITY.md |
| A convention | CODE_STYLE.md |
| Tests, markers, CI | TESTING.md |
| A rule from the owner | this file |

Bump "Last reviewed" on each doc you touch. `tests/test_docs.py` checks that every job
source, setting, table and column is named in the docs, so a forgotten update fails CI.

## Owner's working rules

- **Ask before every commit.** Show what changed and wait for a yes. The owner pushes and
  merges; never push, open or merge a PR unless asked.
- **Work on a branch** (e.g. `claude/<topic>`), not on `main`.
- **Keep existing UI controls** (sliders, checkboxes, expanders, tabs); add a control only
  where there was none. Use the `streamlit-ui-ux` skill for Streamlit work.
- **Two front ends, one backend** (owner's ask, 2026-10-13): the React app is being built in
  `web/` with a thin API in `api/`. The API only calls existing backend functions; a change to
  scoring, scraping or generation belongs in the Python modules, not in `api/` or `web/`. Both
  front ends stay working until the owner says the Streamlit one can go.
- **Scraping**: official APIs only, robots.txt obeyed, rate limited. The only exception is
  the opt-in JobSpy source for LinkedIn and Naukri, approved 2026-10-12: no login, no
  proxies, at most once per `JOBSPY_REFRESH_MINUTES` (60 by default; the owner asked for
  refreshes every 30 to 60 minutes only while the page is open, never every second). Do not
  add other exceptions without asking.
- **Writing rules** (UI and docs): no em dashes, no emoji icons, no purple gradients, no pill
  shapes.
- **Never name the scraping library in the UI** (owner's rule, 2026-10-12): user-visible text says
  "LinkedIn" / "Naukri" and "turn them on in .env", not "JobSpy" or `JOBSPY_*` keys. Code, `.env`
  keys and docs may name it; `tests/test_legal_pages.py` checks the UI strings.
- **Personal data**: never copy, upload or commit the resume, `.env` or `jobhunt.db`.
- **Defaults for search**: country India, roles Java / React, fresher level.
- **Ask before installing system software** (Ollama models, Homebrew packages). Python
  packages go in `.venv` and are pinned in `requirements.txt`.

## Environment notes

- Windows 11 (personal laptop) and macOS (office MacBook,
  `~/Documents/python_scripts/jobhunt-ai`). Use the project's `.venv`:
  `.venv/bin/python -m streamlit run ui/app.py` (macOS) or
  `.venv\Scripts\python -m streamlit run ui/app.py` (Windows).
- The office network breaks SSL to huggingface.co: the semantic score falls back to TF-IDF
  and tests need `HF_HUB_OFFLINE=1`.
- Several agent sessions may share one checkout. Before committing, check `git status` and
  stage only your own files; never commit another session's work in progress.

## Definition of done

Code, tests and docs updated together; `python -m pytest -q` green; UI changes checked in
the running app; a short summary of what the user will see; commit only after the owner
says yes.
