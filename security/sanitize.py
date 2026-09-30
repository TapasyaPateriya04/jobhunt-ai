"""Input sanitisation: text cleaning, safe filenames, traversal-safe paths, upload validation."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

# C0/C1 control chars except tab, newline, carriage return; plus bidi overrides / zero-width chars.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁦-⁩﻿]")
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
TEXT_EXTENSIONS = {".txt", ".md", ".tex", ".csv", ".json"}


def sanitize_text(s: str, max_len: int = 20000) -> str:
    """Normalise unicode, drop control/invisible characters and truncate to ``max_len``."""
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    s = unicodedata.normalize("NFKC", s)
    s = _CONTROL_RE.sub("", s.replace("\r\n", "\n"))
    return s[: max(0, max_len)]


def safe_filename(name: str, max_len: int = 120) -> str:
    """Reduce ``name`` to a safe basename of ``[A-Za-z0-9._-]`` characters (never empty, never hidden)."""
    name = unicodedata.normalize("NFKC", str(name or "")).replace("\\", "/")
    name = name.rsplit("/", 1)[-1]
    name = _UNSAFE_NAME_RE.sub("_", name).strip("._-")
    name = re.sub(r"\.{2,}", ".", name)
    stem, _, _ = name.partition(".")
    if not name or stem.upper() in _WINDOWS_RESERVED:
        name = f"file_{name}" if name else "file"
    if len(name) > max_len:
        root, ext = os.path.splitext(name)
        ext = ext[:16]
        name = root[: max_len - len(ext)] + ext
    return name


def safe_join(base: Path, name: str) -> Path:
    """Join ``name`` under ``base``; raise ``ValueError`` if the result escapes ``base``."""
    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("Invalid path component")
    base_resolved = Path(base).expanduser().resolve()
    candidate = Path(name)
    if candidate.is_absolute() or candidate.drive:
        raise ValueError("Absolute paths are not allowed")
    target = (base_resolved / candidate).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError("Path traversal detected")
    if target == base_resolved:
        raise ValueError("Path must name a file inside the base directory")
    return target


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    sample = text[:8192]
    if not sample:
        return False
    bad = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\t\n\r\f")
    return bad / len(sample) > 0.01


def validate_upload(filename: str, data: bytes, allowed_ext: set[str], max_bytes: int) -> None:
    """Validate an uploaded file; raise ``ValueError`` with a user-safe message on any problem."""
    if not filename or "\x00" in filename:
        raise ValueError("Invalid file name")
    ext = os.path.splitext(filename.strip().lower())[1]
    allowed = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in allowed_ext}
    if ext not in allowed:
        raise ValueError(f"File type '{ext or 'none'}' is not allowed; use one of: {', '.join(sorted(allowed))}")
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError("Upload content must be bytes")
    if len(data) == 0:
        raise ValueError("File is empty")
    if len(data) > max_bytes:
        raise ValueError(f"File is too large ({len(data)} bytes; limit is {max_bytes} bytes)")
    if ext in TEXT_EXTENSIONS and _looks_binary(bytes(data)):
        raise ValueError("Text file contains binary data or is not valid UTF-8")
    if ext == ".pdf" and not bytes(data[:5]) == b"%PDF-":
        raise ValueError("File does not look like a PDF")
