"""robots.txt compliance with a per-host cache. Fails closed: any error means "do not fetch"."""
from __future__ import annotations

import threading
import time
import urllib.request
from urllib import robotparser
from urllib.error import HTTPError
from urllib.parse import urlsplit

from security.url_guard import is_allowed_url

DEFAULT_USER_AGENT = "JobHuntAI-Learner"
TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 3600.0
MAX_ROBOTS_BYTES = 512_000

_cache: dict[str, tuple[float, robotparser.RobotFileParser | None]] = {}
_lock = threading.Lock()


def _fetch_parser(origin: str, user_agent: str) -> robotparser.RobotFileParser | None:
    """Download and parse ``origin/robots.txt``; ``None`` means fetching is not permitted."""
    parser = robotparser.RobotFileParser(origin + "/robots.txt")
    request = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310 (host allowlisted)
            final = resp.geturl()
            if final and not is_allowed_url(final):
                return None  # redirected off the allowlist
            body = resp.read(MAX_ROBOTS_BYTES).decode("utf-8", errors="replace")
    except HTTPError as exc:
        if 400 <= exc.code < 500 and exc.code not in (401, 403, 429):
            parser.parse([])  # no robots.txt => everything allowed (RFC 9309)
            return parser
        return None
    except Exception:
        return None
    parser.parse(body.splitlines())
    return parser


def can_fetch(url: str, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """True only if ``url`` is allowlisted and its host's robots.txt permits ``user_agent``."""
    if not is_allowed_url(url):
        return False
    parts = urlsplit(url)
    origin = f"{parts.scheme.lower()}://{parts.netloc.lower()}"
    now = time.monotonic()
    with _lock:
        cached = _cache.get(origin)
    if cached is None or now - cached[0] > CACHE_TTL_SECONDS:
        parser = _fetch_parser(origin, user_agent)
        with _lock:
            _cache[origin] = (now, parser)
    else:
        parser = cached[1]
    if parser is None:
        return False
    try:
        return parser.can_fetch(user_agent, url)
    except Exception:
        return False


def clear_cache() -> None:
    """Forget all cached robots.txt results (mainly for tests)."""
    with _lock:
        _cache.clear()
