"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from atlas import __version__
from atlas.api.routes_campaigns import router as campaigns_router
from atlas.api.routes_turns import router as turns_router
from atlas.config import Settings, get_settings
from atlas.domain.errors import (
    DomainError,
    InvalidTurnPlanError,
    NarrationValidationError,
    NotFoundError,
    TurnFailedError,
    TurnPendingError,
    UnparsedIntentError,
    VersionConflictError,
)
from atlas.game.turn_service import TurnService
from atlas.persistence.db import create_db_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    resolved.assert_mode_is_configured()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title="ATLAS",
        version=__version__,
        description="Local-first solo roleplaying engine. M1 transactional turn engine.",
        lifespan=lifespan,
    )
    engine = create_db_engine(resolved.database_url)
    session_factory = create_session_factory(engine)
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.turn_service = TurnService(session_factory)

    app.include_router(campaigns_router)
    app.include_router(turns_router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        status = 400
        if isinstance(exc, NotFoundError):
            status = 404
        elif isinstance(exc, (VersionConflictError, TurnPendingError, TurnFailedError)):
            status = 409
        elif isinstance(exc, (InvalidTurnPlanError, UnparsedIntentError, NarrationValidationError)):
            status = 422
        elif exc.code.startswith("invariant."):
            status = 422
        return JSONResponse(status_code=status, content={"error": exc.as_dict()})

    @app.get("/healthz")
    def healthz() -> Any:
        schema_version: str | None = None
        try:
            with app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                schema_version = connection.scalar(text("SELECT version_num FROM alembic_version"))
        except Exception as exc:  # pragma: no cover - operational failure path
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "version": __version__,
                    "mode": resolved.mode,
                    "database": "unavailable",
                    "error": type(exc).__name__,
                },
            )
        return {
            "status": "ok",
            "version": __version__,
            "mode": resolved.mode,
            "database": "ok",
            "schema_version": schema_version,
        }

    return app


app = create_app()
