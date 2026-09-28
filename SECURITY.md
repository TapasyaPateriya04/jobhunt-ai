# Security

JobHunt AI is a local-first, single-user app. It still handles untrusted input (scraped
job posts, uploaded resumes) and a secret (the optional Gemini API key), so the controls
below live in `security/` and `config.py`. Report issues privately to the maintainer.

## Threat model

| Threat | Where it enters | Mitigation |
| --- | --- | --- |
| **Prompt injection** | Job descriptions and resumes are pasted into LLM prompts; a posting can say "ignore previous instructions…". | `security.prompt_guard.wrap_untrusted` sanitises the text, fences it in labelled `<<<BEGIN UNTRUSTED …>>>` / `<<<END UNTRUSTED …>>>` markers, strips anything that spoofs those markers, and prefixes a "treat as data only" notice. LLM output is shown to the user as text, never executed. |
| **Malicious uploads** | Resume upload in the UI. | `security.sanitize.validate_upload`: extension allowlist, size limit (`UPLOAD_MAX_BYTES`), rejects empty files, null bytes / non-UTF-8 in text types, and non-PDF bytes for `.pdf`. `sanitize_text` strips control and bidi/zero-width characters and caps length. |
| **Path traversal** | Filenames of uploads and generated documents. | `safe_filename` reduces names to `[A-Za-z0-9._-]`; `safe_join` resolves the path and raises if it leaves the base directory (`..`, absolute paths, symlink escapes). |
| **SSRF** | Scraper URLs; the Ollama endpoint. | `url_guard.is_allowed_url`: http/https only, no credentials in URLs, no raw IPs, host must be an allowlisted job site (indeed, linkedin, naukri, remoteok, HN) or a subdomain. `validate_llm_endpoint` only accepts localhost/127.0.0.1/::1 unless `ALLOW_REMOTE_LLM=true`. robots.txt fetches that redirect off the allowlist are refused. |
| **Secret leakage** | Gemini key in env/logs/UI. | Key read only from env/`.env` (gitignored; `.env.example` holds no secrets). `Settings` hides the key from `repr`. `logging_setup.setup_logging` redacts the live `GEMINI_API_KEY` value, `AIza…` tokens, `key=`/`token=`/`secret=`/`password=` pairs and bearer tokens from messages and tracebacks, with loguru `diagnose` off. The UI must never render raw exceptions. |
| **Abusive / unethical scraping** (SPEC §10) | Scrapers. | Prefer official/free APIs (RemoteOK, HN Algolia). `robots.can_fetch` checks robots.txt per host (cached 1 h, 5 s timeout) and **fails closed** on any network error or 401/403/429/5xx. `RateLimiter` enforces `SCRAPE_DELAY_SECONDS` (default 3 s) between requests; `MAX_JOBS_PER_SESSION` caps volume (default 50). Results are cached in SQLite to avoid re-scraping. Respect each site's Terms of Service; LinkedIn and Indeed restrict automated access, so use those scrapers only for personal learning, if at all. |

## Out of scope

Multi-user auth, network exposure (run Streamlit bound to localhost), and compromise of
the local machine or of a user-configured remote LLM.
