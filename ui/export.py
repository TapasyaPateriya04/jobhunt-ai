"""Turn a drafted document (plain text with light Markdown) into Word or PDF bytes.

Presentation-only: nothing here touches the database or the language model. The two
libraries are imported lazily so the app still runs, with the buttons disabled, when
they are not installed.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Iterator, Tuple

MAX_CHARS = 50_000
_BULLET = re.compile(r"^\s*[-*\u2022]\s+(.*)")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)")
_MARKS = re.compile(r"(\*\*|__|`)")
# Windows, Linux and macOS locations of a font that covers more than Latin-1.
_FONTS = (
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
)
_LATIN = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
          "\u2022": "-", "\u2026": "...", "\u00a0": " "}


class ExportUnavailable(RuntimeError):
    """The library for this format is not installed."""


def _blocks(text: str) -> Iterator[Tuple[str, str]]:
    """Yield ("heading" | "bullet" | "para" | "blank", text) for each line of the draft."""
    for raw in str(text or "")[:MAX_CHARS].splitlines():
        line = raw.rstrip()
        if not line.strip():
            yield "blank", ""
            continue
        heading, bullet = _HEADING.match(line), _BULLET.match(line)
        if heading:
            yield "heading", _MARKS.sub("", heading.group(1)).strip()
        elif bullet:
            yield "bullet", _MARKS.sub("", bullet.group(1)).strip()
        else:
            yield "para", _MARKS.sub("", line).strip()


def to_docx(text: str, title: str = "") -> bytes:
    try:
        from docx import Document
        from docx.shared import Pt
    except Exception as exc:
        raise ExportUnavailable("Word export needs python-docx. Run: pip install python-docx") from exc

    doc = Document()
    doc.core_properties.title = str(title or "")[:200]
    doc.styles["Normal"].font.size = Pt(11)
    for kind, line in _blocks(text):
        if kind == "heading":
            doc.add_heading(line, level=2)
        elif kind == "bullet":
            doc.add_paragraph(line, style="List Bullet")
        elif kind == "para":
            doc.add_paragraph(line)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def to_pdf(text: str, title: str = "") -> bytes:
    try:
        from fpdf import FPDF
    except Exception as exc:
        raise ExportUnavailable("PDF export needs fpdf2. Run: pip install fpdf2") from exc

    pdf = FPDF(format="A4")
    pdf.set_margins(22, 20, 22)
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_title(str(title or "")[:200])
    family, clean = "Helvetica", _latin1
    for regular, bold in _FONTS:
        if Path(regular).is_file() and Path(bold).is_file():
            try:
                pdf.add_font("Body", "", regular)
                pdf.add_font("Body", "B", bold)
                family, clean = "Body", (lambda s: s)
                break
            except Exception:
                continue
    pdf.add_page()
    for kind, line in _blocks(text):
        if kind == "blank":
            pdf.ln(3)
            continue
        pdf.set_font(family, "B" if kind == "heading" else "", 12 if kind == "heading" else 11)
        body = clean(("-  " if kind == "bullet" else "") + line)
        pdf.multi_cell(0, 6, body, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    return bytes(pdf.output())


def _latin1(text: str) -> str:
    """The built-in PDF fonts only cover Latin-1: swap common typographic characters, drop the rest."""
    for fancy, plain in _LATIN.items():
        text = text.replace(fancy, plain)
    return text.encode("latin-1", "replace").decode("latin-1")
