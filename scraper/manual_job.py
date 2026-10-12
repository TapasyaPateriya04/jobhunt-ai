"""Jobs the user adds by hand: a pasted posting, optionally with its link.

Nothing here touches the network. LinkedIn forbids automated access (its robots.txt
disallows every crawler), so a LinkedIn job reaches the app only when the user copies
the posting from their own browser and pastes it in. The link is stored as-is for
the user to open; the app never fetches it.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from scraper.normalizer import normalize_job

LINKEDIN_HOSTS = ("linkedin.com", "www.linkedin.com", "in.linkedin.com")
LINKEDIN_SEARCH = "https://www.linkedin.com/jobs/search/"
MAX_PASTE_CHARS = 30000

# LinkedIn's job page puts "Company · Location · 2 days ago · 40 applicants" under the title.
_DOT = re.compile(r"\s+[·•|]\s+")
_AGE = re.compile(r"\b(ago|reposted|applicants?|clicked apply|promoted|over \d+)\b", re.I)
_ABOUT = re.compile(r"^\s*about (the|this) (job|role)\s*$", re.I | re.M)


def is_linkedin_url(url: str) -> bool:
    host = (urlsplit(url or "").hostname or "").lower()
    return host in LINKEDIN_HOSTS or host.endswith(".linkedin.com")


def canonical_linkedin_url(url: str) -> str:
    """``.../jobs/view/<id>`` for any LinkedIn job link (view page or search with
    ``currentJobId``), so the same job pasted twice is stored once. Other links are
    returned unchanged."""
    url = (url or "").strip()
    if not is_linkedin_url(url):
        return url
    parts = urlsplit(url)
    m = re.search(r"/jobs/view/(?:[^/]*?-)?(\d{6,})", parts.path)
    job_id = m.group(1) if m else (parse_qs(parts.query).get("currentJobId") or [""])[0]
    if job_id.isdigit():
        return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return url


def linkedin_search_url(keywords: str, location: str = "") -> str:
    """A LinkedIn job search for the user to open in their own browser."""
    params = {"keywords": (keywords or "").strip()}
    if (location or "").strip():
        params["location"] = location.strip()
    return LINKEDIN_SEARCH + "?" + urlencode(params)


def guess_fields(text: str) -> dict:
    """Best guess at title, company, location and description from a pasted posting.

    The first line is taken as the title. A line like ``Acme · Bengaluru, India · 2 days
    ago`` gives the company and location. Text after "About the job" is the description
    when that heading is present, otherwise the whole paste is."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    out = {"title": "", "company": "", "location": "", "description": (text or "").strip()}
    if not lines:
        return out
    out["title"] = lines[0][:200]
    for ln in lines[1:6]:
        bits = [b.strip() for b in _DOT.split(ln) if b.strip() and not _AGE.search(b)]
        if len(bits) >= 2 and len(ln) <= 200:
            out["company"], out["location"] = bits[0][:200], bits[1][:200]
            break
    about = _ABOUT.search(text or "")
    if about:
        out["description"] = text[about.end():].strip()
    return out


def manual_job(text: str, url: str = "", title: str = "", company: str = "", location: str = "") -> dict:
    """Normalized job dict from what the user pasted. Fields the user typed win over guesses.
    The source is ``linkedin`` for a LinkedIn link and ``manual`` otherwise."""
    text = (text or "")[:MAX_PASTE_CHARS]
    url = (url or "").strip()
    guess = guess_fields(text)
    raw = {
        "title": (title or "").strip() or guess["title"],
        "company": (company or "").strip() or guess["company"],
        "location": (location or "").strip() or guess["location"],
        "description": guess["description"],
        "url": canonical_linkedin_url(url),
    }
    return normalize_job(raw, "linkedin" if is_linkedin_url(url) else "manual")
