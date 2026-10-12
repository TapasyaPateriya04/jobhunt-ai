"""Privacy policy page, linked from the footer of every page."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui import components as c  # noqa: E402

c.page_setup("Privacy policy · JobHunt AI")
st.page_link("app.py", label="Back to JobHunt AI")
st.title("Privacy policy")
st.caption("Last updated 12 October 2026")
st.markdown("""
JobHunt AI is a personal job-search tool that runs on your own computer. There is no account,
no server run by us and no usage tracking: Streamlit's usage statistics are switched off. This
page says what the app stores, where it keeps it, and the few cases in which something leaves
your computer.

### What the app stores

Everything is kept on your computer:

- **Your resume.** A copy of the file you upload goes to the `uploads` folder inside your
  documents folder (`DOCS_DIR`, by default `~/jobhunt_docs`). The text and skills read from
  it are saved in the app's database.
- **Jobs and scores.** Jobs the app collects or you paste in, their match scores and the
  status you give them (saved, applied, rejected) are saved in a SQLite database file
  (`DATABASE_URL`, by default `jobhunt.db` in the app folder).
- **Documents you generate.** Cover letters, resume suggestions and backups are written to
  your documents folder.

The app writes its log to the terminal it runs in and does not keep it. API keys are removed
from log lines.

### What leaves your computer

- **Job searches.** When you press **Find jobs**, your search keywords (and your location,
  where the source supports it) are sent to the job sources you ticked (RemoteOK, Hacker News, The Muse, Arbeitnow, Himalayas, and
  any Greenhouse or Lever company boards set in `.env`). Your resume is not sent.
- **LinkedIn and Naukri, only if you turn them on.** If `JOBSPY_SITES` in `.env` lists them,
  the same search is sent to those sites through the JobSpy library. This is
  off by default.
- **Writing with a language model.** By default cover letters and resume suggestions are
  written by Ollama on your own computer, so your resume and the job description stay here.
  If you set `GEMINI_API_KEY` and Ollama is not available, the app sends your resume text and
  the job description to Google's Gemini API instead, and Google's terms then apply to that
  text. Without a key, nothing is sent.
- **The matching model.** The first time it runs, the app downloads a small open model
  (`all-MiniLM-L6-v2`) from Hugging Face. Only the download request is sent; your resume is
  not.
- **Opening a posting.** **Open posting** opens the employer's or job board's page in your
  browser, where that site's own privacy policy applies.

### Deleting your data

Use **Back up or clean up stored jobs** on the Find jobs tab to delete old jobs, or delete the
database file and the documents folder to remove everything. The app keeps no copies anywhere
else. Text you sent to Gemini and searches you sent to job sites are held by those services
under their own policies.

### Changes

If the app starts handling data differently, this page is updated in the same change and the
date above moves forward.
""")
c.legal_footer()
