"""Shared helpers for the API: settings, lazy imports, JSON-safe values.

Nothing here reaches past the repo root. The server binds to 127.0.0.1 only
(see ``api/server.py``), so the resume and the database never leave the laptop.
"""
from __future__ import annotations

import importlib
import sys
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger as log  # noqa: E402


class FeatureUnavailable(RuntimeError):
    """An optional project module or library is not installed."""


def load(module: str, attr: Optional[str] = None) -> Any:
    """Import ``module`` (and optionally return ``attr``), raising FeatureUnavailable.

    Mirrors ``ui.components.load`` so both front ends degrade the same way when a
    heavy dependency is missing.
    """
    try:
        mod = importlib.import_module(module)
        return getattr(mod, attr) if attr else mod
    except Exception as exc:
        log.warning("Could not load {}{}: {}", module, f".{attr}" if attr else "", exc)
        missing = (getattr(exc, "name", None) or "").split(".")[0] if isinstance(exc, ModuleNotFoundError) else ""
        if missing and missing != module.split(".")[0]:
            raise FeatureUnavailable(
                f"the `{missing}` library is not installed in the Python running this server "
                f"(`{sys.executable}`). Stop it and start it with the project's environment: "
                "`.venv/bin/python -m api` (macOS) or `.venv\\Scripts\\python -m api` (Windows).") from exc
        raise FeatureUnavailable(f"`{module}` is not available yet ({type(exc).__name__}).") from exc


def repo():
    return load("db.repository")


@lru_cache(maxsize=1)
def settings():
    """The frozen Settings dataclass from config.py."""
    return load("config", "get_settings")()


def setting(name: str, default: Any = None) -> Any:
    return getattr(settings(), name, default)


def jsonable(value: Any) -> Any:
    """datetime/date to ISO strings, recursively, so a dict can be returned as JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def as_list(value: Any) -> list:
    """A list from a value that may be a list, a JSON string or a single item."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                import json

                parsed = json.loads(text)
                return parsed if isinstance(parsed, list) else [parsed]
            except ValueError:
                return [text] if text else []
        return [text] if text else []
    return [value]


def g(d: Optional[dict], *keys: str, default: Any = None) -> Any:
    """First present key of ``d``, so match dicts and job dicts can be read alike."""
    if not isinstance(d, dict):
        return default
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def score_of(m: dict) -> float:
    try:
        return float(g(m, "confidence_score", "total", default=0) or 0)
    except (TypeError, ValueError):
        return 0.0


def db_location(url: str) -> str:
    """Where the database lives, without any credentials (same output as the Streamlit app)."""
    text = str(url or "")
    if text.startswith("sqlite"):
        return text.split("///", 1)[-1] or ":memory:"
    scheme, _, rest = text.partition("://")
    return f"{scheme}://{rest.rsplit('@', 1)[-1]}"


def llm_error(exc: Exception, action: str) -> str:
    """The message to show when the model could not run.

    ``generator.llm`` raises LLMUnavailable with a line that already says what failed
    and how to fix it, so that line is passed through as it is.
    """
    try:
        unavailable = load("generator.llm", "LLMUnavailable")
        is_llm = isinstance(exc, unavailable)
    except FeatureUnavailable:
        is_llm = type(exc).__name__ == "LLMUnavailable"
    if is_llm:
        return str(exc)
    log.exception("could not {}", action)
    return f"The language model could not {action} ({type(exc).__name__}). Details are in the log."


def clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default
