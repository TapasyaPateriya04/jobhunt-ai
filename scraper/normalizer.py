"""Normalize job postings from any source into the shared job dict.

Normalized job dict (docs/CONTRACTS.md):
    {"title", "company", "location", "description", "source", "url",
     "posted_date": datetime | None, "experience_years": int | None}
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from security.sanitize import sanitize_text

_WORD_NUMS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
}
_NUM = r"(\d{1,2}|" + "|".join(_WORD_NUMS) + r")"
_YEARS = r"(?:years?|yrs?)\b"
# "3+ years", "2-4 yrs", "3 to 5 years", "5 plus years", "at least 3 years", "minimum of 2 years"
_EXP_RE = re.compile(
    rf"(?P<pre>at\s+least|minimum(?:\s+of)?|min\.?|over|more\s+than)?\s*"
    rf"(?P<low>{_NUM})\s*(?P<plus>\+|plus)?\s*"
    rf"(?:(?:-|–|—|to)\s*(?P<high>{_NUM})\s*\+?\s*)?"
    rf"{_YEARS}(?=(?P<post>[^.;\n]{{0,60}}))",
    re.IGNORECASE,
)


def _num(s: str | None) -> int | None:
    if not s:
        return None
    s = s.lower()
    return int(s) if s.isdigit() else _WORD_NUMS.get(s)


def extract_experience_years(text) -> int | None:
    """Required years of experience mentioned in ``text`` (lower bound of a range; the
    largest such requirement when several are listed). ``None`` when not found."""
    if not text:
        return None
    found: list[int] = []
    for m in _EXP_RE.finditer(str(text)):
        low = _num(m.group("low"))
        if low is None or low > 30:
            continue
        post = (m.group("post") or "").lower()
        strong = bool(m.group("plus") or m.group("pre") or m.group("high"))
        contextual = bool(re.search(r"\b(experience|exp\b|professional|industry|working|hands[- ]on|"
                                    r"in\s+(a|an|the)?\s*\w+|of\s+\w+|with\s+\w+|building|developing)", post))
        if re.match(r"\s*(old|ago|warranty|guarantee|history|in\s+business)", post):
            continue
        if strong or contextual:
            found.append(low)
    return max(found) if found else None


def html_to_text(html: str) -> str:
    """Strip HTML tags, keeping paragraph/line structure."""
    if not html:
        return ""
    if "<" not in html and "&" not in html:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_posted_date(value) -> datetime | None:
    """Parse datetimes, epoch seconds/ms, ISO strings and relative text ("3 days ago",
    "Just posted", "30+ days ago") into a naive UTC datetime."""
    if value is None or value == "":
        return None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:  # milliseconds
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return parse_posted_date(int(s))
    iso = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass
    low = s.lower()
    if re.search(r"just\s+(now|posted)|today|few\s+(minutes|hours)\s+ago|^new$|active\s+today", low):
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\s*\+?\s*(minute|min|m|hour|hr|h|day|d|week|wk|w|month|mo)s?\b", low)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ("minute", "min", "m"):
            delta = timedelta(minutes=n)
        elif unit in ("hour", "hr", "h"):
            delta = timedelta(hours=n)
        elif unit in ("day", "d"):
            delta = timedelta(days=n)
        elif unit in ("week", "wk", "w"):
            delta = timedelta(weeks=n)
        else:
            delta = timedelta(days=30 * n)
        return now - delta
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _first(raw: dict, *keys):
    for k in keys:
        v = raw.get(k)
        if v not in (None, "", []):
            return v
    return None


def _clean_line(v, max_len: int = 300) -> str:
    s = html_to_text(str(v)) if v is not None else ""
    return re.sub(r"\s+", " ", sanitize_text(s, max_len=max_len)).strip()


def normalize_job(raw: dict, source: str) -> dict:
    """Map a raw scraped/API job record to the normalized job dict."""
    raw = raw or {}
    title = _clean_line(_first(raw, "title", "position", "jobTitle", "job_title", "role", "name"))
    company = _clean_line(_first(raw, "company", "company_name", "companyName", "employer", "organization"))
    location = _clean_line(_first(raw, "location", "candidate_required_location", "job_location",
                                  "companyLocation", "city") or "")
    desc_raw = _first(raw, "description", "snippet", "summary", "text", "comment_text", "body") or ""
    description = sanitize_text(html_to_text(str(desc_raw)), max_len=20000).strip()
    url = str(_first(raw, "url", "apply_url", "link", "job_url", "href") or "").strip()
    if url and not re.match(r"^https?://", url, re.I):
        url = ""
    posted = parse_posted_date(_first(raw, "posted_date", "date", "epoch", "created_at",
                                      "created_at_i", "posted", "posted_at", "time"))
    exp = raw.get("experience_years")
    try:
        exp = int(exp) if exp not in (None, "") else None
    except (TypeError, ValueError):
        exp = extract_experience_years(str(exp))
    if exp is None:
        exp = extract_experience_years(f"{title}\n{description}")
    return {
        "title": title or "Untitled role",
        "company": company or "Unknown company",
        "location": location,
        "description": description,
        "source": source,
        "url": url[:2000],
        "posted_date": posted,
        "experience_years": exp,
    }
