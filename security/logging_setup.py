"""Loguru configuration with secret redaction applied to every log record."""
from __future__ import annotations

import os
import re
import sys
from typing import Any

from loguru import logger

REDACTED = "[REDACTED]"
_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google API keys
    re.compile(r"(?i)\b((?:api[_-]?)?key|token|secret|password|authorization)\b(\s*[=:]\s*)([^\s&,;\"']+)"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
]


def redact(text: str) -> str:
    """Remove API keys and ``key=...``-style secrets from ``text``."""
    if not text:
        return text
    secret = (os.getenv("GEMINI_API_KEY") or "").strip()
    if len(secret) >= 4:
        text = text.replace(secret, REDACTED)
    text = _PATTERNS[0].sub(REDACTED, text)
    text = _PATTERNS[2].sub(lambda m: f"{m.group(1)}{REDACTED}", text)  # bearer before key=value
    text = _PATTERNS[1].sub(
        lambda m: m.group(0) if m.group(3) == REDACTED else f"{m.group(1)}{m.group(2)}{REDACTED}", text
    )
    return text


def _redact_record(record: dict[str, Any]) -> bool:
    """Loguru filter: scrub the message and any exception text in place; always keep the record."""
    record["message"] = redact(record["message"])
    for key, value in list(record["extra"].items()):
        if isinstance(value, str):
            record["extra"][key] = redact(value)
    return True


def _format(record: dict[str, Any]) -> str:
    fmt = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {name}:{line} - {message}\n"
    if record["exception"] is not None:
        # Render the traceback ourselves so it passes through redaction too.
        import traceback

        exc = record["exception"]
        tb = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))
        record["extra"]["_redacted_exc"] = redact(tb)
        fmt += "{extra[_redacted_exc]}"
    return fmt


def setup_logging(level: str | None = None, sink: Any = None) -> None:
    """(Re)configure loguru: one redacting sink (stderr by default) at ``level`` (env LOG_LEVEL, default INFO)."""
    level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    logger.remove()
    logger.add(
        sink if sink is not None else sys.stderr,
        level=level,
        filter=_redact_record,
        format=_format,
        colorize=False if sink is not None else None,
        backtrace=False,
        diagnose=False,  # diagnose=True would print local variables (possibly secrets)
    )
