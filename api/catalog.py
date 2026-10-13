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

# Band keys come from matching.confidence_score.band(); the thresholds are read from there
# at run time (api/routes_meta.py) so the two front ends can never show different numbers.
BAND_LABELS = {"strong": "Strong fit", "possible": "Worth a look", "weak": "Reach",
               "none": "Not scored"}

# What each part of the score measures, shown next to the breakdown bars. "group" is the half
# of the formula the part belongs to, "share" its weight inside that half.
SCORE_PARTS = [
    {"key": "ats", "label": "Skills and keywords", "group": "fit", "share": 0.6,
     "about": "Half the share of the posting's skills that are on your resume, half how many of "
              "its important words your resume uses."},
    {"key": "semantic", "label": "Meaning match", "group": "fit", "share": 0.4,
     "about": "How close the posting and your resume are in meaning, not just in words."},
    {"key": "experience", "label": "Experience fit", "group": "reach", "share": 0.75,
     "about": "100 when you have the years the job asks for, 20 points less for each year short. "
              "70 when the posting does not say."},
    {"key": "freshness", "label": "Freshness", "group": "reach", "share": 0.25,
     "about": "100 for jobs posted in the last day, down to 30 after two weeks."},
]
SCORE_NOTE = ("Fit is 60% skills and 40% meaning, and is the ceiling. Reach, 75% experience and "
              "25% freshness, decides how much of that fit the job keeps. The total is then "
              "lowered when the job is not open to your location.")

# The "What the scores mean" guide. {strong}, {possible}, {title_cap}, {strong_skills} and
# {possible_skills} are filled from matching/confidence_score.py.
SCORE_GUIDE = [
    ("How the score is worked out",
     ["The match score, 0 to 100, says how well your resume fits the job, lowered when the job is "
      "hard to reach for you right now.",
      "Fit is 60% skills and keywords plus 40% meaning match. It is the ceiling: a job can never "
      "score higher than its fit.",
      "Reach is 75% experience fit plus 25% freshness. A job you can fully reach keeps all of its "
      "fit; one you cannot reach yet keeps 40% of it.",
      "The total is then lowered if the job is not open to your country."]),
    ("What the bands mean",
     ["Strong fit is {strong} and above, worth a look {possible} to {strong_minus}, reach below "
      "{possible}.",
      "A job can only be strong when its skills score is {strong_skills} or more, and only "
      "possible when it is {possible_skills} or more, so experience and freshness alone never "
      "make a job look good.",
      "The skills score is capped at {title_cap} when the job title names a skill you do not have, "
      "for example a Databricks Developer role without Databricks."]),
    ("Reading a job's skills",
     ["A tick means the skill is on your resume, a cross means it is not.",
      "Skills come from a fixed list, so very short names (C, Go, R) can sometimes be picked up by "
      "mistake. Read the posting before you apply."]),
]

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


def band_label(band: str) -> str:
    return BAND_LABELS.get(str(band), BAND_LABELS["none"])
