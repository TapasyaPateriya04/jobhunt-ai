"""The local API the React front end talks to.

Read and call only: every route reads settings or calls a function the Streamlit app
already calls. No job source, scoring rule or prompt lives here. The server binds to
127.0.0.1 (see ``api/server.py``), so the resume, the database and the drafts stay on
this machine.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.core import ROOT, FeatureUnavailable, load, log
from api.routes_documents import router as documents_router
from api.routes_jobs import router as jobs_router
from api.routes_matches import router as matches_router
from api.routes_meta import router as meta_router
from api.routes_resume import router as resume_router

WEB_DIST = ROOT / "web" / "dist"
# Vite's dev server, which proxies /api here. Only loopback origins are allowed.
DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up logging and the database schema once, as ui/app.py does on first run."""
    try:
        load("security.logging_setup", "setup_logging")()
    except Exception:
        pass  # logging is nice to have
    try:
        load("db.database", "init_db")()
        app.state.database_problem = ""
    except Exception as exc:
        log.exception("init_db failed")
        app.state.database_problem = (
            f"The database could not be set up ({type(exc).__name__}). Check DATABASE_URL in .env.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="JobHunt AI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database_problem = ""
    app.add_middleware(CORSMiddleware, allow_origins=DEV_ORIGINS, allow_methods=["*"],
                       allow_headers=["*"], allow_credentials=False)

    @app.exception_handler(FeatureUnavailable)
    async def _unavailable(_: Request, exc: FeatureUnavailable) -> JSONResponse:
        """A missing optional library reads as a sentence, never a traceback."""
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/api/health")
    def health(request: Request) -> dict:
        return {"ok": True, "database_problem": getattr(request.app.state, "database_problem", "")}

    for router in (meta_router, resume_router, jobs_router, matches_router, documents_router):
        app.include_router(router, prefix="/api")

    _serve_built_app(app)
    return app


def _built_file(path: str) -> Path | None:
    """A file inside web/dist, or None when the path escapes it or is not there."""
    if not path or path.endswith("/"):
        return None
    try:
        target = (WEB_DIST / path).resolve()
        target.relative_to(WEB_DIST.resolve())
    except (ValueError, OSError):
        return None
    return target if target.is_file() else None


def _serve_built_app(app: FastAPI) -> None:
    """Serve ``web/dist`` when it has been built, so one URL runs the whole app.

    While developing, Vite serves the pages instead and proxies /api to here.
    """
    if not (WEB_DIST / "index.html").is_file():
        return
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def page(path: str) -> FileResponse:
        found = _built_file(path)
        # Anything else is a route the front end handles itself (/privacy, /terms).
        return FileResponse(found if found else WEB_DIST / "index.html")


app = create_app()
