"""Terms and conditions page, linked from the footer of every page."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui import components as c  # noqa: E402

c.page_setup("Terms and conditions · JobHunt AI")
st.page_link("app.py", label="Back to JobHunt AI")
st.title("Terms and conditions")
st.caption("Last updated 12 October 2026")
st.markdown("""
These terms cover your use of JobHunt AI, a personal job-search tool that you run on your own
computer. By running the app you agree to them.

### What the app does

The app collects job postings from public sources, scores each one against your resume and
helps you draft cover letters and resume changes. It is a helper for your own job search, not
a recruiting service, and nobody reviews your applications on your behalf.

### Your responsibilities

- **Check everything you send.** Match scores are estimates from keyword and text
  comparison. Drafts written by a language model can be wrong or overstate your experience;
  the app flags claims it cannot find in your resume, but it can miss some. Read and correct
  every draft before you send it to an employer.
- **Respect the job sites.** The built-in sources are public APIs and job boards whose
  robots.txt allows the app, and the app limits how often it asks them. LinkedIn and Naukri
  do not allow automated access. If you turn them on through `JOBSPY_SITES`, you do so
  against those sites' terms and at your own risk, including the risk that they block you.
- **Keep your keys private.** If you add a Gemini API key, it is yours to protect, and your
  use of Gemini is covered by Google's terms.
- **Use it for your own search.** Do not use the app to collect jobs for resale or to send
  bulk applications.

### Job postings

Postings belong to the employers and sites that published them. The app shows them as it
received them and cannot confirm that a job is real, still open or accurately described.
Always apply through the employer's own page.

### No warranty

The app is provided as it is, without any warranty. It may contain bugs, a source may stop
working, and stored data can be lost if your computer fails, so keep backups (the app can
export your jobs as CSV). To the extent the law allows, the author is not liable for any loss
that comes from using it, including a missed or failed application.

### Changes

These terms can change as the app changes. The date above shows the latest version.
""")
c.legal_footer()
