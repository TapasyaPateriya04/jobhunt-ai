"""Tests for config.get_settings."""
from pathlib import Path

import pytest

import config

ENV_VARS = [
    "DATABASE_URL", "USE_OLLAMA", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "GEMINI_API_KEY", "GEMINI_MODEL",
    "DOCS_DIR", "SCRAPE_DELAY_SECONDS", "MAX_JOBS_PER_SESSION", "UPLOAD_MAX_BYTES", "ALLOW_REMOTE_LLM",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # so a developer's real .env is not picked up
    monkeypatch.setattr(config, "load_dotenv", lambda **kw: False)


def test_defaults():
    s = config.get_settings()
    assert s.database_url == "sqlite:///jobhunt.db"
    assert s.use_ollama is True
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.ollama_model == "mistral"
    assert s.gemini_api_key is None
    assert s.gemini_model == "gemini-3.8-flash"
    assert s.docs_dir == Path("~/jobhunt_docs").expanduser()
    assert s.scrape_delay_seconds == 3.0
    assert s.max_jobs_per_session == 50
    assert s.upload_max_bytes == 2_000_000
    assert s.allow_remote_llm is False


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_OLLAMA", "false")
    monkeypatch.setenv("GEMINI_API_KEY", " AIzaSECRET ")
    monkeypatch.setenv("DOCS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("SCRAPE_DELAY_SECONDS", "5")
    monkeypatch.setenv("MAX_JOBS_PER_SESSION", "20")
    s = config.get_settings()
    assert s.use_ollama is False
    assert s.gemini_api_key == "AIzaSECRET"
    assert s.docs_dir == tmp_path / "docs"
    assert s.scrape_delay_seconds == 5.0
    assert s.max_jobs_per_session == 20


def test_invalid_values_fall_back(monkeypatch):
    monkeypatch.setenv("USE_OLLAMA", "maybe")
    monkeypatch.setenv("SCRAPE_DELAY_SECONDS", "abc")
    monkeypatch.setenv("MAX_JOBS_PER_SESSION", "-5")
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    s = config.get_settings()
    assert s.use_ollama is True
    assert s.scrape_delay_seconds == 3.0
    assert s.max_jobs_per_session == 1  # clamped to minimum
    assert s.gemini_api_key is None


def test_key_not_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTOPSECRET")
    assert "AIzaTOPSECRET" not in repr(config.get_settings())


def test_dotenv_file_loaded_without_overriding_env(monkeypatch, tmp_path):
    monkeypatch.undo()  # restore real load_dotenv
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / "custom.env"
    env_file.write_text("OLLAMA_MODEL=llama3\nGEMINI_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_MODEL", "from-env")
    s = config.get_settings(env_file=env_file)
    assert s.ollama_model == "llama3"
    assert s.gemini_model == "from-env"
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)  # load_dotenv wrote into os.environ
