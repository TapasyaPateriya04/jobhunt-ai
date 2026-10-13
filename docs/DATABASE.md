# Database: what data exists and how it relates

> Keep this current. Any change to `db/database.py` models ships with an Alembic migration in
> `db/migrations/versions/` and an update to this file in the same commit;
> `tests/test_docs.py` fails when a table or column is missing here. Last reviewed: 2026-10-12.

## Engine

SQLite file `jobhunt.db` in the project folder by default (`DATABASE_URL`). SQLAlchemy 2.0,
foreign keys switched on for SQLite. Timestamps are stored as naive UTC (`db.database.utcnow`).
The file is gitignored and is personal data: it never leaves the machine except through the
user's own backups.

## Diagram

```
resumes 1 ──< matches >── 1 jobs
                 │
                 1
                 │
                 ^
             documents
```

A match is one resume scored against one job (unique per pair). Deleting a resume or a job
deletes its matches, and deleting a match deletes its documents (`ON DELETE CASCADE`).

## Tables

### resumes

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | |
| `file_path` | text | Original filename |
| `raw_text` | text | Parsed text; the same text reuses the row |
| `skills_json` | text | JSON list of skills found in the file |
| `extra_skills_json` | text | JSON list of skills the user typed in |
| `experience_json` | text | JSON list of experience entries |
| `education` | text | |
| `summary` | text | |
| `created_at` | datetime | |

### jobs

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | |
| `title`, `company`, `location` | text | Cleaned single lines |
| `description` | text | Plain text, sanitised, at most 20 000 characters |
| `source` | varchar(64) | Source key, e.g. `remoteok`, `linkedin`, `naukri`, `manual` |
| `url` | text | Posting link; LinkedIn links stored as `https://www.linkedin.com/jobs/view/<id>/` |
| `posted_date` | datetime | When the site says it was posted, if known |
| `experience_years` | integer | Years asked, read from the posting, if found |
| `dedupe_hash` | varchar(64), unique | sha256 of the URL, else of title, company and location |
| `scraped_at` | datetime, indexed | First time this app stored it |

The first copy of a job wins; a later copy only fills fields that were empty.

### matches

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | |
| `resume_id` | FK resumes, indexed | |
| `job_id` | FK jobs | Unique together with `resume_id` |
| `confidence_score` | float, indexed | Total 0 to 100 |
| `ats_score`, `experience_score`, `semantic_score`, `freshness_score` | float | Parts of the total |
| `status` | varchar(32) | `new`, `saved`, `applied`, `rejected`, `hidden` |
| `calculated_at` | datetime | |

### documents

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | |
| `match_id` | FK matches, indexed | |
| `doc_type` | varchar(32) | e.g. cover letter, resume suggestions |
| `content` | text | Generated text |
| `file_path` | text | Saved file under `DOCS_DIR` |
| `generated_at` | datetime | |

## Files outside the database

| File | Holds |
| --- | --- |
| `DOCS_DIR/` (default `~/jobhunt_docs`) | Generated documents, `backups/` |
| `DOCS_DIR/.jobspy_last_run.json` | Last search time per JobSpy site (`{"linkedin": <unix time>}`) |
| `eval/labeled_jobs.json` | Hand labels for matching evaluation (committed) |

## Migrations and upkeep

- `init_db()` runs Alembic to `head` on start; `0001_baseline` creates only what is missing,
  so older databases upgrade in place. Without Alembic it falls back to `create_all` plus
  `_ADDED_COLUMNS`.
- New column: add it to the model, write a migration, add it to `_ADDED_COLUMNS` if it is
  nullable, update this file.
- `scripts/housekeeping.py backup` copies the database and writes CSVs;
  `delete_stale_jobs` removes jobs older than 30 days (default) unless saved, applied or
  used for a document.
- All access goes through `db/repository.py`, which returns plain dicts.
