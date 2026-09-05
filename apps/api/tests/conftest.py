"""PostgreSQL-backed API integration fixtures."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import psycopg
import pytest_asyncio
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.app.auth import Principal, get_principal
from apps.api.app.dependencies import get_db_session
from apps.api.app.idempotency import abandon_idempotency_claims
from apps.api.app.main import app
from db.models import Base

TEST_DATABASE_NAME = "clearledger_test"
TEST_DATABASE_URL = (
    f"postgresql+psycopg://clearledger:clearledger@localhost:5432/{TEST_DATABASE_NAME}"
)
ADMIN_DATABASE_URL = "postgresql://clearledger:clearledger@localhost:5432/clearledger"
ROOT = Path(__file__).resolve().parents[3]


def _ensure_test_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE_NAME,)
        ).fetchone()
        if exists is None:
            connection.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    _ensure_test_database()
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def api_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_session(
        principal: Principal = Depends(get_principal),
    ) -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            session.info["principal"] = principal
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await abandon_idempotency_claims(session)

    app.dependency_overrides[get_principal] = lambda: Principal(
        "demo.finance.operator", "admin", True
    )
    app.dependency_overrides[get_db_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def reconciled_run(api_client: httpx.AsyncClient) -> dict[str, str]:
    create = await api_client.post(
        "/api/runs",
        json={},
        headers={"Idempotency-Key": f"create-{uuid.uuid4()}"},
    )
    assert create.status_code == 201, create.text
    run_id = create.json()["id"]
    source_types = (
        "orders",
        "payments",
        "settlements",
        "settlement_components",
        "bank_transactions",
    )
    files = {
        source_type: (
            f"{source_type}.csv",
            (ROOT / "data" / "demo" / f"{source_type}.csv").read_bytes(),
            "text/csv",
        )
        for source_type in source_types
    }
    upload = await api_client.post(
        f"/api/runs/{run_id}/files",
        files=files,
        headers={"Idempotency-Key": f"upload-{uuid.uuid4()}"},
    )
    assert upload.status_code == 200, upload.text
    assert len(upload.json()) == 5

    validation = await api_client.post(
        f"/api/runs/{run_id}/validate",
        headers={"Idempotency-Key": f"validate-{uuid.uuid4()}"},
    )
    assert validation.status_code == 200, validation.text
    assert validation.json()["valid"] is True

    reconciliation = await api_client.post(
        f"/api/runs/{run_id}/reconcile",
        headers={"Idempotency-Key": f"reconcile-{uuid.uuid4()}"},
    )
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["total_cases"] == 75

    evaluation = await api_client.post(
        f"/api/runs/{run_id}/evaluate",
        headers={"Idempotency-Key": f"evaluate-{uuid.uuid4()}"},
    )
    assert evaluation.status_code == 200, evaluation.text
    return {
        "run_id": run_id,
        "result_checksum": reconciliation.json()["result_checksum"],
    }
