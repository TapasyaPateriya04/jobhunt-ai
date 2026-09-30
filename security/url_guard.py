"""URL allowlisting for scraping (anti-SSRF) and LLM endpoint restriction."""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

ALLOWED_JOB_HOSTS: frozenset[str] = frozenset({
    "indeed.com",
    "linkedin.com",
    "naukri.com",
    "remoteok.com",
    "remoteok.io",
    "hn.algolia.com",
    "news.ycombinator.com",
    "themuse.com",
    "arbeitnow.com",
    "boards-api.greenhouse.io",
    "api.lever.co",
})
LOCAL_LLM_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


def _hostname(url: str) -> str | None:
    """Return the lower-cased hostname of an http(s) URL without credentials, else ``None``."""
    if not isinstance(url, str) or not url or any(c in url for c in "\x00\r\n\t "):
        return None
    try:
        parts = urlsplit(url.strip())
        parts.port  # raises ValueError on a malformed port
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    return parts.hostname.lower().rstrip(".")


def is_allowed_url(url: str) -> bool:
    """True if ``url`` is http(s) and its host is an allowlisted job site (or a subdomain of one)."""
    host = _hostname(url)
    if host is None:
        return False
    try:
        ipaddress.ip_address(host)
        return False  # raw IPs are never job boards
    except ValueError:
        pass
    return any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_JOB_HOSTS)


def _remote_llm_allowed() -> bool:
    return (os.getenv("ALLOW_REMOTE_LLM") or "").strip().lower() in {"1", "true", "yes", "on"}


def validate_llm_endpoint(url: str) -> str:
    """Return ``url`` (without trailing slash) if it points at a local LLM server; else raise ``ValueError``.

    Remote hosts are accepted only when the env var ``ALLOW_REMOTE_LLM=true``.
    """
    host = _hostname(url)
    if host is None:
        raise ValueError("LLM endpoint must be an http(s) URL without credentials")
    if host not in LOCAL_LLM_HOSTS and not _remote_llm_allowed():
        raise ValueError(
            "LLM endpoint must be localhost/127.0.0.1/::1 (set ALLOW_REMOTE_LLM=true to override)"
        )
    return url.strip().rstrip("/")
