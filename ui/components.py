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
import re
import sys
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Optional

import streamlit as st

log = logging.getLogger("jobhunt.ui")

MATCH_STATUSES = ["new", "saved", "applied", "rejected", "hidden"]
STATUS_LABELS = {"new": "New", "saved": "Saved", "applied": "Applied", "rejected": "Rejected", "hidden": "Hidden"}
TRACKED_STATUSES = ["saved", "applied", "rejected"]

SOURCES = {
    "remoteok": "RemoteOK (free public API)",
    "hn": "Hacker News 'Who's Hiring' (Algolia API)",
    "themuse": "The Muse (free public API, uses Location, e.g. Bangalore, India)",
    "arbeitnow": "Arbeitnow (free public API, mostly Europe)",
    "greenhouse": "Greenhouse company boards (set GREENHOUSE_BOARDS in .env)",
    "lever": "Lever company boards (set LEVER_COMPANIES in .env)",
    "indeed": "Indeed (experimental: needs Playwright, check ToS)",
    "linkedin": "LinkedIn (experimental: blocked by robots.txt)",
    "naukri": "Naukri (experimental: blocks automated browsers)",
}
DEFAULT_SOURCES = ["remoteok", "hn", "themuse", "arbeitnow"]
EXPERIMENTAL_SOURCES = ["indeed", "linkedin", "naukri"]

ETHICAL_NOTE = (
    "**Scrape responsibly.** Prefer official/free APIs (RemoteOK, HN Who's Hiring, The Muse, "
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

CSS = r"""
<style>
/* Colors come from .streamlit/config.toml; this sheet only styles the app's own markup
   (cards, chips, score, empty states). No animation, no web fonts: the app stays offline. */
:root {
  --jh-ink:#0f172a; --jh-ink-2:#334155; --jh-muted:#5b6678; --jh-line:#e2e8f0; --jh-line-2:#cbd5e1;
  --jh-surface:#ffffff; --jh-wash:#f1f5f9;
  --jh-accent:#0f766e; --jh-accent-ink:#115e59; --jh-accent-wash:#e6f2f0;
  --jh-ok:#166534; --jh-ok-wash:#e8f4ec; --jh-warn:#9a4a07; --jh-warn-wash:#fbf0e1;
  --jh-bad:#b91c1c; --jh-bad-wash:#fbeaea;
  --jh-r:6px;
}
[data-testid="stMainBlockContainer"], .block-container {max-width:1080px; padding-top:2.2rem; padding-bottom:4rem;}
h1 {font-size:1.9rem !important; font-weight:700 !important; letter-spacing:-.02em; padding-bottom:.1rem !important;}
h3 {font-size:1.3rem !important; font-weight:650 !important; letter-spacing:-.01em;}
h4 {font-size:1.02rem !important; font-weight:650 !important; padding-top:1rem !important;}
*:focus-visible {outline:2px solid var(--jh-accent) !important; outline-offset:2px;}
[data-testid="stWidgetLabel"] p {font-weight:600; color:var(--jh-ink-2); font-size:.88rem;}
[data-testid="stForm"] {border:0; padding:0;}
[data-testid="stSidebar"] code {overflow-wrap:anywhere; white-space:normal;}

.jh-panel-title {font-size:.76rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  color:var(--jh-muted); margin:0 0 2px 0;}
.jh-muted {color:var(--jh-muted); font-size:.86rem;}

/* chips: a tick or a cross carries the meaning, color only reinforces it */
.jh-chips, .jh-tags {display:flex; flex-wrap:wrap; gap:6px; margin:4px 0 12px 0;}
.jh-chip, .jh-tag {font-size:.8rem; font-weight:550; line-height:1.5; padding:1px 8px; border-radius:var(--jh-r);
  background:var(--jh-wash); color:var(--jh-ink-2); border:1px solid var(--jh-line);}
.jh-chip.ok, .jh-tag.ok {background:var(--jh-ok-wash); color:var(--jh-ok); border-color:#c5dfcd;}
.jh-chip.miss, .jh-tag.miss {background:var(--jh-bad-wash); color:var(--jh-bad); border-color:#efc9c9;}
.jh-chip.ok::before, .jh-tag.ok::before {content:"\2713\00a0";}
.jh-chip.miss::before, .jh-tag.miss::before {content:"\2715\00a0";}

/* job card */
.jh-card {font-size:.94rem; color:var(--jh-ink-2);}
.jh-card-head {display:flex; gap:14px; align-items:flex-start;}
.jh-card-main {min-width:0; flex:1;}
.jh-title {font-size:1.08rem; font-weight:650; color:var(--jh-ink); line-height:1.3; overflow-wrap:anywhere;}
.jh-company {color:var(--jh-ink-2); font-weight:550; margin-top:1px; overflow-wrap:anywhere;}
.jh-avatar {flex:none; width:40px; height:40px; border-radius:var(--jh-r); display:flex; align-items:center;
  justify-content:center; font-weight:700; font-size:1rem; border:1px solid var(--jh-line);}
.jh-score {flex:none; width:104px; text-align:right;}
.jh-score b {display:block; font-size:1.5rem; font-weight:700; line-height:1; font-variant-numeric:tabular-nums;
  color:var(--jh-muted);}
.jh-score small {display:block; font-size:.76rem; font-weight:600; color:var(--jh-muted); margin:4px 0 5px 0;}
.jh-score i {display:block; height:4px; background:var(--jh-wash); overflow:hidden;}
.jh-score i > u {display:block; height:100%; background:var(--jh-line-2);}
.jh-score.hi b, .jh-score.hi small {color:var(--jh-ok);} .jh-score.hi i > u {background:var(--jh-ok);}
.jh-score.mid b, .jh-score.mid small {color:var(--jh-warn);} .jh-score.mid i > u {background:var(--jh-warn);}
.jh-meta {display:flex; flex-wrap:wrap; gap:6px 18px; margin:12px 0 8px 0;}
.jh-meta span {display:inline-flex; align-items:center; gap:6px; max-width:100%;}
.jh-meta svg {flex:none; width:15px; height:15px; color:var(--jh-muted);}
.jh-meta .ok, .jh-meta .ok svg {color:var(--jh-ok);} .jh-meta .bad, .jh-meta .bad svg {color:var(--jh-bad);}
.jh-snippet {color:var(--jh-muted); margin:4px 0 10px 0; max-width:78ch; display:-webkit-box;
  -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;}
.jh-near {display:flex; gap:8px; align-items:center; margin:2px 0 10px 0; padding:6px 10px;
  border-left:3px solid var(--jh-ok); background:var(--jh-ok-wash); color:#14532d; font-size:.87rem; font-weight:550;}
.jh-near svg {flex:none; width:15px; height:15px;}
.jh-foot {display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between;
  color:var(--jh-muted); font-size:.83rem;}
.jh-foot a {color:var(--jh-accent-ink); font-weight:600; text-decoration:underline; text-underline-offset:3px;}
.jh-badge {font-size:.74rem; font-weight:650; padding:1px 8px; border-radius:var(--jh-r); background:var(--jh-wash);
  color:var(--jh-ink-2); border:1px solid var(--jh-line); text-transform:capitalize;}
.jh-badge.saved {background:var(--jh-warn-wash); color:var(--jh-warn); border-color:#ecd5b4;}
.jh-badge.applied {background:var(--jh-ok-wash); color:var(--jh-ok); border-color:#c5dfcd;}
.jh-badge.rejected {background:var(--jh-bad-wash); color:var(--jh-bad); border-color:#efc9c9;}
@media (max-width:560px) {
  .jh-avatar {display:none;}
  .jh-score {width:84px;}
}

/* score breakdown */
.jh-bars {display:grid; grid-template-columns:max-content 1fr max-content; gap:9px 12px; align-items:center;
  margin:2px 0 14px 0; font-size:.88rem;}
.jh-bars label {color:var(--jh-ink-2); font-weight:550;}
.jh-bars .track {height:6px; background:var(--jh-wash); overflow:hidden;}
.jh-bars .fill {height:100%; background:var(--jh-accent);}
.jh-bars .fill.low {background:var(--jh-line-2);} .jh-bars .fill.mid {background:var(--jh-warn);}
.jh-bars b {font-variant-numeric:tabular-nums; font-weight:650; color:var(--jh-ink); min-width:2ch; text-align:right;}
.jh-bars small {grid-column:1 / -1; color:var(--jh-muted); margin-top:-4px;}
.jh-counts {grid-template-columns:minmax(0,max-content) minmax(40px,1fr) max-content; font-size:.84rem;}
.jh-counts small {margin-top:2px;}
[data-testid="stSidebar"] h2 {font-size:1rem !important; font-weight:650 !important;}

/* full job description */
.jh-jd {max-width:72ch; max-height:440px; overflow:auto; padding:4px 14px 4px 0; line-height:1.6; font-size:.94rem;
  color:var(--jh-ink-2);}
.jh-jd h6 {font-size:.95rem; font-weight:700; color:var(--jh-ink); margin:14px 0 4px; padding:0;}
.jh-jd p {margin:0 0 10px; overflow-wrap:anywhere;} .jh-jd ul {margin:0 0 10px; padding-left:1.2rem;}
.jh-jd li {margin:2px 0;}
.jh-jd :first-child {margin-top:0;}

/* summary strip, headline numbers, empty states */
.jh-strip {display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:6px 0 14px 0; color:var(--jh-muted);
  font-size:.87rem;}
.jh-strip b {color:var(--jh-ink); font-variant-numeric:tabular-nums;}
.jh-strip .pill {padding:1px 8px; border-radius:var(--jh-r); background:var(--jh-accent-wash);
  color:var(--jh-accent-ink); font-weight:600;}
.jh-empty {text-align:center; padding:32px 20px 34px; border:1px dashed var(--jh-line-2);
  border-radius:var(--jh-r); background:var(--jh-surface); margin:10px 0 18px;}
.jh-empty svg {width:28px; height:28px; color:var(--jh-muted); margin-bottom:8px;}
.jh-empty h5 {margin:0 0 4px; padding:0; font-size:1.02rem; font-weight:650; color:var(--jh-ink);}
.jh-empty p {margin:0 auto; max-width:48ch; color:var(--jh-muted); font-size:.92rem;}
.jh-stat {display:flex; gap:10px 32px; flex-wrap:wrap; margin:4px 0 6px;}
.jh-stat div b {display:block; font-size:1.45rem; font-weight:700; color:var(--jh-ink);
  font-variant-numeric:tabular-nums; line-height:1.15; overflow-wrap:anywhere;}
.jh-stat div span {color:var(--jh-muted); font-size:.82rem;}
.jh-next {margin:6px 0 14px; padding:8px 12px; border-left:3px solid var(--jh-accent); background:var(--jh-accent-wash);
  color:var(--jh-ink); font-size:.93rem;}
.jh-dot {display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:8px; background:var(--jh-line-2);}
.jh-dot.on {background:var(--jh-ok);}
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
        missing = (getattr(exc, "name", None) or "").split(".")[0] if isinstance(exc, ModuleNotFoundError) else ""
        if missing and missing != module.split(".")[0]:
            # A third-party library is missing: almost always the app was started with a Python
            # that is not the project's virtual environment.
            raise FeatureUnavailable(
                f"the `{missing}` library is not installed in the Python running this app "
                f"(`{sys.executable}`). Stop the app and start it with the project's environment: "
                "`.venv\\Scripts\\python -m streamlit run ui/app.py` on Windows or "
                "`.venv/bin/python -m streamlit run ui/app.py` elsewhere.") from exc
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


# Inline icons (16px grid, 1.5 stroke) so the app needs no icon font or network.
_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' \
       'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{}</svg>'
ICONS = {
    "briefcase": _SVG.format('<rect x="2" y="5" width="12" height="8.5" rx="1.8"/>'
                             '<path d="M6 5V3.8A1.3 1.3 0 0 1 7.3 2.5h1.4A1.3 1.3 0 0 1 10 3.8V5M2 9h12"/>'),
    "pin": _SVG.format('<path d="M8 14.2s4.3-3.9 4.3-7.4a4.3 4.3 0 0 0-8.6 0c0 3.5 4.3 7.4 4.3 7.4Z"/>'
                       '<circle cx="8" cy="6.7" r="1.5"/>'),
    "check": _SVG.format('<circle cx="8" cy="8" r="6"/><path d="m5.4 8.2 1.8 1.8 3.5-3.7"/>'),
    "alert": _SVG.format('<path d="M8 2.4 14 13H2L8 2.4Z"/><path d="M8 6.6v3M8 11.3v.1"/>'),
    "dot": _SVG.format('<circle cx="8" cy="8" r="6"/><path d="M8 5.2v3.1M8 10.7v.1"/>'),
    "spark": _SVG.format('<path d="M8 2v3M8 11v3M2 8h3M11 8h3M4.2 4.2l1.6 1.6M10.2 10.2l1.6 1.6'
                         'M11.8 4.2l-1.6 1.6M5.8 10.2l-1.6 1.6"/>'),
    "file": _SVG.format('<path d="M4 2.5h5l3 3v8H4v-11Z"/><path d="M9 2.5v3h3M6 9h4M6 11.2h4"/>'),
    "search": _SVG.format('<circle cx="7.2" cy="7.2" r="4.2"/><path d="m10.4 10.4 3.1 3.1"/>'),
    "filter": _SVG.format('<path d="M2.5 3.5h11L9.3 8.6v3.6l-2.6 1.3V8.6L2.5 3.5Z"/>'),
}


def time_ago(value: Any, now: Optional[datetime] = None) -> str:
    """'Today', '2 days ago', '3 weeks ago' for a posting date; '' when unknown."""
    if not isinstance(value, datetime):
        return ""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    days = (now - value.replace(tzinfo=None)).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "1 day ago"
    if days < 14:
        return f"{days} days ago"
    if days < 60:
        return f"{days // 7} weeks ago"
    return f"{days // 30} months ago"


def snippet(text: Any, limit: int = 220) -> str:
    """First sentences of a posting on one line, cut at a word boundary."""
    s = " ".join(str(text or "").split())
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0] + "..."


def score_class(value: float) -> str:
    return "hi" if value >= 50 else "mid" if value >= 35 else "low"


SCORE_LABELS = {"hi": "Strong match", "mid": "Possible match", "low": "Weak match"}


def score_label(value: Any) -> str:
    """The score band in words, so the number never has to be read from its color."""
    try:
        return SCORE_LABELS[score_class(float(value))]
    except (TypeError, ValueError):
        return "Not scored"


def source_name(key: Any) -> str:
    return SOURCES.get(str(key or ""), str(key or "")).split(" (")[0]


def status_name(status: Any) -> str:
    return STATUS_LABELS.get(str(status), str(status).capitalize())


_BULLET = re.compile(r"^(?:[-*•·‣▪●]|\d{1,2}[.)])\s+(.*)")


# A short line ending in one of these is a sentence cut short, not a heading.
_CONNECTORS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or", "our",
               "the", "to", "with", "your"}


def description_html(text: Any, limit: int = 12000) -> str:
    """A posting's plain text as readable HTML: paragraphs, bullet lists and short headings.
    Every line is escaped."""
    out: list = []
    bullets: list = []
    after_break = True  # at the start, or straight after a blank line

    def flush() -> None:
        if bullets:
            out.append("<ul>" + "".join(f"<li>{html.escape(b)}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for raw in str(text or "")[:limit].splitlines():
        line = " ".join(raw.split())
        if not line:
            flush()
            after_break = True
            continue
        bullet = _BULLET.match(line)
        if bullet:
            bullets.append(bullet.group(1))
            after_break = False
            continue
        flush()
        short = len(line) <= 60 and "://" not in line and "@" not in line and "|" not in line
        if short and (line.endswith(":") or (after_break and len(line.split()) <= 6 and line[0].isupper() and line[-1].isalnum()
                                              and line.split()[-1].lower() not in _CONNECTORS)):
            out.append(f"<h6>{html.escape(line.rstrip(':'))}</h6>")
        elif not after_break and out and out[-1].endswith("</p>") and out[-1][-5] not in ".!?:":
            # A sentence the source broke across lines (often around a link): keep it together.
            out[-1] = f"{out[-1][:-4]} {html.escape(line)}</p>"
        else:
            out.append(f"<p>{html.escape(line)}</p>")
        after_break = False
    flush()
    return f'<div class="jh-jd" tabindex="0" role="region" aria-label="Full job description">{"".join(out)}</div>'


def job_card_html(job: dict, *, score: Any = None, years: Any = None, fit: str = "", fit_ok: Optional[bool] = None,
                  matched: Iterable[str] = (), missing: Iterable[str] = (), tags: Iterable[str] = (),
                  near: str = "", status: str = "", link: bool = False) -> str:
    """One job as a card (HTML). Every value from a posting is escaped."""
    e = html.escape
    title = str(g(job, "title", default="Untitled role"))
    company = str(g(job, "company", default="Unknown company"))
    source = source_name(g(job, "source", default=""))
    initial = next((ch for ch in company if ch.isalnum()), "?").upper()
    hue = sum(map(ord, company)) * 37 % 360  # a stable, quiet tint per company

    badge = ""
    if score is not None:
        try:
            value = max(0.0, min(100.0, float(score)))
            label = score_label(value)
            badge = (f'<div class="jh-score {score_class(value)}" role="img" '
                     f'aria-label="Match score {value:.0f} out of 100, {label.lower()}" '
                     f'title="Match score out of 100"><b>{value:.0f}</b><small>{label}</small>'
                     f'<i><u style="width:{value:.0f}%"></u></i></div>')
        except (TypeError, ValueError):
            badge = ""
    meta = []
    if years is not None:
        meta.append(f'<span title="Experience asked">{ICONS["briefcase"]}{e(str(years))}+ yrs</span>')
    if g(job, "location"):
        meta.append(f'<span title="Location">{ICONS["pin"]}{e(str(job["location"])[:60])}</span>')
    if fit:
        cls, icon = ("", "dot") if fit_ok is None else (("ok", "check") if fit_ok else ("bad", "alert"))
        meta.append(f'<span class="{cls}">{ICONS[icon]}{e(fit[:70])}</span>')
    chips = "".join(f'<span class="jh-tag ok" title="On your resume">{e(str(t))}</span>' for t in list(matched)[:6])
    chips += "".join(f'<span class="jh-tag miss" title="Not on your resume">{e(str(t))}</span>'
                     for t in list(missing)[:6])
    chips += "".join(f'<span class="jh-tag">{e(str(t))}</span>' for t in list(tags)[:7])
    foot_left = " &middot; ".join(x for x in (e(time_ago(g(job, "posted_date"))), e(source)) if x)
    foot_right = ""
    if status and status != "new":
        foot_right = f'<span class="jh-badge {e(status)}">{e(status_name(status))}</span>'
    url = str(g(job, "url", default="") or "")
    if link and url.startswith(("https://", "http://")):
        foot_right += f' <a href="{e(url, quote=True)}" target="_blank" rel="noopener noreferrer">Open posting &#8599;</a>'
    text = snippet(g(job, "description", default=""))
    return (
        '<article class="jh-card">'
        '<div class="jh-card-head">'
        f'<div class="jh-avatar" style="background:hsl({hue} 38% 93%);color:hsl({hue} 42% 30%)">{e(initial)}</div>'
        f'<div class="jh-card-main"><div class="jh-title">{e(title)}</div>'
        f'<div class="jh-company">{e(company)}</div></div>{badge}</div>'
        + (f'<div class="jh-meta">{"".join(meta)}</div>' if meta else "")
        + (f'<div class="jh-snippet">{e(text)}</div>' if text else "")
        + (f'<div class="jh-near">{ICONS["spark"]}<span>{e(near)}</span></div>' if near else "")
        + (f'<div class="jh-tags">{chips}</div>' if chips else "")
        + f'<div class="jh-foot"><span>{foot_left}</span><span>{foot_right}</span></div>'
        "</article>"
    )


def score_bars_html(parts: Iterable[tuple], note: str = "") -> str:
    """Labelled horizontal bars for a score breakdown: ``[(label, value 0-100 or None), ...]``."""
    rows = []
    for label, value in parts:
        try:
            v = max(0.0, min(100.0, float(value)))
            rows.append(f'<label>{html.escape(str(label))}</label><div class="track">'
                        f'<div class="fill {score_class(v) if score_class(v) != "hi" else ""}" '
                        f'style="width:{v:.0f}%"></div></div><b>{v:.0f}</b>')
        except (TypeError, ValueError):
            rows.append(f'<label>{html.escape(str(label))}</label><div class="track"></div><b>-</b>')
    tail = f"<small>{html.escape(note)}</small>" if note else ""
    return f'<div class="jh-bars">{"".join(rows)}{tail}</div>'


def count_bars_html(rows: Iterable[tuple], note: str = "") -> str:
    """Horizontal bars for counts, ``[(label, count), ...]``, scaled to the largest. The count is
    written beside each bar, so the chart reads without hover or color."""
    rows = [(str(label), int(count)) for label, count in rows]
    top = max([count for _, count in rows] + [1])
    body = "".join(f'<label>{html.escape(label)}</label><div class="track"><div class="fill" '
                   f'style="width:{100 * count / top:.0f}%"></div></div><b>{count}</b>' for label, count in rows)
    tail = f"<small>{html.escape(note)}</small>" if note else ""
    return f'<div class="jh-bars jh-counts">{body}{tail}</div>'


def empty_state(icon: str, title: str, hint: str) -> None:
    """A composed empty state instead of a bare info box."""
    st.markdown(f'<div class="jh-empty">{ICONS.get(icon, ICONS["dot"])}<h5>{html.escape(title)}</h5>'
                f'<p>{html.escape(hint)}</p></div>', unsafe_allow_html=True)


def strip(parts: Iterable[str]) -> None:
    """One-line summary strip; ``parts`` are trusted HTML fragments built by the caller."""
    st.markdown(f'<div class="jh-strip">{"".join(parts)}</div>', unsafe_allow_html=True)


def panel_title(text: str, marker: str = "") -> None:
    st.markdown(f'<p class="jh-panel-title {html.escape(marker)}">{html.escape(text)}</p>', unsafe_allow_html=True)


def match_label(m: dict) -> str:
    company = g(m, "company", default="Unknown company")
    title = g(m, "title", default="Untitled role")
    score = fmt_score(g(m, "confidence_score", "total"))
    status = g(m, "status", default="new")
    prefix = f"{status_name(status)}: " if status in TRACKED_STATUSES else ""
    return f"{prefix}{title} at {company}  (score {score})"


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
    st.markdown(f'<span class="jh-dot {"on" if ok else ""}"></span>**{label}:** {ok_text if ok else bad_text}',
                unsafe_allow_html=True)


def db_location(url: str) -> str:
    """Human display of the database location without any credentials."""
    if url.startswith("sqlite"):
        return url.split("///", 1)[-1] or ":memory:"
    # Strip user:password@ from server URLs.
    scheme, _, rest = url.partition("://")
    return f"{scheme}://{rest.rsplit('@', 1)[-1]}"
