"""LinkedIn and Naukri through JobSpy (python-jobspy), as an opt-in exception.

Every other source in this app is a public API that allows programs and is checked
against robots.txt first. LinkedIn and Naukri do not allow that: their robots.txt and
terms forbid automated access. They are used only when the user lists them in
``JOBSPY_SITES`` and then gently:

- each site is searched at most once per ``JOBSPY_REFRESH_MINUTES`` (30 at least,
  60 by default), whether the search was started by hand or by the page's auto-refresh;
  the last run is kept on disk so restarting the app does not reset the wait;
- a small number of results per site, only recent postings;
- no login and no proxies; JobSpy stops a site at its first non-200 answer (a 429
  "too many requests" included), and the wait still applies after a failed run.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from loguru import logger

from config import get_settings
from scraper.manual_job import canonical_linkedin_url
from scraper.normalizer import normalize_job

SITES = ("linkedin", "naukri")
STATE_FILE = ".jobspy_last_run.json"
_lock = threading.Lock()


def enabled_sites(settings=None) -> tuple[str, ...]:
    settings = settings or get_settings()
    return tuple(s for s in getattr(settings, "jobspy_sites", ()) if s in SITES)


def _state_path(settings) -> Path:
    return Path(getattr(settings, "docs_dir", "~/jobhunt_docs")).expanduser() / STATE_FILE


def _read_state(settings) -> dict:
    try:
        data = json.loads(_state_path(settings).read_text(encoding="utf-8"))
        return {k: float(v) for k, v in data.items() if k in SITES}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _write_state(settings, state: dict) -> None:
    path = _state_path(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Could not save the JobSpy run times: {}", type(exc).__name__)


def wait_seconds(site: str, settings=None, now: float | None = None) -> float:
    """Seconds until ``site`` may be searched again (0 when it may run now)."""
    settings = settings or get_settings()
    last = _read_state(settings).get(site)
    if last is None:
        return 0.0
    gap = int(getattr(settings, "jobspy_refresh_minutes", 60)) * 60
    return max(0.0, last + gap - (time.time() if now is None else now))


def last_run(site: str, settings=None) -> float | None:
    return _read_state(settings or get_settings()).get(site)


def _naukri_location(location: str, settings) -> str:
    # Naukri takes a city. A country (or "Remote") is replaced by the first configured city.
    loc = (location or "").split(";")[0].strip()
    country = (getattr(settings, "candidate_country", "") or "").strip().lower()
    if not loc or loc.lower() in {country, "india", "remote", "anywhere"}:
        cities = tuple(getattr(settings, "candidate_cities", ()) or ())
        return cities[0] if cities else ""
    return loc


def _to_job(row: dict, site: str) -> dict:
    url = str(row.get("job_url") or row.get("job_url_direct") or "")
    if site == "linkedin":
        url = canonical_linkedin_url(url)
    raw = {
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "description": row.get("description") or "",
        "url": url,
        "posted_date": row.get("date_posted"),
    }
    return normalize_job(raw, site)


def _clean(value):
    # pandas gives NaN / NaT for empty cells
    try:
        if value != value:  # NaN
            return None
    except Exception:
        pass
    return None if str(value) in {"NaT", "None", "nan"} else value


def fetch_jobspy(site: str, keywords: str, location: str, max_jobs: int = 15,
                 settings=None, now: float | None = None) -> list[dict]:
    """Search one JobSpy ``site`` unless it is switched off or ran too recently.
    Returns normalized jobs ([] when skipped or blocked)."""
    settings = settings or get_settings()
    if site not in enabled_sites(settings) or not (keywords or "").strip():
        return []
    with _lock:  # two browser tabs must not both start a search
        if wait_seconds(site, settings, now) > 0:
            logger.info("{}: skipped, searched less than {} min ago", site, settings.jobspy_refresh_minutes)
            return []
        state = _read_state(settings)
        state[site] = time.time() if now is None else now
        _write_state(settings, state)  # recorded before the search, so a failure still waits

    from jobspy import scrape_jobs  # optional dependency, imported only when used

    wanted = max(1, min(int(max_jobs or 1), int(getattr(settings, "jobspy_results_per_site", 15))))
    loc = _naukri_location(location, settings) if site == "naukri" else (location or "").split(";")[0].strip()
    try:
        df = scrape_jobs(
            site_name=[site],
            search_term=keywords.strip(),
            location=loc or None,
            results_wanted=wanted,
            hours_old=int(getattr(settings, "jobspy_hours_old", 72)),
            fetch_description=True,  # the description is what the resume is scored against
            verbose=0,
        )
    except Exception as exc:
        logger.warning("{} via JobSpy failed: {}", site, type(exc).__name__)
        return []
    if df is None or getattr(df, "empty", True):
        logger.info("{}: no jobs (none matched, or the site refused the request)", site)
        return []
    rows = [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]
    return [_to_job(r, site) for r in rows[:wanted]]
