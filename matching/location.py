"""Can the candidate actually take this job, given where they live?

``location_fit(job, country, cities)`` reads a posting's location line and description and
returns ``{"status", "score", "reason"}``:

    local       100  in the candidate's country (a preferred city is named in the reason)
    remote_open  90  remote and open worldwide, or to a region that includes the country
    remote       70  remote, no restriction stated
    unknown      50  no usable location information
    restricted    0  remote but limited to other countries, other time zones, or a language
    elsewhere     0  on-site or hybrid in another country

It is rule-based and deliberately small: a gazetteer of countries, their main tech cities
and the phrases postings use to restrict applicants ("US only", "must reside in ...").
With no country configured every job gets a neutral pass, so nothing changes.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

LOCAL, REMOTE_OPEN, REMOTE, UNKNOWN, RESTRICTED, ELSEWHERE = (
    "local", "remote_open", "remote", "unknown", "restricted", "elsewhere")
SCORES = {LOCAL: 100.0, REMOTE_OPEN: 90.0, REMOTE: 70.0, UNKNOWN: 50.0, RESTRICTED: 0.0, ELSEWHERE: 0.0}
LABELS = {LOCAL: "In your country", REMOTE_OPEN: "Remote, open to you", REMOTE: "Remote",
          UNKNOWN: "Location unclear", RESTRICTED: "Restricted", ELSEWHERE: "Another country"}
# A job the candidate cannot take keeps this share of its score; a local one keeps all of it.
MIN_FACTOR = 0.4

# country -> lowercase names and cities that identify it in a posting
PLACES: dict[str, tuple[str, ...]] = {
    "India": ("india", "bangalore", "bengaluru", "gurgaon", "gurugram", "hyderabad", "pune", "mumbai",
              "chennai", "noida", "greater noida", "delhi", "new delhi", "delhi ncr", "kolkata",
              "ahmedabad", "kochi", "jaipur", "chandigarh", "indore", "coimbatore", "navi mumbai"),
    "United States": ("united states", "usa", "u.s.a", "u.s", "new york", "nyc", "san francisco",
                      "bay area", "seattle", "austin", "boston", "chicago", "los angeles", "denver",
                      "atlanta", "dallas", "houston", "miami", "washington", "palo alto",
                      "mountain view", "san jose", "san diego", "portland", "philadelphia",
                      "redwood city", "sunnyvale", "santa clara", "menlo park", "cupertino",
                      "cincinnati", "northern virginia", "silicon valley"),
    "United Kingdom": ("united kingdom", "uk", "u.k", "england", "scotland", "london", "manchester",
                       "edinburgh", "cambridge", "oxford", "bristol", "glasgow"),
    "Canada": ("canada", "toronto", "vancouver", "montreal", "ottawa", "ontario", "calgary"),
    "Germany": ("germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt",
                "cologne", "köln", "nuremberg", "nürnberg", "stuttgart", "düsseldorf", "konstanz"),
    "France": ("france", "paris", "lyon", "île-de-france"),
    "Switzerland": ("switzerland", "zurich", "zürich", "zug", "geneva", "lausanne", "basel", "olten"),
    "Netherlands": ("netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven"),
    "Ireland": ("ireland", "dublin"),
    "Spain": ("spain", "madrid", "barcelona"),
    "Portugal": ("portugal", "lisbon", "porto"),
    "Poland": ("poland", "warsaw", "krakow", "kraków", "wroclaw"),
    "Romania": ("romania", "bucharest"),
    "Sweden": ("sweden", "stockholm"),
    "Belgium": ("belgium", "brussels"),
    "Austria": ("austria", "vienna"),
    "Italy": ("italy", "milan", "rome"),
    "Denmark": ("denmark", "copenhagen"),
    "Israel": ("israel", "tel aviv"),
    "United Arab Emirates": ("united arab emirates", "uae", "dubai", "abu dhabi"),
    "Singapore": ("singapore",),
    "Malaysia": ("malaysia", "kuala lumpur"),
    "Philippines": ("philippines", "cebu", "manila"),
    "Pakistan": ("pakistan", "lahore", "karachi"),
    "Japan": ("japan", "tokyo"),
    "China": ("china", "shanghai", "beijing", "shenzhen"),
    "Hong Kong": ("hong kong",),
    "Australia": ("australia", "sydney", "melbourne"),
    "New Zealand": ("new zealand", "auckland"),
    "Brazil": ("brazil", "são paulo", "sao paulo"),
    "Mexico": ("mexico", "mexico city"),
    "Costa Rica": ("costa rica",),
}
REGIONS: dict[str, tuple[str, ...]] = {  # region word -> member countries we know about
    "apac": ("India", "Singapore", "Malaysia", "Philippines", "Japan", "China", "Hong Kong",
             "Australia", "New Zealand", "Pakistan"),
    "asia": ("India", "Singapore", "Malaysia", "Philippines", "Japan", "China", "Hong Kong", "Pakistan",
             "Israel", "United Arab Emirates"),
    "europe": ("United Kingdom", "Germany", "France", "Switzerland", "Netherlands", "Ireland", "Spain",
               "Portugal", "Poland", "Romania", "Sweden", "Belgium", "Austria", "Italy", "Denmark"),
    "emea": ("United Kingdom", "Germany", "France", "Switzerland", "Netherlands", "Ireland", "Spain",
             "Portugal", "Poland", "Romania", "Sweden", "Belgium", "Austria", "Italy", "Denmark",
             "Israel", "United Arab Emirates"),
    "americas": ("United States", "Canada", "Brazil", "Mexico", "Costa Rica"),
    "north america": ("United States", "Canada", "Mexico"),
    "latam": ("Brazil", "Mexico", "Costa Rica"),
}
REGIONS["eu"] = REGIONS["europe"]
REGIONS["amer"] = REGIONS["americas"]
REGIONS["northern america"] = REGIONS["north america"]
_GERMAN_SPEAKING = {"Germany", "Austria", "Switzerland"}

_US_STATE_RE = re.compile(
    r",\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|"
    r"NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC|D\.C\.)\b")
_US_TOKEN_RE = re.compile(r"(?<![A-Za-z])US(?![A-Za-z])")  # "US" but not "us"
_UK_TOKEN_RE = re.compile(r"(?<![A-Za-z])UK(?![A-Za-z])")
_REMOTE_RE = re.compile(r"\b(remote|remoto|anywhere|everywhere|worldwide|distributed|work from home|wfh)\b", re.I)
_WORLDWIDE_RE = re.compile(
    r"\b(worldwide|anywhere|everywhere|global(?:ly)?|any ?where in the world|any (?:country|time ?zone)|"
    r"all (?:countries|time ?zones))\b", re.I)
_ONSITE_RE = re.compile(r"\b(on-?site|hybrid|in[- ]office|in person)\b", re.I)
# Sentences that limit who may apply; the places they name decide the outcome.
_RESTRICT_RES = [
    re.compile(p, re.I) for p in (
        r"[^.\n|]{0,60}\b(only|residents?|citizens?|persons)\b[^.\n|]{0,60}",
        r"[^.\n|]{0,20}\bmust (?:reside|be based|be located|live|be)\b[^.\n|]{0,80}",
        r"[^.\n|]{0,20}\b(?:applicants|candidates) must\b[^.\n|]{0,80}",
        r"[^.\n|]{0,40}\bauthori[sz]ed to work\b[^.\n|]{0,60}",
        r"[^.\n|]{0,60}\b(?:visa|sponsor(?:ship)?)\b[^.\n|]{0,60}",
        r"[^.\n|]{0,40}\btime ?zones?\b[^.\n|]{0,40}",
        r"[^.\n|]{0,30}\b(?:PT|ET|EST|PST|CST|CET|GMT)\b[^.\n|]{0,10}\b(?:hours|overlap|window)\b[^.\n|]{0,30}",
        r"\bremote\s*[(\[–:-]\s*[^)\]\n|]{2,60}",
    )]
_NO_SPONSOR_RE = re.compile(r"\b(no|not|unable to|cannot|can't|without|don't|do not)\b[^.\n]{0,30}\bsponsor", re.I)
_US_TZ_RE = re.compile(r"\b(PT|ET|EST|PST|CST|EDT|PDT)\b|\b(?:US|U\.S\.|American?|eastern|pacific) time", re.I)
_GERMAN_RE = re.compile(r"\((?:m/w/d|w/m/d|m/f/d|f/m/d|m/w/x)\)|\b(?:gute|fließend\w*|sehr gute)\s+deutsch|"
                        r"\b(?:good|fluent|native|business[- ]level)\s+german\b|\bgerman (?:is )?required", re.I)
_GERMAN_WORDS_RE = re.compile(r"\b(und|für|mit|wir|sie|der|die|das|eine|ist|bei|oder)\b", re.I)
_ENGLISH_OK_RE = re.compile(r"\b(?:english[- ]speaking|working language is english|no german (?:required|needed))\b", re.I)


def _places(text: str) -> tuple[set[str], set[str]]:
    """Countries and region words named in ``text``."""
    low = " " + (text or "").lower() + " "
    countries = {c for c, names in PLACES.items()
                 if any(re.search(rf"(?<![a-zà-ÿ]){re.escape(n)}(?![a-zà-ÿ])", low) for n in names
                        if n not in ("uk", "u.s", "u.k"))}
    if _US_TOKEN_RE.search(text or "") or _US_STATE_RE.search(text or "") or re.search(r"\bu\.s\.", low):
        countries.add("United States")
    if _UK_TOKEN_RE.search(text or "") or "u.k" in low:
        countries.add("United Kingdom")
    regions = {r for r in REGIONS if re.search(rf"(?<![a-z]){re.escape(r)}(?![a-z])", low)
               and (r != "eu" or re.search(r"(?<![A-Za-z])EU(?![A-Za-z])", text or ""))}
    return countries, regions


def _covers(country: str, countries: set[str], regions: set[str]) -> bool:
    return country in countries or any(country in REGIONS[r] for r in regions)


def _result(status: str, reason: str) -> dict:
    return {"status": status, "score": SCORES[status], "reason": reason}


def normalize_country(name: str) -> str:
    """Map user input ("india", "USA", "Bangalore") to a gazetteer country, else title-case it."""
    low = (name or "").strip().lower()
    if not low:
        return ""
    for country, names in PLACES.items():
        if low == country.lower() or low in names:
            return country
    return {"us": "United States", "america": "United States"}.get(low, (name or "").strip().title())


def location_fit(job: dict, country: str, cities: Iterable[str] = ()) -> dict:
    """Where ``job`` stands for a candidate living in ``country`` (see module docstring)."""
    country = normalize_country(country)
    if not country:
        return {"status": UNKNOWN, "score": 100.0, "reason": "No home country set"}
    job = job or {}
    loc = str(job.get("location") or "")
    desc = str(job.get("description") or job.get("snippet") or "")
    header = f"{job.get('title') or ''} | {loc} | {desc[:300]}"  # HN posts keep the place in line one
    loc_countries, loc_regions = _places(loc)
    head_countries, head_regions = _places(header)
    remote = bool(_REMOTE_RE.search(loc)) or (
        not _ONSITE_RE.search(header) and bool(_REMOTE_RE.search(header))) or job.get("source") == "remoteok"
    onsite = bool(_ONSITE_RE.search(header)) and not re.search(r"\bor\s+remote|remote\s+or\b|remote possible", header, re.I)

    # Language: a German-language posting needs German.
    if country not in _GERMAN_SPEAKING and not _ENGLISH_OK_RE.search(desc) and (
            _GERMAN_RE.search(f"{job.get('title') or ''} {desc}") and len(_GERMAN_WORDS_RE.findall(desc)) > 12
            or len(_GERMAN_WORDS_RE.findall(desc)) > 40
            or re.search(r"\b(?:good|fluent|native)\s+german\b|german (?:is )?required|deutschkenntnisse", desc, re.I)):
        return _result(RESTRICTED, "Needs German")

    if country in loc_countries or (not loc_countries and country in head_countries):
        city = next((c for c in cities or () if c and c.strip().lower() in header.lower()), None)
        return _result(LOCAL, f"In {city.strip().title()}" if city else f"In {country}")

    # Who may apply?
    excluded = ""
    for pattern in _RESTRICT_RES:
        for m in pattern.finditer(f"{loc}\n{desc}"):
            phrase = m.group(0)
            countries, regions = _places(phrase)
            if _US_TZ_RE.search(phrase) and re.search(r"time ?zone|hours|overlap|window", phrase, re.I):
                countries.add("United States")
            sponsor = bool(_NO_SPONSOR_RE.search(phrase))
            if not countries and not regions:
                if sponsor and (loc_countries or head_countries):
                    excluded = excluded or "No visa sponsorship"
                continue
            if _covers(country, countries, regions):
                continue
            if re.search(r"\bonly\b|residents?|citizens?|persons|must|authori[sz]ed|sponsor|time ?zone|hours|"
                         r"overlap|remote\s*[(\[–:-]", phrase, re.I):
                named = sorted(countries) or sorted(r.upper() if len(r) <= 4 else r.title() for r in regions)
                excluded = excluded or f"Limited to {', '.join(named[:2])}"
    if excluded:
        return _result(RESTRICTED, excluded)

    places = loc_countries or head_countries
    regions = loc_regions | head_regions
    if remote:
        # "Anywhere" only counts from the location line once a place is named ("anywhere in the UK").
        if _WORLDWIDE_RE.search(f"{job.get('title') or ''} {loc}") or (
                not places and _WORLDWIDE_RE.search(desc[:1500])):
            return _result(REMOTE_OPEN, "Remote, worldwide")
        if not loc_countries and regions and _covers(country, set(), regions):
            return _result(REMOTE_OPEN, "Remote, your region")
        if places or regions:
            named = sorted(places) or sorted(r.title() for r in regions)
            return _result(RESTRICTED, f"Remote in {', '.join(named[:2])}")
        return _result(REMOTE, "Remote, no restriction stated")
    if places:
        return _result(ELSEWHERE, f"{'On-site' if onsite else 'Based'} in {', '.join(sorted(places)[:2])}")
    if regions and not _covers(country, set(), regions):
        return _result(ELSEWHERE, f"Based in {', '.join(sorted(r.title() for r in regions)[:2])}")
    return _result(UNKNOWN, "Location not stated")


def location_factor(score: Optional[float]) -> float:
    """Multiplier applied to a job's total: 1.0 for a local job down to ``MIN_FACTOR``."""
    s = 100.0 if score is None else max(0.0, min(100.0, float(score)))
    return MIN_FACTOR + (1.0 - MIN_FACTOR) * s / 100.0


__all__ = ["location_fit", "location_factor", "normalize_country", "LABELS", "SCORES",
           "LOCAL", "REMOTE_OPEN", "REMOTE", "UNKNOWN", "RESTRICTED", "ELSEWHERE"]
