"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.auth import Principal, get_principal
from apps.api.app.config import Settings, get_settings
from apps.api.app.errors import APIError
from db.session import get_session_factory
from services.reconciliation.run_service import RunService


async def get_db_session(
    principal: Principal = Depends(get_principal),
) -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        session.info["principal"] = principal
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            from apps.api.app.idempotency import abandon_idempotency_claims

            await abandon_idempotency_claims(session)


def get_run_service(
    session: AsyncSession = Depends(get_db_session),
    config: Settings = Depends(get_settings),
    principal: Principal = Depends(get_principal),
) -> RunService:
    return RunService(
        session,
        upload_dir=config.upload_dir,
        policy_path=config.default_policy_path,
        max_upload_bytes=config.max_upload_bytes,
        ai_config=config.ai_client_config(),
        owner_subject=principal.subject,
    )


def require_ai(config: Settings = Depends(get_settings)) -> Settings:
    if not config.ai_enabled:
        raise APIError(
            "AI_DISABLED",
            "AI analysis is disabled. Set AI_ENABLED=true and configure a provider to enable it.",
            status_code=501,
        )
    return config
