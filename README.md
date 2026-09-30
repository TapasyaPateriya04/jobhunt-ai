# 🎯 JobHunt AI — Budget Learner's Edition

A local-first job hunting assistant that costs ₹0/month. It scrapes job listings, parses your resume,
scores how well you match each job, and drafts cover letters and resume edits with a free LLM.
Everything runs on your laptop. The full plan lives in [docs/SPEC.md](docs/SPEC.md).

| Layer | Tool |
|-------|------|
| Scraping | RemoteOK API, HN "Who's Hiring" (Algolia API), Playwright + BeautifulSoup4 (Indeed / LinkedIn / Naukri) |
| Parsing | pylatexenc, regex, spaCy (optional) |
| Matching | scikit-learn TF-IDF + SentenceTransformers `all-MiniLM-L6-v2` (TF-IDF fallback if not installed) |
| LLM | Ollama (Mistral / Llama 3.2) locally, Gemini free tier as fallback |
| Database | SQLite via SQLAlchemy (PostgreSQL-ready) |
| UI | Streamlit on `localhost:8501` |

## Workflow

```
Resume (.tex/.txt/.md/.pdf) ─► parser ─► SQLite ◄─ scraper (RemoteOK, HN, Playwright sites)
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
playwright install chromium                        # for Indeed/LinkedIn/Naukri scrapers
python -m spacy download en_core_web_sm            # better skill hints
ollama pull mistral                                # local LLM (https://ollama.ai)

python scripts/init_db.py                          # creates jobhunt.db
streamlit run ui/app.py                            # open http://localhost:8501
```

Or run the whole pipeline from the terminal:

```bash
python pipeline.py --resume my_resume.tex --keywords "Python Developer" --location Remote --max-jobs 20 --sources remoteok,hn
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

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Ethical scraping

Prefer official/free APIs (RemoteOK, HN). The Playwright scrapers check `robots.txt`, wait between
requests and cap each session at 50 jobs. Scraping Indeed/LinkedIn may break their Terms of Service;
keep it to personal, low-volume learning use. See [SECURITY.md](SECURITY.md).
