"""Polite HTTP helpers shared by the scrapers: allowlist + robots.txt + rate limiting."""
from __future__ import annotations

import threading
from urllib.parse import urlsplit

import requests
from loguru import logger

from config import get_settings
from security.rate_limit import RateLimiter
from security.robots import can_fetch
from security.url_guard import is_allowed_url

USER_AGENT = "JobHuntAI-Learner"
BROWSER_HEADERS = {
    "User-Agent": f"Mozilla/5.0 (compatible; {USER_AGENT}/1.0; personal learning project)",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
DEFAULT_TIMEOUT = (5, 20)  # connect, read seconds
MAX_RESPONSE_BYTES = 10_000_000

_limiters: dict[str, RateLimiter] = {}
_lock = threading.Lock()


class FetchBlocked(Exception):
    """Raised when a URL is not allowlisted or robots.txt disallows it."""


def limiter_for(url: str) -> RateLimiter:
    """One RateLimiter per host, spaced by settings.scrape_delay_seconds."""
    host = (urlsplit(url).hostname or "").lower()
    with _lock:
        if host not in _limiters:
            _limiters[host] = RateLimiter(get_settings().scrape_delay_seconds)
        return _limiters[host]


def check_allowed(url: str) -> None:
    if not is_allowed_url(url):
        raise FetchBlocked(f"URL not on the allowlist: {url}")
    if not can_fetch(url, USER_AGENT):
        raise FetchBlocked(f"robots.txt disallows (or could not be checked for) {url}")


def polite_get_json(url: str, params: dict | list | None = None, timeout=DEFAULT_TIMEOUT):
    """GET ``url`` and return decoded JSON, after allowlist/robots checks and rate limiting.

    Raises ``FetchBlocked`` if disallowed and ``requests.RequestException``/``ValueError``
    on network or decoding errors.
    """
    check_allowed(url)
    limiter_for(url).wait()
    logger.debug("GET {} params={}", url, params)
    resp = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=timeout)
    resp.raise_for_status()
    if len(resp.content or b"") > MAX_RESPONSE_BYTES:
        raise ValueError(f"Response from {url} too large")
    return resp.json()


def keyword_terms(keywords: str) -> list[str]:
    """Split a keyword query into lowercase terms, dropping generic job words."""
    generic = {"developer", "engineer", "senior", "junior", "jr", "sr", "remote", "job", "jobs",
               "role", "the", "and", "or", "a", "an", "of", "in", "for", "lead", "staff", "mid"}
    terms = [t for t in (keywords or "").lower().replace(",", " ").split() if t]
    specific = [t for t in terms if t not in generic]
    return specific or terms


def contains_term(term: str, text: str) -> bool:
    """Word-boundary-safe, case-insensitive containment (works for c++, c#, node.js)."""
    import re

    return re.search(rf"(?<![a-z0-9+#]){re.escape(term.lower())}(?![a-z0-9+#])", text.lower()) is not None
