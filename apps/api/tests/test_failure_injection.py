from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.dependencies import get_db_session
from apps.api.app.main import app


@pytest.mark.asyncio(loop_scope="session")
async def test_database_unavailable_returns_recoverable_service_error(
    api_client: httpx.AsyncClient,
) -> None:
    original = app.dependency_overrides[get_db_session]

    async def unavailable_session() -> AsyncIterator[AsyncSession]:
        raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db_session] = unavailable_session
    try:
        response = await api_client.get("/api/runs/00000000-0000-0000-0000-000000000000")
    finally:
        app.dependency_overrides[get_db_session] = original

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json()["error"] == {
        "code": "DATABASE_UNAVAILABLE",
        "message": "The database is temporarily unavailable. Retry the request.",
        "request_id": response.headers["X-Request-ID"],
        "details": {"recoverable": True},
    }
