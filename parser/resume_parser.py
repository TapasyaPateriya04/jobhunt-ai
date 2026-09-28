"""Resume parsing: LaTeX / plain text / Markdown (and PDF when pypdf is installed).

Public API (see docs/CONTRACTS.md):
    parse_resume_text(text) -> dict
    parse_latex_resume(path) -> dict
    parse_resume_bytes(filename, data) -> dict

Each returns ``{"raw_text", "skills", "experience", "education", "summary"}`` plus a few
extra helpful keys (``projects``, ``sections``, ``total_experience_years``).
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

from loguru import logger

from parser.skills_vocab import canonicalize, find_skills

MAX_TEXT_CHARS = 100_000

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary", "professional summary", "profile", "professional profile", "objective",
        "career objective", "about", "about me", "overview", "career summary",
    ),
    "skills": (
        "skills", "technical skills", "core skills", "key skills", "core competencies",
        "competencies", "technologies", "tech stack", "technical expertise", "tools",
        "skills and tools", "skills & tools", "tools and technologies", "tools & technologies",
        "programming skills", "skills summary", "technical proficiencies",
    ),
    "experience": (
        "experience", "work experience", "professional experience", "employment",
        "employment history", "work history", "relevant experience", "industry experience",
        "internships", "internship experience", "career history",
    ),
    "education": (
        "education", "academic background", "academics", "education and training",
        "academic qualifications", "qualifications", "educational background",
    ),
    "projects": (
        "projects", "personal projects", "key projects", "academic projects",
        "selected projects", "side projects", "project experience",
    ),
    # Recognized so they terminate the previous section.
    "certifications": ("certifications", "certificates", "licenses and certifications"),
    "achievements": ("achievements", "awards", "honors", "honors and awards", "accomplishments"),
    "publications": ("publications", "research"),
    "other": ("interests", "hobbies", "languages", "volunteering", "volunteer experience",
              "extracurricular activities", "activities", "leadership", "references",
              "positions of responsibility", "contact"),
}
_HEADING_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}

_LATEX_SECTION_MACROS = r"(?:section|cvsection|resumeSection|sectiontitle|Section|cvSection|mysection)\*?"


def _normalize_heading(line: str) -> str | None:
    s = line.strip()
    if not s or len(s) > 50:
        return None
    s = re.sub(r"^[#=*_\-\s§>]+", "", s)          # markdown / latex2text decorations
    s = re.sub(r"[#=*_\-\s:|]+$", "", s)
    s = s.replace("&", "and") if s.lower().replace("&", "and") in _HEADING_LOOKUP else s
    key = re.sub(r"\s+", " ", s).strip().lower()
    return _HEADING_LOOKUP.get(key)


def extract_sections(text: str) -> dict[str, str]:
    """Split plain text into named sections keyed by canonical section name."""
    sections: dict[str, list[str]] = {}
    current = "header"
    for line in text.splitlines():
        # A heading line, or "Skills: Python, Java" (heading with inline content).
        key = _normalize_heading(line)
        inline = ""
        if key is None and ":" in line:
            head, _, rest = line.partition(":")
            k2 = _normalize_heading(head)
            if k2 and k2 not in ("other",) and len(head.strip()) <= 30:
                key, inline = k2, rest.strip()
        if key is not None and key not in sections:
            current = key
            sections.setdefault(current, [])
            if inline:
                sections[current].append(inline)
            continue
        if key is not None:  # repeated heading: keep appending to the same section
            current = key
            if inline:
                sections[current].append(inline)
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


# ---------------------------------------------------------------------------
# LaTeX -> text
# ---------------------------------------------------------------------------
# Multi-argument macros pylatexenc understands natively; leave them alone.
_KNOWN_MULTIARG = {
    "href", "textcolor", "colorbox", "setlength", "newcommand", "renewcommand",
    "multicolumn", "definecolor", "setcounter", "addtolength", "titleformat", "frac",
    "providecommand", "newenvironment", "renewenvironment", "hypersetup", "fancyhf",
    # single-argument formatting macros; a following {group} is plain text, not an argument
    "textbf", "textit", "emph", "underline", "texttt", "textsc", "textsf", "textrm", "small",
    "large", "Large", "Huge", "huge", "footnotesize", "scriptsize", "mbox", "hbox", "fbox",
    "uline", "textmd", "textup", "section", "subsection", "item", "vspace", "hspace",
}
_BRACE_GROUP = r"\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}"
_MULTIARG_RE = re.compile(r"\\([A-Za-z]+)\*?((?:\s*" + _BRACE_GROUP + r"){2,})")
_SECTION_RE = re.compile(r"\\" + _LATEX_SECTION_MACROS + r"\s*(" + _BRACE_GROUP + ")")


def _latex_preprocess(latex: str) -> str:
    # Keep only the document body when present (drops preamble macro definitions).
    m = re.search(r"\\begin\{document\}(.*?)(\\end\{document\}|$)", latex, re.S)
    body = m.group(1) if m else latex
    # Remove comments (unescaped %).
    body = re.sub(r"(?<!\\)%.*", "", body)
    # \href{url}{text} -> text (pylatexenc 2.x crashes on some \href forms).
    body = re.sub(r"\\href\s*\{[^{}]*\}\s*(" + _BRACE_GROUP + ")", lambda mm: mm.group(1)[1:-1], body)
    body = re.sub(r"\\url\s*\{([^{}]*)\}", r"\1", body)
    # Section headings -> standalone plain-text lines.
    body = _SECTION_RE.sub(lambda mm: "\n\n" + mm.group(1)[1:-1] + "\n\n", body)

    # Custom multi-arg resume macros (\resumeSubheading{Co}{Loc}{Title}{Dates}) -> "a | b | c".
    def _join_args(mm: re.Match) -> str:
        name = mm.group(1)
        if name in _KNOWN_MULTIARG:
            return mm.group(0)
        groups = re.findall(_BRACE_GROUP, mm.group(2))
        parts = [g[1:-1].strip() for g in groups]
        parts = [p for p in parts if p]
        return "\n" + " | ".join(parts) + "\n"

    prev = None
    while prev != body:  # nested macros resolve outer-first then inner
        prev = body
        body = _MULTIARG_RE.sub(_join_args, body)
    # Line breaks and item markers
    body = re.sub(r"\\\\(\[[^\]]*\])?", "\n", body)
    body = re.sub(r"\\(?:resume)?[iI]tem\b", "\n- ", body)
    return body


def latex_to_text(latex: str) -> str:
    body = _latex_preprocess(latex)
    try:
        from pylatexenc.latex2text import LatexNodes2Text

        text = LatexNodes2Text(math_mode="text", strict_latex_spaces=False).latex_to_text(body)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("pylatexenc failed ({}); using regex LaTeX stripping", type(exc).__name__)
        text = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?", " ", body)
        text = text.replace("{", "").replace("}", "")
    return _clean_text(text)


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if not ln and out and not out[-1]:
            continue
        out.append(ln)
    return "\n".join(out).strip()[:MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# Experience extraction
# ---------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
_DATE_RE = rf"(?:{_MONTH_RE}\s*,?\s*(?:19|20)\d{{2}}|(?:0?[1-9]|1[0-2])\s*[/.\-]\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}}\s*[/.\-]\s*(?:0?[1-9]|1[0-2])(?!\d)|(?:19|20)\d{{2}})"
_PRESENT_RE = r"(?:present|current|now|today|ongoing|till\s+date|to\s+date)"
_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_RE})\s*(?:-{{1,3}}|–|—|to|until|till|→)\s*(?P<end>{_DATE_RE}|{_PRESENT_RE})",
    re.IGNORECASE,
)

_TITLE_WORDS = re.compile(
    r"\b(engineer|developer|intern|internship|manager|analyst|scientist|lead|consultant|architect|"
    r"designer|specialist|administrator|assistant|associate|director|officer|researcher|head|"
    r"founder|co-founder|programmer|devops|sre|technician|coordinator|executive|trainee|fellow|"
    r"swe|sde|cto|ceo|vp|president|instructor|teaching|tutor|member of technical staff|mts)\b",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(
    r"^(remote|hybrid|on-?site|worldwide|anywhere|[A-Z][a-zA-Z .]+,\s*[A-Z]{2}|"
    r"[A-Z][a-zA-Z .]+,\s*(India|USA|US|UK|Canada|Germany|Remote))$"
)


def _parse_date(s: str, is_end: bool = False) -> date | None:
    s = s.strip().lower().rstrip(".")
    if re.fullmatch(_PRESENT_RE, s, re.IGNORECASE):
        return date.today()
    m = re.match(r"([a-z]+)\.?\s*,?\s*(\d{4})", s)
    if m:
        mon = _MONTHS.get(m.group(1)[:4]) or _MONTHS.get(m.group(1)[:3])
        if mon:
            return date(int(m.group(2)), mon, 1)
    m = re.match(r"(\d{1,2})\s*[/.\-]\s*(\d{4})$", s)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"(\d{4})\s*[/.\-]\s*(\d{1,2})$", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"(\d{4})$", s)
    if m:
        return date(int(m.group(1)), 12 if is_end else 1, 1)
    return None


def _split_parts(line: str) -> list[str]:
    parts = re.split(r"\s*(?:\||•|·|\s[–—-]\s|\t|,\s+|\bat\b|@)\s*", line)
    return [p.strip(" ,;:-–—()[]") for p in parts if p and p.strip(" ,;:-–—()[]")]


def _pick_title_company(candidates: list[str]) -> tuple[str, str]:
    title = next((p for p in candidates if _TITLE_WORDS.search(p)), "")
    company = next(
        (p for p in candidates if p != title and not _LOCATION_RE.match(p) and len(p) <= 80), ""
    )
    return title, company


def extract_experience(text: str) -> list[dict]:
    """Extract ``{title, company, dates, start, end, years, description}`` entries."""
    if not text:
        return []
    lines = [ln.strip() for ln in text.splitlines()]
    entries: list[dict] = []
    for i, line in enumerate(lines):
        m = _RANGE_RE.search(line)
        if not m:
            continue
        start = _parse_date(m.group("start"))
        end = _parse_date(m.group("end"), is_end=True)
        if start and end and end < start:
            start, end = end, start
        rest = (line[: m.start()] + " | " + line[m.end():]).strip()
        rest = re.sub(r"^[-*•]\s*", "", rest)
        parts = _split_parts(rest)
        title, company = _pick_title_company(parts)
        # Two-line layouts: look at neighbouring non-bullet lines for the missing bit.
        neighbours = []
        for j in (i - 1, i + 1, i - 2):
            if 0 <= j < len(lines) and lines[j] and not lines[j].startswith(("-", "*", "•")) \
                    and not _RANGE_RE.search(lines[j]) and len(lines[j]) <= 100:
                neighbours.extend(_split_parts(lines[j]))
        if not title or not company:
            t2, c2 = _pick_title_company([p for p in neighbours if p not in (title, company)])
            title = title or t2
            if not company:
                company = c2 if c2 and c2 != title else ""
        years = None
        if start and end:
            years = round(max(0.0, (end - start).days / 365.25), 1)
        entries.append({
            "title": title,
            "company": company,
            "dates": m.group(0).strip(),
            "start": start.strftime("%Y-%m") if start else None,
            "end": end.strftime("%Y-%m") if end else None,
            "years": years,
            "description": "",
            "_line": i,
        })
    # Attach bullet text between consecutive entries as description.
    for idx, e in enumerate(entries):
        stop = entries[idx + 1]["_line"] if idx + 1 < len(entries) else len(lines)
        bullets = [ln.lstrip("-*• ").strip() for ln in lines[e["_line"] + 1: stop]
                   if ln.startswith(("-", "*", "•"))]
        e["description"] = "\n".join(b for b in bullets if b)[:2000]
    for e in entries:
        e.pop("_line", None)
    return entries


def total_experience_years(entries: list[dict]) -> float:
    """Sum of experience with overlapping periods merged."""
    spans = []
    for e in entries:
        try:
            s = date.fromisoformat(e["start"] + "-01")
            t = date.fromisoformat(e["end"] + "-01")
        except (TypeError, ValueError, KeyError):
            continue
        spans.append((s, t))
    spans.sort()
    total_days, cur_s, cur_e = 0, None, None
    for s, t in spans:
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total_days += (cur_e - cur_s).days
            cur_s, cur_e = s, t
        else:
            cur_e = max(cur_e, t)
    if cur_e is not None:
        total_days += (cur_e - cur_s).days
    return round(total_days / 365.25, 1)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
def _skills_section_items(skills_text: str) -> list[str]:
    """Split a skills section into short list items (catches skills not in the vocabulary)."""
    items: list[str] = []
    for line in skills_text.splitlines():
        line = re.sub(r"^[-*•\s]+", "", line)
        # "Languages: Python, Java" -> drop the category label
        if ":" in line:
            label, _, rest = line.partition(":")
            if len(label.split()) <= 4:
                line = rest
        for item in re.split(r"[,;|•·]|\s/\s|\s{2,}", line):
            item = item.strip(" ()[]-").rstrip(".")
            if 1 < len(item) <= 30 and len(item.split()) <= 3 and not re.search(r"[.!?]\s", item) \
                    and re.search(r"[A-Za-z]", item):
                items.append(item)
    return items


_spacy_nlp = None
_spacy_failed = False


def _spacy_hints(text: str) -> list[str]:
    """Optional noun-chunk hints from spaCy (only when spaCy + a model are installed)."""
    global _spacy_nlp, _spacy_failed
    if _spacy_failed or not text:
        return []
    if _spacy_nlp is None:
        try:
            import spacy  # type: ignore

            _spacy_nlp = spacy.load("en_core_web_sm")
        except Exception:
            _spacy_failed = True
            return []
    try:
        doc = _spacy_nlp(text[:5000])
        return [c.text.strip() for c in doc.noun_chunks if 1 < len(c.text.strip()) <= 30]
    except Exception:  # pragma: no cover
        return []


def extract_skills(text: str, skills_section: str = "") -> list[str]:
    """Canonical vocabulary skills (skills section first, then the rest of the text), plus
    unrecognized short items listed in the skills section."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            ordered.append(s)

    for s in find_skills(skills_section):
        add(s)
    for s in find_skills(text):
        add(s)
    extra = _skills_section_items(skills_section) + _spacy_hints(skills_section)
    for item in extra:
        canon = canonicalize(item)
        if canon:
            add(canon)
        elif not find_skills(item) and item[0].isalnum():
            add(item)
    return ordered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_resume_text(text: str) -> dict:
    text = _clean_text(text or "")
    sections = extract_sections(text)
    experience = extract_experience(sections.get("experience", ""))
    summary = sections.get("summary", "")
    if not summary:
        # Fall back to the first paragraph after the header block (name/contact lines).
        header = sections.get("header", "")
        paras = [p.strip() for p in re.split(r"\n\s*\n", header) if len(p.strip()) > 80]
        summary = paras[0] if paras else ""
    return {
        "raw_text": text,
        "skills": extract_skills(text, sections.get("skills", "")),
        "experience": experience,
        "education": sections.get("education", ""),
        "summary": summary,
        "projects": sections.get("projects", ""),
        "sections": sorted(k for k in sections if k != "header"),
        "total_experience_years": total_experience_years(experience),
    }


def parse_latex_string(latex: str) -> dict:
    return parse_resume_text(latex_to_text(latex))


def parse_latex_resume(path) -> dict:
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_latex_string(content)


def _pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise ValueError("PDF support requires the optional 'pypdf' package "
                         "(pip install pypdf), or upload a .tex/.txt/.md resume.") from exc
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _markdown_to_text(md: str) -> str:
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)                 # images
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)              # links
    md = re.sub(r"(\*\*|__|`)", "", md)                            # bold / code
    md = re.sub(r"^\s*[*+]\s+", "- ", md, flags=re.M)              # bullets
    return md


SUPPORTED_EXTENSIONS = {".tex", ".txt", ".md", ".pdf"}


def parse_resume_bytes(filename: str, data: bytes) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        return parse_resume_text(_pdf_to_text(data))
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported resume type '{ext}'. Use one of: .tex, .txt, .md, .pdf")
    text = data.decode("utf-8", errors="replace")
    if ext == ".tex":
        return parse_latex_string(text)
    if ext == ".md":
        text = _markdown_to_text(text)
    return parse_resume_text(text)
