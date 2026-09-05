"""Database-backed idempotency controls for mutation endpoints."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.errors import APIError
from db.models import IdempotencyRecord


def _request_checksum(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(data).hexdigest()


async def replay_response(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    request_payload: Any,
) -> JSONResponse | None:
    result = await session.scalars(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    existing = result.one_or_none()
    if existing is None:
        return None
    checksum = _request_checksum(request_payload)
    if existing.request_checksum != checksum:
        raise APIError(
            "IDEMPOTENCY_KEY_REUSED",
            "This idempotency key was already used with a different request.",
            status_code=409,
            details={"scope": scope},
        )
    return JSONResponse(existing.response_payload, status_code=existing.response_status)


async def store_response(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    request_payload: Any,
    response_payload: dict[str, Any],
    status_code: int = 200,
) -> None:
    session.add(
        IdempotencyRecord(
            scope=scope,
            idempotency_key=key,
            request_checksum=_request_checksum(request_payload),
            response_status=status_code,
            response_payload=response_payload,
        )
    )
    await session.flush()
