# PRD: what we are building

> Keep this current. When a feature is added, changed or dropped, update this file in the
> same commit. Last reviewed: 2026-10-13.

## Problem

Arpit is a fresher in India looking for Java / React (full-stack) roles. Job postings are
spread over many sites, most are senior roles, and every application needs a resume and
cover letter tuned to the posting. Doing this by hand is slow and paid tools cost money.

## Product

JobHunt AI is a personal, local-first app that runs on one laptop (Windows 11 or macOS). It has
two front ends over one backend: the Streamlit app and a React app, which show the same data and
stay in step until the owner says the Streamlit one can go.

1. **Read the resume** (`.tex`, `.txt`, `.md`, `.pdf`) and pull out skills, experience and
   education. Skills the file misses can be typed in.
2. **Collect jobs** from free public job APIs, company career boards, an opt-in LinkedIn and
   Naukri source, or postings the user pastes in.
3. **Score every job** against the resume (0 to 100) and explain the score: matched and
   missing skills, years asked, whether the job is in or open to the user's country.
4. **Track applications**: save, hide, mark applied or rejected.
5. **Write documents**: a cover letter and resume suggestions per job, from a local LLM
   (Ollama) or the Gemini free tier, with sentences that claim more than the resume shows
   flagged. Export as Word or PDF.

## Users

One person, on their own machine. No accounts, no server, no sharing.

## Constraints

- **₹0 to run.** Free tools, free APIs, local models.
- **Private.** The resume and jobs stay in a local SQLite file. Nothing is sent anywhere
  except job searches and, if configured, LLM prompts to Gemini.
- **Polite collection.** Official APIs only, robots.txt obeyed, rate limited. The single
  exception is the opt-in JobSpy source for LinkedIn and Naukri (see SECURITY.md).
- **Works on a laptop CPU.** Small models, streaming output, fallbacks when ML libraries or
  the embedding model are missing (e.g. behind an office proxy).

## Features and where they live

| Feature | Tab | Status |
| --- | --- | --- |
| Upload / switch resume, add skills | Resume | Done |
| Search the free sources and company boards | Find jobs | Done |
| LinkedIn and Naukri via JobSpy (opt-in, at most hourly, auto-refresh while open) | Find jobs | Done 2026-10-12 |
| Paste a job yourself, open the search on LinkedIn | Find jobs | Done 2026-10-12 |
| Back up (CSV) and clean up old jobs | Find jobs | Done |
| Ranked matches with filters, score breakdown, skill gaps | Matches | Done |
| Skills to learn that would close near-miss jobs | Matches | Done |
| Saved / applied / rejected tracking | Applications | Done |
| Cover letter and resume suggestions, fact check, Word/PDF export | Documents | Done |
| Privacy policy and terms pages, linked from a footer on every page; favicon | All | Done 2026-10-12 |
| UI restyle (Geist type, indigo on warm paper, job list with detail pane) | All | In progress |
| React front end (`web/`) over a local API (`api/`), same five tabs and data | All | In progress 2026-10-13 |

## Out of scope (for now)

Auto-applying to jobs, logging in to job sites, multi-user use, hosting the app online,
email alerts.

## Success measures

- Matching quality on the labelled set (`eval/labeled_jobs.json`) via
  `scripts/evaluate_matching.py` (precision@k, nDCG@k) does not drop after a change.
- A full search plus scoring finishes in a few minutes on a laptop CPU.
- The user finds fresher-level Java / React jobs in India each week.
