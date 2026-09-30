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
                         matching: 0.35 ATS + 0.25 experience + 0.20 semantic + 0.20 freshness
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
ollama pull mistral                                # local LLM (https://ollama.ai)

python scripts/init_db.py                          # creates jobhunt.db
streamlit run ui/app.py                            # open http://localhost:8501
```

On Windows: if `spacy download` fails with a 404, install the model wheel directly with
`pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl`.
Ollama installs with `winget install Ollama.Ollama`. On a CPU-only laptop the first Mistral
generation can take about two minutes.

Or run the whole pipeline from the terminal:

```bash
python pipeline.py --resume my_resume.tex --keywords "Python Developer" --location Remote --max-jobs 20 --sources remoteok,hn,themuse,arbeitnow
```

## Project layout

```
config.py        settings from .env
security/        input sanitizing, URL allowlist, robots.txt, rate limiting, prompt fencing, log redaction
db/              SQLAlchemy models (Resume, Job, Match, Document) and repository helpers
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

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q             # offline unit tests (what CI runs)
python -m pytest -m live -v     # opt-in smoke tests against the real job APIs
```

## Ethical scraping

Prefer the official/free APIs above. Every request checks `robots.txt`, waits between requests and
each session is capped at 50 jobs. RemoteOK asks that you link back to the job and credit
it as the source; the stored job URL does that.

Indeed, LinkedIn and Naukri are **experimental** and off by default. LinkedIn's `robots.txt`
disallows the job search, Naukri answers automated browsers with "Access Denied", and Indeed sits
behind bot protection and restricts scraping in its Terms of Service. The scrapers return nothing
when blocked and must never be changed to get around a block. See [SECURITY.md](SECURITY.md).
