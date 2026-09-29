"""Application settings loaded from environment variables and an optional ``.env`` file.

Every setting has a safe default so the app runs out of the box with no configuration.
Real environment variables always take precedence over values in ``.env``.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, "")))
    except ValueError:
        return default


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, "")))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    database_url: str = "sqlite:///jobhunt.db"
    use_ollama: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    gemini_api_key: Optional[str] = field(default=None, repr=False)  # never printed
    gemini_model: str = "gemini-3.8-flash"
    docs_dir: Path = field(default_factory=lambda: Path("~/jobhunt_docs").expanduser())
    scrape_delay_seconds: float = 3.0
    max_jobs_per_session: int = 50
    upload_max_bytes: int = 2_000_000
    allow_remote_llm: bool = False


def get_settings(env_file: Optional[str | os.PathLike[str]] = None) -> Settings:
    """Load settings from the environment (after reading ``.env`` without overriding real env vars)."""
    load_dotenv(dotenv_path=env_file, override=False)
    key = (os.getenv("GEMINI_API_KEY") or "").strip()
    return Settings(
        database_url=_env_str("DATABASE_URL", Settings.database_url),
        use_ollama=_env_bool("USE_OLLAMA", True),
        ollama_base_url=_env_str("OLLAMA_BASE_URL", Settings.ollama_base_url),
        ollama_model=_env_str("OLLAMA_MODEL", Settings.ollama_model),
        gemini_api_key=key or None,
        gemini_model=_env_str("GEMINI_MODEL", Settings.gemini_model),
        docs_dir=Path(_env_str("DOCS_DIR", "~/jobhunt_docs")).expanduser(),
        scrape_delay_seconds=_env_float("SCRAPE_DELAY_SECONDS", 3.0),
        max_jobs_per_session=_env_int("MAX_JOBS_PER_SESSION", 50),
        upload_max_bytes=_env_int("UPLOAD_MAX_BYTES", 2_000_000),
        allow_remote_llm=_env_bool("ALLOW_REMOTE_LLM", False),
    )
