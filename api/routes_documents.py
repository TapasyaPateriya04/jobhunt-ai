"""Documents screen: draft a cover letter or resume suggestions, check it, save it, export it."""
from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api import catalog
from api.core import g, jsonable, llm_error, load, log, repo, score_of, settings
from api.matching_view import band_of
from api.routes_meta import GEMINI, ollama_reachable

router = APIRouter()


class DraftIn(BaseModel):
    match_id: int
    doc_type: str = "cover_letter"
    model: str | None = None


class ContentIn(BaseModel):
    match_id: int
    doc_type: str = "cover_letter"
    content: str
    resume_id: int | None = None


class ExportIn(BaseModel):
    content: str
    title: str = ""
    kind: str = "docx"


@router.get("/documents/jobs")
def draftable_jobs(resume_id: int) -> dict:
    """The jobs you can write for: tracked ones first, then the rest by score."""
    matches = repo().list_matches(resume_id, limit=100)
    rank = {"saved": 0, "applied": 1}
    matches.sort(key=lambda m: (rank.get(g(m, "status", default="new"), 2), -score_of(m)))
    return {"jobs": [{
        "id": g(m, "id", "match_id"),
        "title": g(m, "title", default="Untitled role"),
        "company": g(m, "company", default="Unknown company"),
        "location": g(m, "location", default="") or "",
        "status": g(m, "status", default="new"),
        "status_label": catalog.status_name(g(m, "status", default="new")),
        "score": round(score_of(m), 1),
        "band_label": catalog.band_label(band_of(score_of(m))),
        "source_name": catalog.source_name(g(m, "source", default="")),
        "posted_date": jsonable(g(m, "posted_date")),
    } for m in matches]}


@router.get("/documents/writer")
def writer(model: str | None = None) -> dict:
    """Whether a model is ready, and one line saying which one will write."""
    s = settings()
    if model == GEMINI:
        return {"ready": True,
                "note": "Written by Gemini. Your resume and the posting are sent to Google for this."}
    if model:
        return {"ready": True,
                "note": f"Written by {model} on this machine. Without a graphics card this can take "
                        "a few minutes."}
    if bool(getattr(s, "use_ollama", True)) and ollama_reachable(str(getattr(s, "ollama_base_url", ""))):
        return {"ready": True,
                "note": f"Written by Ollama ({getattr(s, 'ollama_model', 'mistral')}) on this machine."}
    if getattr(s, "gemini_api_key", None):
        return {"ready": True,
                "note": "Written by Gemini. Your resume and the posting are sent to Google for this."}
    return {"ready": False,
            "note": "No language model is ready, so Generate cannot write yet. The sidebar shows what "
                    "is missing."}


@router.post("/documents/draft")
def draft(body: DraftIn) -> StreamingResponse:
    """Stream a draft as the model writes it, so the first words appear straight away."""
    if body.doc_type not in catalog.DOC_TYPES:
        raise HTTPException(status_code=400, detail="Unknown document type.")
    match = _match(body.match_id)
    resume = repo().get_resume(match["resume_id"])
    if not resume:
        raise HTTPException(status_code=404, detail="The resume for this job is not stored any more.")
    job = _job_for(match)

    def chunks() -> Iterator[bytes]:
        try:
            if body.doc_type == "cover_letter":
                gen = load("generator.cover_letter")
                for part in gen.stream_cover_letter(resume, job, model=body.model):
                    yield str(part).encode("utf-8")
            else:
                stream = load("generator.resume_optimizer", "stream_resume_edits")
                for part in stream(resume, job, model=body.model):
                    yield str(part).encode("utf-8")
        except Exception as exc:
            # The response has already started, so the message goes in the body on its own line.
            yield ("\n\n[" + llm_error(exc, "write this draft") + "]").encode("utf-8")

    return StreamingResponse(chunks(), media_type="text/plain; charset=utf-8",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/documents/tidy")
def tidy(body: ContentIn) -> dict:
    """The finished cover letter with the model's preamble and sign-off noise removed.

    The draft streams raw so the first words show at once; this is called when the stream
    ends, so the text the user edits is the same text the Streamlit app produces.
    """
    if body.doc_type != "cover_letter":
        return {"content": body.content.strip()}
    try:
        return {"content": load("generator.cover_letter", "clean_cover_letter")(body.content)}
    except Exception:
        log.exception("cleaning the cover letter failed")
        return {"content": body.content.strip()}


@router.post("/documents/check")
def check(body: ContentIn) -> dict:
    """Sentences that claim more than the resume shows (models embellish)."""
    match = _match(body.match_id)
    resume = repo().get_resume(body.resume_id or match["resume_id"])
    if not resume:
        return {"flags": []}
    try:
        flags = load("generator.fact_check", "check_draft")(body.content, resume, _job_for(match))
    except Exception:
        log.exception("draft check failed")
        return {"flags": [], "error": "The draft could not be checked. Read it once yourself."}
    return {"flags": [{"sentence": f["sentence"][:300], "why": f["why"]} for f in flags]}


@router.post("/documents/save")
def save(body: ContentIn) -> dict:
    """Keep a copy in the documents folder and list it under this job."""
    if body.doc_type not in catalog.DOC_TYPES:
        raise HTTPException(status_code=400, detail="Unknown document type.")
    _match(body.match_id)
    try:
        path = load("generator.documents", "save_generated_doc")(body.match_id, body.doc_type, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"path": str(path)}


@router.get("/documents")
def list_documents(match_id: int) -> dict:
    try:
        docs = repo().list_documents(match_id)
    except Exception:
        log.exception("list_documents failed")
        return {"documents": []}
    return {"documents": [{
        "id": d.get("id"),
        "doc_type": d.get("doc_type"),
        "label": catalog.DOC_TYPES.get(d.get("doc_type"), str(d.get("doc_type"))),
        "generated_at": jsonable(d.get("generated_at")),
        "content": str(d.get("content") or ""),
        "words": len(str(d.get("content") or "").split()),
    } for d in docs]}


@router.post("/documents/export")
def export(body: ExportIn) -> Response:
    """The draft as a Word or PDF file."""
    exporter = load("ui.export")
    builders = {"docx": (exporter.to_docx,
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "pdf": (exporter.to_pdf, "application/pdf")}
    if body.kind not in builders:
        raise HTTPException(status_code=400, detail="Unknown file type.")
    build, media = builders[body.kind]
    try:
        data = build(body.content, body.title)
    except exporter.ExportUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("export to %s failed", body.kind)
        raise HTTPException(status_code=500,
                            detail=f"This draft could not be turned into a .{body.kind} file.") from exc
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="document.{body.kind}"'})


@router.get("/documents/export-formats")
def export_formats() -> dict:
    """Which file types this machine can write, so disabled buttons can say why."""
    exporter = load("ui.export")
    out = []
    for kind, build in (("docx", exporter.to_docx), ("pdf", exporter.to_pdf)):
        try:
            build("Ready", "Ready")
            out.append({"kind": kind, "available": True, "reason": ""})
        except exporter.ExportUnavailable as exc:
            out.append({"kind": kind, "available": False, "reason": str(exc)})
        except Exception:
            out.append({"kind": kind, "available": False,
                        "reason": f"A .{kind} file could not be written on this machine."})
    return {"formats": out}


def _match(match_id: int) -> dict:
    """One match row by id, looked up through the resume it belongs to."""
    dbm = load("db.database")
    with dbm.get_session() as session:
        row = session.get(dbm.Match, match_id)
        if row is None:
            raise HTTPException(status_code=404, detail="That job is not in your matches.")
        resume_id, job_id = row.resume_id, row.job_id
    for m in repo().list_matches(resume_id, limit=1000):
        if m.get("id") == match_id:
            return m
    return {"id": match_id, "resume_id": resume_id, "job_id": job_id}


def _job_for(match: dict) -> dict:
    job_id = g(match, "job_id")
    if job_id is not None:
        try:
            job = repo().get_job(job_id)
            if job:
                return job
        except Exception:
            log.warning("get_job failed")
    keys = ("title", "company", "location", "description", "source", "url", "posted_date", "experience_years")
    return {k: match.get(k) for k in keys}
