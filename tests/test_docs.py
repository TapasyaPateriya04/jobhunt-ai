"""The design docs stay in step with the code (see AGENTS.md, "Keep the docs current")."""
from dataclasses import fields
from pathlib import Path

import pytest

from config import Settings
from db.database import Base
from scraper import service

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["docs/PRD.md", "docs/DESIGN_SYSTEM.md", "docs/ARCHITECTURE.md", "docs/DATABASE.md",
        "SECURITY.md", "docs/CODE_STYLE.md", "docs/TESTING.md", "AGENTS.md"]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", DOCS)
def test_every_doc_exists_and_is_linked_from_agents(name):
    assert _read(name).strip()
    assert name in _read("AGENTS.md")


def test_architecture_names_every_job_source():
    text = _read("docs/ARCHITECTURE.md")
    assert [s for s in service.ALL_SOURCES if f"`{s}`" not in text] == []


@pytest.mark.parametrize("doc", ["docs/ARCHITECTURE.md", ".env.example"])
def test_every_setting_is_documented(doc):
    text = _read(doc)
    assert [f.name.upper() for f in fields(Settings) if f.name.upper() not in text] == []


def test_database_doc_names_every_table_and_column():
    text = _read("docs/DATABASE.md")
    missing = []
    for table in Base.metadata.sorted_tables:
        if f"### {table.name}" not in text:
            missing.append(table.name)
        missing += [f"{table.name}.{c.name}" for c in table.columns if f"`{c.name}`" not in text]
    assert missing == []
