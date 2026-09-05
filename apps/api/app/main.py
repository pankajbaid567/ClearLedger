"""ClearLedger FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from apps.api.app.auth import get_principal
from apps.api.app.config import settings
from apps.api.app.errors import APIError
from apps.api.app.middleware.correlation import CorrelationIdMiddleware
from apps.api.app.routes import ai, auth, cases, cash, exports, review, runs
from db.session import configure_database, dispose_database, get_engine
from services.reconciliation.run_service import RunServiceError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    engine = configure_database(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("Database unavailable during startup; readiness will remain degraded")
    try:
        yield
    finally:
        await dispose_database()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_origin_regex=(
        r"^http://(?:localhost|127\.0\.0\.1):\d+$"
        if settings.app_mode == "local_demo"
        else None
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIdMiddleware)


def _error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", "req_unknown"),
                "details": details or {},
            }
        },
    )


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return _error_response(
        request,
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


@app.exception_handler(RunServiceError)
async def run_service_error_handler(request: Request, exc: RunServiceError) -> JSONResponse:
    return _error_response(
        request,
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = {
        "issues": [
            {
                "location": [str(part) for part in error["loc"]],
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
    }
    return _error_response(
        request,
        code="REQUEST_VALIDATION_FAILED",
        message="The request did not satisfy the API contract.",
        status_code=422,
        details=details,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, _: SQLAlchemyError) -> JSONResponse:
    return _error_response(
        request,
        code="DATABASE_UNAVAILABLE",
        message="The database is temporarily unavailable. Retry the request.",
        status_code=503,
        details={"recoverable": True},
        headers={"Retry-After": "5"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, _: Exception) -> JSONResponse:
    return _error_response(
        request,
        code="INTERNAL_SERVER_ERROR",
        message="The request could not be completed.",
        status_code=500,
    )


for router in (runs.router, cases.router, review.router, exports.router, cash.router, ai.router):
    app.include_router(router, dependencies=[Depends(get_principal)])
app.include_router(auth.router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str]:
    async with get_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}
