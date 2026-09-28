"""Persist generated documents to docs_dir (traversal-safe) and record them in the DB."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from config import get_settings
from security.sanitize import safe_filename, safe_join, sanitize_text

MAX_DOC_CHARS = 50_000


def save_generated_doc(match_id, doc_type: str, content: str) -> str:
    """Write ``content`` to ``<docs_dir>/match<id>_<type>_<timestamp>.md``, store it via
    ``db.repository.save_document`` and return the file path."""
    from db.repository import save_document  # imported lazily (db owned by another module)

    try:
        match_int = int(match_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("match_id must be an integer") from exc
    kind = re.sub(r"[^a-z0-9_]+", "_", str(doc_type or "document").lower()).strip("_") or "document"
    text = sanitize_text(content or "", max_len=MAX_DOC_CHARS)

    base = Path(get_settings().docs_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = safe_join(base, safe_filename(f"match{match_int}_{kind}_{stamp}.md"))
    path.write_text(text, encoding="utf-8")
    try:
        save_document(match_int, kind, text, str(path))
    except Exception:
        path.unlink(missing_ok=True)  # don't leave orphan files when the DB write fails
        raise
    logger.info("Saved {} for match {} to {}", kind, match_int, path.name)
    return str(path)
