# Code style: how code should be written

> Keep this current. When a convention changes, change it here first. Last reviewed: 2026-10-12.

## Language and layout

- Python 3.10+ (developed on 3.10 Windows and 3.11 macOS; CI runs 3.11). Package root is
  the repo root; run things from there.
- Start each module with a docstring that says what it does and why, then
  `from __future__ import annotations`.
- Type hints on public functions (`dict`, `list[str]`, `X | None`). Plain dicts cross module
  boundaries (the normalized job dict, resume dict, score dict); no SQLAlchemy objects leave
  `db/repository.py`.
- Lines up to about 110 characters. Four-space indents, double quotes.
- Names: `snake_case` functions and modules, `UPPER_CASE` constants, a leading `_` for
  helpers used only inside the module.
- No formatter or linter is enforced; match the surrounding code.

## Patterns to follow

- **Settings** come only from `config.get_settings()`; never read `os.environ` elsewhere
  (the UI's `_FallbackSettings` is the one exception). Read new optional settings with
  `getattr(settings, "name", default)` in the UI so an old settings object still works.
- **Optional or heavy imports** (spaCy, sentence-transformers, google-genai, JobSpy) go
  inside the function that uses them, and the code works without them.
- **One failure must not sink the rest**: a source, a model or a document that fails is
  logged and skipped, and the caller gets `[]`, `None` or a readable message.
- **Logging** with `loguru.logger`; log the exception type, not the message, when the
  message could hold a URL, key or personal text. No `print` outside scripts.
- **HTTP** only through `scraper/net.py` (`polite_get_json`), which applies the allowlist,
  robots.txt and rate limiting. The JobSpy source is the single documented exception.
- **Untrusted text** (postings, resumes, LLM output) goes through `security.sanitize` before
  storage and `security.prompt_guard.wrap_untrusted` before a prompt. HTML built for
  `st.markdown(..., unsafe_allow_html=True)` escapes every value with `html.escape`.
- **UI**: wrap actions in `friendly_errors("<verb phrase>")`, load modules with
  `components.load`, give widgets stable `key=`s, follow DESIGN_SYSTEM.md.
- **Database**: every read and write through `db/repository.py`; schema changes need a
  migration (see DATABASE.md).

## Comments

Explain why, not what. A short comment where a rule or number is not obvious (a weight, a
regex, a site quirk). No commented-out code.

## Commits

- One topic per commit. Subject in plain English, imperative or descriptive, under ~70
  characters (e.g. "Faster Matches tab; store each Arbeitnow job once"); a body that says
  what the user sees and why.
- Update the affected docs in the same commit (see AGENTS.md).
- Never commit `.env`, `*.db`, resumes, `uploads/` or generated documents.
- Pin dependency versions in `requirements.txt` and, if tests need them,
  `requirements-dev.txt` too; bump both together.
