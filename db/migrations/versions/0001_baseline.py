"""Baseline: the schema as it stood before migrations were introduced.

Databases made earlier by ``Base.metadata.create_all`` already hold some or all of these
tables, so every step here only creates what is missing. That lets one ``upgrade head``
bring a fresh database, an old one and a current one to the same place.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    have = _tables()
    if "resumes" not in have:
        op.create_table(
            "resumes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("file_path", sa.Text()),
            sa.Column("raw_text", sa.Text()),
            sa.Column("skills_json", sa.Text()),
            sa.Column("extra_skills_json", sa.Text()),
            sa.Column("experience_json", sa.Text()),
            sa.Column("education", sa.Text()),
            sa.Column("summary", sa.Text()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    elif "extra_skills_json" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("resumes")}:
        op.add_column("resumes", sa.Column("extra_skills_json", sa.Text()))  # added in Phase 4

    if "jobs" not in have:
        op.create_table(
            "jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.Text()),
            sa.Column("company", sa.Text()),
            sa.Column("location", sa.Text()),
            sa.Column("description", sa.Text()),
            sa.Column("source", sa.String(64)),
            sa.Column("url", sa.Text()),
            sa.Column("posted_date", sa.DateTime()),
            sa.Column("experience_years", sa.Integer()),
            sa.Column("dedupe_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("scraped_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_jobs_scraped_at", "jobs", ["scraped_at"])

    if "matches" not in have:
        op.create_table(
            "matches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("resume_id", sa.Integer(), sa.ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("confidence_score", sa.Float()),
            sa.Column("ats_score", sa.Float()),
            sa.Column("experience_score", sa.Float()),
            sa.Column("semantic_score", sa.Float()),
            sa.Column("freshness_score", sa.Float()),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("calculated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("resume_id", "job_id", name="uq_matches_resume_job"),
        )
        op.create_index("ix_matches_resume_id", "matches", ["resume_id"])
        op.create_index("ix_matches_confidence_score", "matches", ["confidence_score"])

    if "documents" not in have:
        op.create_table(
            "documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("doc_type", sa.String(32), nullable=False),
            sa.Column("content", sa.Text()),
            sa.Column("file_path", sa.Text()),
            sa.Column("generated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_documents_match_id", "documents", ["match_id"])


def downgrade() -> None:
    for table in ("documents", "matches", "jobs", "resumes"):
        op.drop_table(table)
