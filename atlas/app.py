from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from atlas import __version__
from atlas.agents.types import AgentError, Provider
from atlas.api.routes import router
from atlas.api.schemas import error_body
from atlas.config import Settings
from atlas.errors import BudgetExceeded, EmptyNarration, LeakDetected
from atlas.game import CampaignService
from atlas.state.store import CampaignNotFound
from atlas.state.validate import InvalidState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIST = PROJECT_ROOT / "web" / "dist"


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    settings = settings or Settings()
    service = CampaignService(settings, provider=provider)

    app = FastAPI(title="ATLAS", version=__version__)
    app.state.settings = settings
    app.state.service = service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "provider": settings.provider,
            "live": settings.live,
            "campaigns": len(service.list_campaigns()),
        }

    @app.exception_handler(CampaignNotFound)
    def _not_found(_: Request, exc: CampaignNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404, content=error_body("not_found", f"campaign {exc} not found")
        )

    @app.exception_handler(LeakDetected)
    def _leak(_: Request, exc: LeakDetected) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("content_leak", str(exc)),
        )

    @app.exception_handler(EmptyNarration)
    def _empty(_: Request, exc: EmptyNarration) -> JSONResponse:
        return JSONResponse(status_code=502, content=error_body("empty_narration", str(exc)))

    @app.exception_handler(AgentError)
    def _agent(_: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(status_code=502, content=error_body("provider_error", str(exc)))

    @app.exception_handler(BudgetExceeded)
    def _budget(_: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse(status_code=402, content=error_body("budget_exceeded", str(exc)))

    @app.exception_handler(InvalidState)
    def _invalid(_: Request, exc: InvalidState) -> JSONResponse:
        return JSONResponse(status_code=422, content=error_body("invalid_state", str(exc)))

    @app.exception_handler(ValueError)
    def _value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content=error_body("invalid_request", str(exc)))

    app.include_router(router)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False, response_model=None)
    def spa(full_path: str) -> FileResponse | JSONResponse:
        if full_path.startswith("api/") or full_path == "healthz":
            return JSONResponse(status_code=404, content=error_body("not_found", "no such route"))
        if full_path:
            candidate = (WEB_DIST / full_path).resolve()
            if WEB_DIST.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        index = WEB_DIST / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            status_code=404,
            content=error_body(
                "frontend_missing",
                "the frontend has not been built; run 'npm run build' in web/ "
                "or use the Vite dev server",
            ),
        )
