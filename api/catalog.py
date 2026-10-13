"""Names the front end shows for sources, statuses and score bands.

Kept here rather than imported from ``ui/components.py`` so the API process does
not have to import Streamlit. ``tests/test_api.py`` checks the keys still match
the Streamlit app's, and that no wording names the scraping library.
"""
from __future__ import annotations

MATCH_STATUSES = ["new", "saved", "applied", "rejected", "hidden"]
STATUS_LABELS = {"new": "New", "saved": "Saved", "applied": "Applied",
                 "rejected": "Rejected", "hidden": "Hidden"}
TRACKED_STATUSES = ["saved", "applied", "rejected"]
TRACK_HINTS = {"saved": "to apply to", "applied": "waiting to hear back", "rejected": "closed"}

# key: (short name, one line of help)
SOURCES = {
    "remoteok": ("RemoteOK", "Free public API of remote jobs."),
    "hn": ("Hacker News Who's Hiring", "The monthly thread, read through the Algolia API."),
    "themuse": ("The Muse", "Free public API. Needs its own spelling of a place, e.g. Bangalore, India."),
    "arbeitnow": ("Arbeitnow", "Free public API, mostly Europe."),
    "himalayas": ("Himalayas", "Free public API of remote jobs open to your country."),
    "greenhouse": ("Greenhouse company boards", "The company boards named in GREENHOUSE_BOARDS in .env."),
    "lever": ("Lever company boards", "The company boards named in LEVER_COMPANIES in .env."),
    "linkedin": ("LinkedIn", "Off unless you turn it on in .env. Searched at most once an hour."),
    "naukri": ("Naukri", "Off unless you turn it on in .env. Searched at most once an hour."),
}
ADDED_SOURCES = {"manual": ("Added by you", "A posting you pasted in yourself.")}
OPT_IN_SOURCES = ["linkedin", "naukri"]
DEFAULT_SOURCES = ["remoteok", "hn", "themuse", "arbeitnow", "himalayas"]
BOARD_SOURCES = ["greenhouse", "lever"]

SCORE_BANDS = [
    {"key": "hi", "label": "Strong match", "min": 50},
    {"key": "mid", "label": "Possible match", "min": 35},
    {"key": "low", "label": "Weak match", "min": 0},
]

# What each part of the score measures, shown next to the breakdown bars.
SCORE_PARTS = [
    {"key": "ats", "label": "Skills and keywords", "weight": 0.35,
     "about": "How many of the skills and words the posting asks for appear in your resume."},
    {"key": "experience", "label": "Experience fit", "weight": 0.30,
     "about": "Your years against the years the posting asks for. Full marks when you meet or pass them."},
    {"key": "semantic", "label": "Meaning match", "weight": 0.25,
     "about": "How close the posting reads to your resume overall, not word by word."},
    {"key": "freshness", "label": "Freshness", "weight": 0.10,
     "about": "How recently the job was posted. Older postings are often already filled."},
]
SCORE_NOTE = ("The match score is 35% skills and keywords, 30% experience fit, 25% meaning match and "
              "10% freshness. It is then lowered when the job is not open to your location.")

DOC_TYPES = {"cover_letter": "Cover letter", "resume_suggestions": "Resume suggestions"}

SORTS = ["Best match", "Fewest missing skills", "Newest posting", "Least experience asked"]

# Location statuses a candidate cannot act on (see matching/location.py).
BLOCKED_LOCATIONS = ("restricted", "elsewhere")

COLLECTION_NOTE = [
    ("Official, free job APIs by default",
     "RemoteOK, Hacker News Who's Hiring, The Muse, Arbeitnow, Himalayas and the Greenhouse and Lever "
     "company boards publish their jobs for programs to read. For these the app checks the site's "
     "robots.txt before every request and skips the site if it disallows it, waits 3 to 5 seconds "
     "between requests, caps each search and stores results so the same job is never fetched twice."),
    ("LinkedIn and Naukri are an exception you opt into",
     "Their robots.txt and terms forbid automated access, so they are off unless you turn them on in "
     ".env. When on, they are searched with no login and no proxies, at most once an hour. Indeed is "
     "never used. You can also paste a posting in yourself under Add a job yourself."),
]


def source_name(key) -> str:
    key = str(key or "")
    if key in ADDED_SOURCES:
        return ADDED_SOURCES[key][0]
    return SOURCES[key][0] if key in SOURCES else key


def status_name(status) -> str:
    return STATUS_LABELS.get(str(status), str(status).capitalize())


def score_band(value) -> dict:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"key": "none", "label": "Not scored", "min": 0}
    return next(b for b in SCORE_BANDS if v >= b["min"])
