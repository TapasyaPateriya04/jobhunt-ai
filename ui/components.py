"""Reusable Streamlit UI helpers for JobHunt AI.

Everything here is presentation-only: no business logic, no secrets. Helpers
that touch other packages import them lazily so a missing/broken module shows a
friendly message instead of crashing the whole dashboard.
"""
from __future__ import annotations

import html
import importlib
import json
import logging
import urllib.request
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

import streamlit as st

log = logging.getLogger("jobhunt.ui")

MATCH_STATUSES = ["new", "saved", "applied", "rejected"]

SOURCES = {
    "remoteok": "RemoteOK (free public API)",
    "hn": "Hacker News 'Who's Hiring' (Algolia API)",
    "remotive": "Remotive (free public API)",
    "arbeitnow": "Arbeitnow (free public API, mostly Europe)",
    "greenhouse": "Greenhouse company boards (set GREENHOUSE_BOARDS in .env)",
    "lever": "Lever company boards (set LEVER_COMPANIES in .env)",
    "indeed": "Indeed (experimental: needs Playwright, check ToS)",
    "linkedin": "LinkedIn (experimental: blocked by robots.txt)",
    "naukri": "Naukri (experimental: blocks automated browsers)",
}
DEFAULT_SOURCES = ["remoteok", "hn", "remotive", "arbeitnow"]
EXPERIMENTAL_SOURCES = ["indeed", "linkedin", "naukri"]

ETHICAL_NOTE = (
    "**Scrape responsibly.** Prefer official/free APIs (RemoteOK, HN Who's Hiring, Remotive, "
    "Arbeitnow, Greenhouse and Lever company boards). For HTML portals the scraper checks "
    "`robots.txt` and skips disallowed sites, waits 3-5 s between requests, caps each "
    "session at 20-50 jobs, and caches results so the same job is never re-scraped. "
    "Indeed, LinkedIn and Naukri are **experimental**: they restrict automated access, "
    "usually return nothing, and are for personal learning only. Read each site's Terms "
    "of Service before enabling them."
)

LLM_HELP = (
    "No language model is available right now. To enable document generation either:\n\n"
    "1. **Run Ollama locally (free):** install from https://ollama.com, then run "
    "`ollama pull mistral` and `ollama serve` (default http://localhost:11434), or\n"
    "2. **Use Gemini's free tier:** put `GEMINI_API_KEY=...` in your `.env` file and restart the app."
)

CSS = """
<style>
.jh-chips {display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 12px 0;}
.jh-chip {background:rgba(79,70,229,.10); color:#4338ca; border:1px solid rgba(79,70,229,.25);
          border-radius:999px; padding:2px 10px; font-size:.82rem; line-height:1.5;}
.jh-chip.miss {background:rgba(220,38,38,.08); color:#b91c1c; border-color:rgba(220,38,38,.25);}
.jh-chip.ok {background:rgba(22,163,74,.10); color:#15803d; border-color:rgba(22,163,74,.25);}
.jh-muted {color:#6b7280; font-size:.85rem;}
@media (prefers-color-scheme: dark) {
  .jh-chip {color:#c7d2fe;} .jh-chip.miss {color:#fca5a5;} .jh-chip.ok {color:#86efac;}
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- errors

class FeatureUnavailable(RuntimeError):
    """Raised when an optional project module cannot be imported."""


def load(module: str, attr: Optional[str] = None) -> Any:
    """Import ``module`` (and optionally return ``attr``), raising FeatureUnavailable."""
    try:
        mod = importlib.import_module(module)
        return getattr(mod, attr) if attr else mod
    except Exception as exc:  # ImportError, AttributeError, or import-time failure
        log.warning("Could not load %s%s: %s", module, f".{attr}" if attr else "", exc)
        raise FeatureUnavailable(f"`{module}` is not available yet ({type(exc).__name__}).") from exc


@contextmanager
def friendly_errors(action: str) -> Iterator[None]:
    """Show a readable error instead of a traceback when ``action`` fails."""
    try:
        yield
    except FeatureUnavailable as exc:
        st.warning(f"Could not {action}: {exc}")
    except ValueError as exc:
        # Validation errors (upload checks, bad input) carry user-facing messages.
        st.error(f"Could not {action}: {exc}")
    except Exception as exc:
        log.exception("UI action failed: %s", action)
        st.error(f"Something went wrong while trying to {action} ({type(exc).__name__}). "
                 "Details were written to the log.")


# --------------------------------------------------------------------------- display

def chips(items: Iterable[str], kind: str = "") -> None:
    items = [str(i) for i in items if str(i).strip()]
    if not items:
        st.markdown('<span class="jh-muted">None found.</span>', unsafe_allow_html=True)
        return
    cls = f"jh-chip {kind}".strip()
    body = "".join(f'<span class="{cls}">{html.escape(i)}</span>' for i in items)
    st.markdown(f'<div class="jh-chips">{body}</div>', unsafe_allow_html=True)


def g(d: Optional[dict], *keys: str, default: Any = None) -> Any:
    """First non-None value among ``keys`` in ``d``."""
    if not d:
        return default
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


def as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except (ValueError, TypeError):
            return [value]
    return list(value)


def fmt_score(v: Any) -> str:
    try:
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return "-"


def experience_line(item: Any) -> str:
    if isinstance(item, dict):
        title = g(item, "title", "role", "position", default="")
        org = g(item, "company", "organization", "org", default="")
        dates = g(item, "dates", "duration", "period", default="")
        if not dates and (item.get("start") or item.get("end")):
            dates = f"{item.get('start') or ''} - {item.get('end') or ''}"
        head = " @ ".join(p for p in (str(title), str(org)) if p)
        line = f"**{head}**" if head else ""
        if dates:
            line += f" <span class='jh-muted'>({html.escape(str(dates))})</span>"
        return line or html.escape(json.dumps(item)[:200])
    return html.escape(str(item))


def match_label(m: dict) -> str:
    company = g(m, "company", default="Unknown company")
    title = g(m, "title", default="Untitled role")
    score = fmt_score(g(m, "confidence_score", "total"))
    return f"{company} - {title}  ({score}%)"


# --------------------------------------------------------------------------- backend status

@st.cache_data(ttl=30, show_spinner=False)
def ollama_reachable(base_url: str) -> bool:
    """Quick (1 s) probe of Ollama's /api/tags. Only local endpoints are probed."""
    try:
        try:
            guard = load("security.url_guard", "validate_llm_endpoint")
            base_url = guard(base_url)
        except FeatureUnavailable:
            pass
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/tags", timeout=1) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except Exception:
        return False


def status_row(label: str, ok: bool, ok_text: str, bad_text: str) -> None:
    icon = "🟢" if ok else "⚪"
    st.markdown(f"{icon} **{label}:** {ok_text if ok else bad_text}")


def db_location(url: str) -> str:
    """Human display of the database location without any credentials."""
    if url.startswith("sqlite"):
        return url.split("///", 1)[-1] or ":memory:"
    # Strip user:password@ from server URLs.
    scheme, _, rest = url.partition("://")
    return f"{scheme}://{rest.rsplit('@', 1)[-1]}"
