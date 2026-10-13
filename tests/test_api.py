"""The local API behind the React front end: routes, wording and the main flow."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WEB_SRC = ROOT / "web" / "src"
RESUME_TEXT = (
    "Jane Doe\nSkills: Java, Spring Boot, SQL, React, Docker\n"
    "Experience\nBackend Engineer at Acme, 2024-2025\nEducation\nB.Tech Computer Science\n"
)
POSTING = (
    "Java Backend Developer\nInitech - Bengaluru, India\n"
    "We need a fresher with Java, Spring Boot, SQL and REST APIs. 0 to 2 years. Kafka is nice to have."
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client on an empty database in a temp folder, with no language model configured."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'api_test.db').as_posix()}")
    monkeypatch.setenv("DOCS_DIR", str(tmp_path / "docs"))
    monkeypatch.setenv("USE_OLLAMA", "false")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for module in [m for m in list(sys.modules) if m == "api" or m.startswith("api.")]:
        del sys.modules[module]
    import config

    clear = getattr(config.get_settings, "cache_clear", None)
    if callable(clear):
        clear()
    from db.database import dispose_engines

    dispose_engines()
    from api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    dispose_engines()
    if callable(clear):
        clear()


def test_health_and_catalog(client):
    assert client.get("/api/health").json()["ok"] is True
    catalog = client.get("/api/catalog").json()
    keys = {source["key"] for source in catalog["sources"]}
    assert {"remoteok", "hn", "themuse", "arbeitnow", "himalayas"} <= keys
    assert [part["key"] for part in catalog["score_parts"]] == ["ats", "experience", "semantic", "freshness"]
    assert sum(part["weight"] for part in catalog["score_parts"]) == pytest.approx(1.0)


def test_catalog_names_match_the_streamlit_app():
    """One app must not call a source or a status something the other does not."""
    pytest.importorskip("streamlit")
    from api import catalog
    from ui import components as c

    assert set(catalog.SOURCES) == set(c.SOURCES)
    assert catalog.MATCH_STATUSES == c.MATCH_STATUSES
    assert catalog.TRACKED_STATUSES == c.TRACKED_STATUSES
    assert catalog.DEFAULT_SOURCES == c.DEFAULT_SOURCES
    assert catalog.OPT_IN_SOURCES == c.JOBSPY_SOURCES


def test_overview_names_the_next_step(client):
    overview = client.get("/api/overview").json()
    assert overview["has_resume"] is False
    assert overview["next_step"]["tab"] == "resume"


def test_the_whole_flow(client):
    upload = client.post("/api/resume/upload", files={"file": ("resume.txt", RESUME_TEXT, "text/plain")})
    assert upload.status_code == 200, upload.text
    resume = upload.json()["resume"]
    assert "Java" in resume["skills"]
    assert resume["suggested_keywords"].startswith("Java")

    added = client.post("/api/jobs/manual", json={"text": POSTING, "resume_id": resume["id"]})
    assert added.status_code == 200, added.text
    assert added.json()["new"] is True
    assert added.json()["scored"] == 1

    client.post(f"/api/resume/{resume['id']}/score", params={"country": "India"})
    listed = client.get("/api/matches", params={"resume_id": resume["id"], "country": "India"}).json()
    match = listed["matches"][0]
    assert match["title"] == "Java Backend Developer"
    assert match["score"] > 0
    assert match["band"] in {"hi", "mid", "low"}
    assert set(match["parts"]) == {"ats", "experience", "semantic", "freshness"}
    assert match["location_status"] == "local"
    assert "Java" in match["gap"]["required"]

    detail = client.get(f"/api/matches/{match['id']}", params={"resume_id": resume["id"]}).json()
    assert "Spring Boot" in detail["description"]

    status = client.patch(f"/api/matches/{match['id']}/status", json={"status": "saved"})
    assert status.status_code == 200
    assert "Applications" in status.json()["message"]
    tracked = client.get("/api/matches", params={"resume_id": resume["id"]}).json()["matches"]
    assert tracked[0]["status"] == "saved"

    jobs = client.get("/api/documents/jobs", params={"resume_id": resume["id"]}).json()["jobs"]
    assert jobs[0]["id"] == match["id"]


def test_added_skills_are_kept_and_removed(client):
    resume = client.post(
        "/api/resume/upload", files={"file": ("resume.txt", RESUME_TEXT, "text/plain")}
    ).json()["resume"]
    added = client.post(f"/api/resume/{resume['id']}/skills", json={"add": "Kafka, Hibernate"}).json()
    assert added["added"] == ["Kafka", "Hibernate"]
    assert set(added["resume"]["extra_skills"]) == {"Kafka", "Hibernate"}
    removed = client.post(f"/api/resume/{resume['id']}/skills", json={"remove": "Kafka"}).json()
    assert removed["resume"]["extra_skills"] == ["Hibernate"]


def test_bad_input_reads_as_a_sentence(client):
    assert client.post("/api/jobs/search", json={"keywords": "", "sources": ["remoteok"]}).json()["detail"] == (
        "Enter at least one keyword."
    )
    assert client.post("/api/jobs/search", json={"keywords": "Java", "sources": []}).json()["detail"] == (
        "Pick at least one source."
    )
    assert client.post("/api/jobs/manual", json={"text": "  "}).status_code == 400
    assert client.get("/api/matches", params={"resume_id": 999}).status_code == 404


def test_the_server_binds_to_this_machine_only():
    from api import server

    assert server.HOST == "127.0.0.1"


def _web_sources() -> list[Path]:
    return [p for p in WEB_SRC.rglob("*.ts*")] + [p for p in (ROOT / "api").rglob("*.py")]


def test_front_end_never_names_the_scraping_library():
    """Owner's rule: the UI says LinkedIn and Naukri, never the library or its settings.

    Only text a user can see is checked. Python modules may name the library.
    """
    for path in [*WEB_SRC.rglob("*.ts*"), ROOT / "api" / "catalog.py"]:
        text = path.read_text(encoding="utf-8")
        assert "jobspy" not in text.lower(), f"the library is named in {path.name}"
        assert "JOBSPY_" not in text, f"a JOBSPY_ setting is named in {path.name}"


def test_front_end_has_no_em_dashes_or_emoji():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-⛿️]")
    for path in _web_sources():
        text = path.read_text(encoding="utf-8")
        assert "—" not in text, f"em dash in {path.name}"
        assert not emoji.search(text), f"emoji in {path.name}"


def test_theme_has_no_pill_shapes_or_gradients():
    css = (WEB_SRC / "theme.css").read_text(encoding="utf-8")
    assert "999px" not in css and "border-radius:50px" not in css
    # The only gradient is the grey shimmer of a loading placeholder.
    assert css.count("gradient(") == 1 and "--accent" not in css.split("skeleton")[1].split("}")[0]


def test_the_front_end_has_a_favicon_and_legal_pages():
    assert (ROOT / "web" / "public" / "favicon.png").is_file()
    assert (WEB_SRC / "pages" / "Privacy.tsx").is_file()
    assert (WEB_SRC / "pages" / "Terms.tsx").is_file()
    app = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    assert '"/privacy"' in app and '"/terms"' in app
