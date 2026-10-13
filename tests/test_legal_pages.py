"""The privacy and terms pages render, are linked from the app, and the UI keeps the owner's design rules."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from tests.test_ui import ui_env  # noqa: E402,F401  (fixture: empty database in a temp folder)

UI = Path(__file__).resolve().parent.parent / "ui"
PAGES = {"privacy.py": "Privacy policy", "terms.py": "Terms and conditions"}


@pytest.mark.parametrize("page,title", PAGES.items())
def test_legal_page_renders(ui_env, page, title):
    # Start from the app, as a user does, so the pages' links back to app.py resolve.
    at = AppTest.from_file(str(UI / "app.py"), default_timeout=60)
    at.run()
    at.switch_page(f"pages/{page}")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == title
    text = " ".join(m.value for m in at.markdown)
    assert "Last updated" in " ".join(c.value for c in at.caption)
    assert "Ollama" in text or "warranty" in text


def test_favicon_is_a_file_not_an_emoji():
    from ui import components as c

    assert Path(c.FAVICON).is_file() and Path(c.FAVICON).suffix == ".png"
    assert [p for p, _ in c.LEGAL_PAGES] == ["pages/privacy.py", "pages/terms.py"]
    for path, _ in c.LEGAL_PAGES:
        assert (UI / path).is_file()


def _ui_sources():
    return [p for p in UI.rglob("*.py") if "__pycache__" not in p.parts]


def test_ui_has_no_em_dashes_or_emoji():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-⛿️]")
    for path in _ui_sources():
        text = path.read_text(encoding="utf-8")
        assert "—" not in text, f"em dash in {path.name}"
        assert not emoji.search(text), f"emoji in {path.name}"


def test_no_pill_shapes_or_gradients_in_css():
    from ui import components as c

    assert "999px" not in c.CSS and "border-radius:50px" not in c.CSS
    assert "gradient(" not in c.CSS


def test_footer_survives_pages_the_server_does_not_know(monkeypatch):
    """Pages added while the server runs are unknown until a restart; the footer must not crash."""
    import streamlit as st
    from streamlit.errors import StreamlitPageNotFoundError

    from ui import components as c

    shown = []

    def missing(path, label=None, **_):
        raise StreamlitPageNotFoundError(page=path, main_script_directory="ui", uses_pages_directory=True)

    monkeypatch.setattr(st, "page_link", missing)
    monkeypatch.setattr(st, "markdown", lambda text, **_: shown.append(text))
    monkeypatch.setattr(st, "divider", lambda: None)
    monkeypatch.setattr(st, "columns", lambda spec: [_Col() for _ in spec])
    c.legal_footer()
    assert shown == ["[Privacy policy](/privacy)", "[Terms and conditions](/terms)"]


class _Col:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_ui_text_never_names_the_scraping_library():
    """The owner's rule: the library behind LinkedIn and Naukri is not named anywhere a user reads."""
    import ast

    hits = []
    for path in [UI / "app.py", UI / "components.py", *sorted((UI / "pages").glob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            text = node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""
            # Identifiers (module paths, setting names, widget keys) are not shown to the user.
            if "jobspy" in text.lower() and id(node) not in docstrings and not re.fullmatch(r"[\w.]+", text):
                hits.append(f"{path.name}:{node.lineno}: {text[:60]}")
    assert hits == []
