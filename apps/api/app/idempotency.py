"""Durable, pool-safe PostgreSQL idempotency claims and response replay."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.errors import APIError
from db.models import IdempotencyRecord

_IN_PROGRESS = "IN_PROGRESS"
_COMPLETED = "COMPLETED"
_LEASE_SECONDS = 30
_HEARTBEAT_SECONDS = 10
_POLL_SECONDS = 0.05


@dataclass
class _Claim:
    scope: str
    key: str
    token: str
    heartbeat: asyncio.Task[None]


def _request_checksum(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(data).hexdigest()


def _scope(session: AsyncSession, scope: str) -> str:
    principal = session.info.get("principal")
    return f"{principal.subject}:{scope}" if principal is not None else scope


def _engine(session: AsyncSession) -> AsyncEngine:
    bind = session.bind
    if bind is None:
        raise RuntimeError("Idempotency requires a bound database engine")
    return bind if isinstance(bind, AsyncEngine) else bind.engine


def _claims(session: AsyncSession) -> dict[tuple[str, str], _Claim]:
    return session.info.setdefault("idempotency_claims", {})


async def _heartbeat(engine: AsyncEngine, scope: str, key: str, token: str) -> None:
    """Renew a short lease without occupying a pool connection between renewals."""
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_SECONDS)
            lease = datetime.now(UTC) + timedelta(seconds=_LEASE_SECONDS)
            async with engine.begin() as connection:
                result = await connection.execute(
                    update(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.scope == scope,
                        IdempotencyRecord.idempotency_key == key,
                        IdempotencyRecord.state == _IN_PROGRESS,
                        IdempotencyRecord.claim_token == token,
                    )
                    .values(lease_expires_at=lease)
                )
            if result.rowcount != 1:
                return
    except asyncio.CancelledError:
        return
    except Exception:
        # The request still owns the durable lease until it expires. A waiter can
        # recover it if this worker or its database connection has failed.
        return


async def _record_claim(
    session: AsyncSession, *, scope: str, key: str, token: str
) -> None:
    heartbeat = asyncio.create_task(_heartbeat(_engine(session), scope, key, token))
    _claims(session)[(scope, key)] = _Claim(scope, key, token, heartbeat)


async def _stop_claim(claim: _Claim) -> None:
    claim.heartbeat.cancel()
    await claim.heartbeat


async def abandon_idempotency_claims(session: AsyncSession) -> None:
    """Release only claims owned by this request after an exception/cancellation."""
    claims = list(_claims(session).values())
    session.info.pop("idempotency_claims", None)
    if not claims:
        return
    for claim in claims:
        await _stop_claim(claim)
    try:
        for claim in claims:
            await session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.scope == claim.scope,
                    IdempotencyRecord.idempotency_key == claim.key,
                    IdempotencyRecord.state == _IN_PROGRESS,
                    IdempotencyRecord.claim_token == claim.token,
                )
            )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise


async def release_idempotency_locks(session: AsyncSession) -> None:
    """Compatibility alias for older integrations; claims replaced advisory locks."""
    await abandon_idempotency_claims(session)


async def _legacy_record(
    session: AsyncSession,
    *,
    raw_scopes: tuple[str, ...],
    scoped: str,
    key: str,
) -> tuple[str, str, int, dict[str, Any]] | None:
    for raw_scope in dict.fromkeys(raw_scopes):
        if raw_scope == scoped:
            continue
        row = (
            await session.execute(
                select(
                    IdempotencyRecord.request_checksum,
                    IdempotencyRecord.response_status,
                    IdempotencyRecord.response_payload,
                ).where(
                    IdempotencyRecord.scope == raw_scope,
                    IdempotencyRecord.idempotency_key == key,
                )
            )
        ).one_or_none()
        await session.rollback()
        if row is not None:
            checksum, status, payload = row
            return raw_scope, checksum, status, payload
    return None


async def replay_response(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    request_payload: Any,
    legacy_scopes: tuple[str, ...] = (),
) -> JSONResponse | None:
    """Atomically claim a key, or wait for and replay the owning request's response."""
    raw_scope = scope
    scope = _scope(session, scope)
    checksum = _request_checksum(request_payload)

    # Pre-authentication records cannot be attributed safely. Block reuse rather
    # than silently performing the mutation again under a newly scoped identity.
    legacy = await _legacy_record(
        session,
        raw_scopes=(raw_scope, *legacy_scopes),
        scoped=scope,
        key=key,
    )
    if legacy is not None:
        legacy_scope, legacy_checksum, _, _ = legacy
        code = (
            "LEGACY_IDEMPOTENCY_RECORD"
            if legacy_checksum == checksum
            else "IDEMPOTENCY_KEY_REUSED"
        )
        raise APIError(
            code,
            "This key belongs to a pre-authentication request and cannot be replayed safely. "
            "Inspect the original result before choosing a new key.",
            status_code=409,
            details={"scope": legacy_scope},
        )

    while True:
        token = uuid.uuid4().hex
        lease = datetime.now(UTC) + timedelta(seconds=_LEASE_SECONDS)
        claimed = await session.scalar(
            insert(IdempotencyRecord)
            .values(
                scope=scope,
                idempotency_key=key,
                request_checksum=checksum,
                response_status=102,
                response_payload={},
                state=_IN_PROGRESS,
                claim_token=token,
                lease_expires_at=lease,
            )
            .on_conflict_do_nothing(index_elements=["scope", "idempotency_key"])
            .returning(IdempotencyRecord.id)
        )
        # The claim is visible to peers and this request releases its connection
        # before doing any business work or waiting on another request.
        await session.commit()
        if claimed is not None:
            await _record_claim(session, scope=scope, key=key, token=token)
            return None

        existing = (
            await session.execute(
                select(
                    IdempotencyRecord.id,
                    IdempotencyRecord.request_checksum,
                    IdempotencyRecord.response_status,
                    IdempotencyRecord.response_payload,
                    IdempotencyRecord.state,
                    IdempotencyRecord.lease_expires_at,
                ).where(
                    IdempotencyRecord.scope == scope,
                    IdempotencyRecord.idempotency_key == key,
                )
            )
        ).one_or_none()
        await session.rollback()
        if existing is None:
            continue
        record_id, recorded_checksum, status_code, payload, state, expires_at = existing
        if recorded_checksum != checksum:
            raise APIError(
                "IDEMPOTENCY_KEY_REUSED",
                "This idempotency key was already used with a different request.",
                status_code=409,
                details={"scope": scope},
            )
        if state == _COMPLETED:
            return JSONResponse(payload, status_code=status_code)

        now = datetime.now(UTC)
        if expires_at is None or expires_at <= now:
            recovered = await session.scalar(
                update(IdempotencyRecord)
                .where(
                    IdempotencyRecord.id == record_id,
                    IdempotencyRecord.state == _IN_PROGRESS,
                    or_(
                        IdempotencyRecord.lease_expires_at.is_(None),
                        IdempotencyRecord.lease_expires_at <= now,
                    ),
                )
                .values(claim_token=token, lease_expires_at=lease)
                .returning(IdempotencyRecord.id)
            )
            await session.commit()
            if recovered is not None:
                await _record_claim(session, scope=scope, key=key, token=token)
                return None
        await asyncio.sleep(_POLL_SECONDS)


async def store_response(
    session: AsyncSession,
    *,
    scope: str,
    key: str,
    request_payload: Any,
    response_payload: Any,
    status_code: int = 200,
) -> None:
    scoped = _scope(session, scope)
    claim = _claims(session).get((scoped, key))
    if claim is None:
        raise RuntimeError("Cannot store an idempotent response without owning its claim")
    checksum = _request_checksum(request_payload)
    result = await session.execute(
        update(IdempotencyRecord)
        .where(
            IdempotencyRecord.scope == scoped,
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.request_checksum == checksum,
            IdempotencyRecord.state == _IN_PROGRESS,
            IdempotencyRecord.claim_token == claim.token,
        )
        .values(
            state=_COMPLETED,
            claim_token=None,
            lease_expires_at=None,
            response_status=status_code,
            response_payload=response_payload,
        )
    )
    if result.rowcount != 1:
        await session.rollback()
        raise RuntimeError("The idempotency claim expired before its response was stored")
    # Publish the business changes and replay response in one final transaction.
    await session.commit()
    _claims(session).pop((scoped, key), None)
    await _stop_claim(claim)
