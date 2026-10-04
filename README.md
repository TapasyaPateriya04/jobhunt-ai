# 🎯 JobHunt AI — Budget Learner's Edition

A local-first job hunting assistant that costs ₹0/month. It scrapes job listings, parses your resume,
scores how well you match each job, and drafts cover letters and resume edits with a free LLM.
Everything runs on your laptop. The full plan lives in [docs/SPEC.md](docs/SPEC.md).

| Layer | Tool |
|-------|------|
| Scraping | Free APIs: RemoteOK, HN "Who's Hiring" (Algolia), The Muse, Arbeitnow, Greenhouse and Lever company boards. Experimental: Playwright + BeautifulSoup4 (Indeed / LinkedIn / Naukri) |
| Parsing | pylatexenc, regex, spaCy (optional) |
| Matching | scikit-learn TF-IDF + SentenceTransformers `all-MiniLM-L6-v2` (TF-IDF fallback if not installed) |
| LLM | Ollama (Mistral / Llama 3.2) locally, Gemini free tier as fallback |
| Database | SQLite via SQLAlchemy (PostgreSQL-ready) |
| UI | Streamlit on `localhost:8501` |

## Workflow

```
Resume (.tex/.txt/.md/.pdf) ─► parser ─► SQLite ◄─ scraper (RemoteOK, HN, The Muse, Arbeitnow, ...)
                                            │
                                            ▼
                         matching: 0.35 ATS + 0.30 experience + 0.25 semantic + 0.10 freshness
                                            │
                                            ▼
                     Streamlit dashboard ─► cover letter / resume suggestions (Ollama or Gemini)
```

## Quick start

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                               # edit if you use Gemini

# Optional extras
playwright install chromium                        # only for the experimental Indeed/LinkedIn/Naukri scrapers
python -m spacy download en_core_web_sm            # better skill hints
ollama pull llama3.2:3b                            # local LLM (https://ollama.com); mistral if you have a GPU

python scripts/init_db.py                          # creates or upgrades jobhunt.db
streamlit run ui/app.py                            # open http://localhost:8501
```

On Windows: if `spacy download` fails with a 404, install the model wheel directly with
`pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl`.
Ollama installs with `winget install Ollama.Ollama`. On a CPU-only laptop the first Mistral
generation can take about two minutes.

### Windows setup

The app is developed on Windows 11 with Python 3.10, and CI tests Windows with Python 3.11. Run these in PowerShell from the
project folder.

```powershell
py -3.11 -m venv .venv                                   # or: python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m playwright install chromium     # only for the experimental scrapers
winget install Ollama.Ollama                             # then, in a new terminal:
ollama pull llama3.2:3b
.venv\Scripts\python -m streamlit run ui/app.py
```

- **Always start the app with `.venv\Scripts\python`.** Plain `python` or `streamlit` may be a
  different Python without the project's libraries; the app then says a library such as
  `sqlalchemy` is missing.
- **Activating the environment** (`.venv\Scripts\Activate.ps1`) is optional. If PowerShell refuses
  to run it, use the `.venv\Scripts\python` form above, or allow local scripts once with
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **spaCy model**: `python -m spacy download en_core_web_sm` can fail with a 404 on Windows; install
  the wheel directly instead (see the note above).
- **First run downloads the MiniLM model** (about 90 MB) into `%USERPROFILE%\.cache\huggingface`.
  Scoring works offline afterwards, and falls back to keyword similarity if the download fails.
- **Ollama on a laptop without a GPU**: use a small model. `ollama pull llama3.2:3b` writes a cover
  letter in about a minute on a mid-range laptop CPU; Mistral 7B can take five. Pick the model in the
  sidebar's **Model for writing**, or set the default with `OLLAMA_MODEL=llama3.2:3b` in `.env`.
  Replies are streamed, so a slow model is only stopped if it goes quiet for 5 minutes.
- **The app only listens on localhost** (`.streamlit/config.toml`), so others on your Wi-Fi cannot
  open it. Keep it that way: your resume and job data are in it.
- **Tests**: one test creates a symlink, which Windows only allows with Developer Mode or an admin
  terminal; it is skipped otherwise. Git's CRLF line endings are handled by the parser.

Or run the whole pipeline from the terminal:

```bash
python pipeline.py --resume my_resume.tex --keywords "Python Developer" --location Remote --max-jobs 20 --sources remoteok,hn,themuse,arbeitnow
```

## Project layout

```
config.py        settings from .env
security/        input sanitizing, URL allowlist, robots.txt, rate limiting, prompt fencing, log redaction
db/              SQLAlchemy models, repository helpers, Alembic migrations, housekeeping
scraper/         source scrapers + normalizer + scrape_jobs() service
parser/          resume parser and job description analyzer
matching/        ATS scorer, semantic matcher, confidence score
generator/       LLM client, cover letters, resume suggestions, saved documents
ui/              Streamlit dashboard
pipeline.py      end-to-end CLI
tests/           pytest suite (no network, no heavy models needed)
```

## Job sources

| Source | `--sources` name | Notes |
|--------|------------------|-------|
| RemoteOK | `remoteok` | Free public API. On by default. |
| HN "Who's Hiring" | `hn` | Latest monthly thread via the Algolia API. On by default. |
| The Muse | `themuse` | Free public API, large companies worldwide including India. Uses the location you give. On by default. |
| Arbeitnow | `arbeitnow` | Free public API, mostly Europe. On by default. |
| Greenhouse boards | `greenhouse` | Companies you list in `GREENHOUSE_BOARDS` (e.g. `gitlab`). |
| Lever boards | `lever` | Companies you list in `LEVER_COMPANIES` (e.g. `palantir`). |
| Indeed, LinkedIn, Naukri | `indeed`, `linkedin`, `naukri` | **Experimental**, off by default. See below. |

The Muse has no keyword search and needs locations spelled its own way, separated by `;`:
`--location "Bangalore, India; Gurgaon, India; Hyderabad, India; Pune, India"`. "Remote" (the
default) searches its "Flexible / Remote" jobs. Entry-level software roles in India are rare
there; most listings are mid or senior level.

For Greenhouse and Lever the slug is the last part of the company's careers URL:
`boards.greenhouse.io/<slug>` or `jobs.lever.co/<slug>`.

Jobs are kept only when they are relevant to your keywords: a keyword must be in the job
title or mentioned at least twice in the description (see `scraper/relevance.py`).

## Using the app

Start it with the project's environment (`.venv\Scripts\python -m streamlit run ui/app.py` on
Windows); a different Python will be missing libraries. The line above the tabs shows your
numbers and the next step to take.

- **Resume tab**: upload a resume, or a newer version of it (skills you added by hand carry over,
  and your stored jobs are scored against it straight away). Type skills your file doesn't
  mention into **Add a skill**. Switch between stored resumes in the sidebar.
- **Find jobs tab**: collect postings from the sources you pick. At the bottom, **Back up or clean
  up stored jobs** downloads jobs and scores as CSV and deletes postings older than a number of
  days you choose (30 by default). Jobs you saved, applied to or wrote a document for are kept.
- **Matches tab**: search by title, company, location or skill; sliders, checkboxes and dropdowns
  narrow the list; **Reset filters** clears them. Each card shows the score with its band
  (strong 50+, possible 35 to 49, weak), the years asked, whether you can take the job and the
  skills you have (✓) and lack (✕). **Save** and **Hide** work from the card; the expander holds
  the score breakdown, must-have skills and the full posting. **Skills worth adding** lists jobs
  only 1 to 3 skills short. After scraping, adding skills or changing your country, click
  **Score stored jobs**.
- **Applications tab**: every job you saved, applied to or were rejected for, with its status.
  **Write documents** picks the job on the Documents tab.
- **Documents tab**: draft a cover letter or resume suggestions with the local model (or Gemini),
  edit the draft and download it as .txt, .docx or .pdf.

### Demo video

`python scripts/record_demo.py` records a 50-second captioned walkthrough of the running app
(resume, finding jobs, matches, applications, documents) as an MP4 in `<docs_dir>/demo/`. It needs
Playwright's Chromium and ffmpeg. The video shows your own resume and jobs, so it is kept out of
the repository; share it only if you are happy for others to see them.

## Database

The schema is managed with Alembic (`db/migrations`). The app applies migrations when it starts,
and databases made before migrations existed are upgraded in place without losing data. To change
the schema, edit the models in `db/database.py`, then:

```bash
alembic revision --autogenerate -m "describe the change"   # review the file it writes
alembic upgrade head                                       # or just restart the app
```

`tests/test_housekeeping.py` fails if the models and the migrations drift apart.

Housekeeping from the terminal:

```bash
python scripts/housekeeping.py status               # schema version and how many jobs are stale
python scripts/housekeeping.py backup               # CSVs + a copy of jobhunt.db in <docs_dir>/backups
python scripts/housekeeping.py clean --days 30      # report only; add --yes to delete
```

SQLite is enough for one person's job search. The code only uses portable SQLAlchemy, so moving
to PostgreSQL later means changing `DATABASE_URL` and running `alembic upgrade head`.

## Matching quality

The score is `0.35 ATS + 0.30 experience + 0.25 semantic + 0.10 freshness`:

- **ATS**: half TF-IDF keyword overlap, half skill coverage (share of the posting's known skills
  that are on your resume).
- **Experience**: 100 when you meet the years asked, minus 20 points per missing year. When a
  posting states no number, seniority words in the title ("Senior", "Lead", "Junior") stand in;
  with no cue at all the score is a neutral 70.
- **Semantic**: MiniLM sentence-embedding similarity, scaled from the range seen on real postings.
- **Freshness**: newer postings score higher.
- **Location**: set `CANDIDATE_COUNTRY` in `.env` (for example `India`) and the total is multiplied
  by 1.0 for a job in your country, 0.94 for worldwide remote, down to 0.4 for a job on-site abroad
  or restricted to other countries, time zones or a language you were not asked about. The Matches
  tab can hide those jobs and filter by the years of experience a posting asks for.

These weights differ from the plan's 0.35/0.25/0.20/0.20 because they were measured:

```bash
python scripts/evaluate_matching.py --snapshot   # once: copy the labeled jobs from your database
python scripts/evaluate_matching.py --weights    # precision@5, nDCG@10 and a ranked list
```

`eval/labeled_jobs.json` holds 52 real postings labeled good / partial / bad fit for one resume.
On that set precision@5 went from 0.00 (plan weights and formulas) to 0.60, and nDCG@10 from
0.07 to 0.85 once the home country is used. Edit the labels if you disagree with them, add your
own, and re-run after any change under `matching/`. The set is small, so treat differences of
one job in the top 5 as noise. Location rules are keyword-based (`matching/location.py`): a
restriction worded in an unusual way can be missed, so read the posting before applying.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q             # offline unit tests (what CI runs)
python -m pytest -m live -v     # opt-in smoke tests against the real job APIs
python -m pytest -m localdata   # opt-in: prompt-injection checks over every posting in your jobhunt.db
pip-audit -r requirements.txt --no-deps --disable-pip   # known vulnerabilities in the pinned packages
```

CI runs the tests on Ubuntu and Windows, and `pip-audit` on every push and each Monday. Both
requirements files are pinned to exact versions; when `pip-audit` reports a vulnerable package,
bump its pin in both files, reinstall and re-run the tests.

`tests/test_prompt_injection.py` plants attacks (instructions to the model, fake end-of-data
markers, chat-template tokens, invisible characters) at the start, middle and end of real scraped
postings in `tests/fixtures/real_jds.json`, and checks every prompt keeps them fenced off as data.

## Ethical scraping

Prefer the official/free APIs above. Every request checks `robots.txt`, waits between requests and
each session is capped at 50 jobs. RemoteOK asks that you link back to the job and credit
it as the source; the stored job URL does that.

Indeed, LinkedIn and Naukri are **experimental** and off by default. LinkedIn's `robots.txt`
disallows the job search, Naukri answers automated browsers with "Access Denied", and Indeed sits
behind bot protection and restricts scraping in its Terms of Service. The scrapers return nothing
when blocked and must never be changed to get around a block. See [SECURITY.md](SECURITY.md).
