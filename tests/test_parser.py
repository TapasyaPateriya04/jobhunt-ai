from pathlib import Path

import pytest

from parser.jd_analyzer import analyze_jd, top_keywords
from parser.resume_parser import (
    extract_sections,
    parse_latex_resume,
    parse_resume_bytes,
    parse_resume_text,
)
from parser.skills_vocab import find_skills

FIX = Path(__file__).parent / "fixtures"
CONTRACT_KEYS = {"raw_text", "skills", "experience", "education", "summary"}


@pytest.fixture(scope="module")
def latex_resume():
    return parse_latex_resume(FIX / "sample_resume.tex")


def test_latex_resume_contract_keys(latex_resume):
    assert CONTRACT_KEYS <= set(latex_resume)
    assert isinstance(latex_resume["skills"], list)
    assert "\\section" not in latex_resume["raw_text"]
    assert "newcommand" not in latex_resume["raw_text"]


def test_latex_sections(latex_resume):
    assert "Python services" in latex_resume["summary"]
    assert "State University" in latex_resume["education"]
    assert "JobHunt AI" in latex_resume["projects"]


def test_latex_skills_canonical_and_symbols(latex_resume):
    skills = latex_resume["skills"]
    for s in ["Python", "C++", "C#", "Node.js", "FastAPI", "Kubernetes", "CI/CD", "scikit-learn",
              "Pandas", "PostgreSQL", "Apache Airflow"]:
        assert s in skills, s
    # unknown item from the Skills section is kept as-is
    assert "WidgetFlow" in skills
    # no duplicates, case-insensitive
    assert len({s.lower() for s in skills}) == len(skills)


def test_latex_experience_entries(latex_resume):
    exp = latex_resume["experience"]
    assert len(exp) == 2
    first, second = exp
    assert first["title"] == "Senior Software Engineer"
    assert first["company"] == "Acme Corp"
    assert first["start"] == "2021-01"
    assert first["end"] is not None and first["years"] > 4
    assert second == {**second, "title": "Software Engineer", "company": "Globex Inc",
                      "start": "2018-06", "end": "2020-12"}
    assert 2.4 <= second["years"] <= 2.6
    assert "Airflow" in second["description"]
    assert latex_resume["total_experience_years"] >= 7


def test_plain_text_resume():
    parsed = parse_resume_text((FIX / "sample_resume.txt").read_text(encoding="utf-8"))
    assert CONTRACT_KEYS <= set(parsed)
    assert parsed["summary"].startswith("Full-stack developer")
    assert {"C#", ".NET", "Node.js", "TypeScript", "HotChocolate"} <= set(parsed["skills"])
    titles = [(e["title"], e["company"], e["start"]) for e in parsed["experience"]]
    assert ("Full Stack Developer", "Initech", "2020-03") in titles
    assert ("Junior Developer", "Globex Corp", "2017-07") in titles
    assert "Some Institute" in parsed["education"]


def test_parse_resume_bytes_dispatch():
    tex = (FIX / "sample_resume.tex").read_bytes()
    assert "Python" in parse_resume_bytes("cv.tex", tex)["skills"]
    md = b"# Jane\n\n## Skills\n- **Python**, [Django](https://djangoproject.com)\n\n## Education\nMIT"
    parsed = parse_resume_bytes("cv.md", md)
    assert {"Python", "Django"} <= set(parsed["skills"])
    assert parsed["education"] == "MIT"
    with pytest.raises(ValueError):
        parse_resume_bytes("cv.exe", b"MZ")


def test_pdf_without_pypdf_gives_helpful_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "pypdf":
            raise ImportError("no pypdf")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ValueError, match="pypdf"):
        parse_resume_bytes("cv.pdf", b"%PDF-1.4")


def test_extract_sections_headings_variants():
    text = "Jane\n\nTECHNICAL SKILLS:\nPython\n\n## Work Experience\nStuff\n\n**Education**\nBSc"
    sec = extract_sections(text)
    assert sec["skills"] == "Python"
    assert sec["experience"] == "Stuff"
    assert sec["education"] == "BSc"


@pytest.mark.parametrize("text,expected,absent", [
    ("Expert in C++ and C# and Node.js", {"C++", "C#", "Node.js"}, {"C"}),
    ("golang, k8s, sklearn, Postgres", {"Go", "Kubernetes", "scikit-learn", "PostgreSQL"}, set()),
    ("We go to the office in spring", set(), {"Go", "Spring Boot"}),
    ("Experienced with react.js and REACT", {"React"}, set()),
    ("Deployed on AWS; used CI/CD pipelines", {"AWS", "CI/CD"}, set()),
])
def test_find_skills_boundaries(text, expected, absent):
    found = set(find_skills(text))
    assert expected <= found
    assert not (absent & found)


def test_analyze_jd():
    jd = ("Senior Backend Engineer. You have 5+ years of experience with Python and Django, "
          "2-4 yrs with AWS. Our company is 20 years old. Kubernetes is a plus. Python everywhere.")
    out = analyze_jd(jd)
    assert out["experience_years"] == 5
    assert {"Python", "Django", "AWS", "Kubernetes"} <= set(out["skills"])
    assert out["keywords"][0] == "python"
    assert "the" not in out["keywords"]


def test_analyze_jd_empty():
    assert analyze_jd("") == {"skills": [], "experience_years": None, "keywords": []}
    assert top_keywords("c++ c++ node.js") == ["c++", "node.js"]
