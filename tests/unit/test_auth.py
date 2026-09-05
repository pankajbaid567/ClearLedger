"""Offline authentication, role and run-ownership boundary tests."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.auth import Principal, get_principal
from apps.api.app.config import Settings, get_settings
from apps.api.app.errors import APIError
from apps.api.app.routes.auth import router as auth_router
from apps.api.app.routes.helpers import require_run
from scripts.create_auth_token import main as create_token
from services.reconciliation.run_service import RunServiceError


def _config(role: str = "admin", subject: str = "alice") -> tuple[Settings, str]:
    token = secrets.token_urlsafe(32)
    return Settings(
        _env_file=None,
        app_mode="shared",
        auth_tokens=[
            {
                "subject": subject,
                "role": role,
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            }
        ],
    ), token


def _app(config: Settings) -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: config
    app.include_router(auth_router)

    @app.exception_handler(APIError)
    async def api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse({"code": exc.code}, status_code=exc.status_code)

    @app.get("/api/runs/probe")
    @app.post("/api/runs")
    @app.post("/api/cases/probe/approve")
    @app.post("/api/runs/run-probe/cases/probe/approve")
    @app.post("/api/runs/run-probe/questions")
    async def protected(principal: Principal = Depends(get_principal)) -> dict[str, str]:
        return {"subject": principal.subject}

    return app


@pytest.mark.asyncio
async def test_shared_default_fails_closed_without_configured_identity() -> None:
    config = Settings(_env_file=None, app_mode="shared")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(config)), base_url="http://localhost"
    ) as client:
        discover = await client.get("/api/auth/config")
        assert discover.json() == {"mode": "shared", "authentication_required": True}
        response = await client.get("/api/runs/probe")
        assert response.status_code == 503
        assert response.json()["code"] == "AUTH_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_token_is_header_only_and_identity_is_server_derived() -> None:
    config, token = _config(subject="alice")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(config)), base_url="http://localhost"
    ) as client:
        assert (await client.get("/api/auth/me")).status_code == 401
        assert (await client.get("/api/auth/me", params={"token": token})).status_code == 401
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {
            "subject": "alice",
            "role": "admin",
            "is_demo": False,
            "permissions": ["read", "create", "review"],
        }
        spoof = await client.post(
            "/api/cases/probe/approve",
            json={"actor": "someone-else"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert spoof.json()["subject"] == "alice"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "create_status", "review_status"),
    [("viewer", 403, 403), ("operator", 200, 403), ("reviewer", 403, 200), ("admin", 200, 200)],
)
async def test_role_matrix(role: str, create_status: int, review_status: int) -> None:
    config, token = _config(role)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(config)),
        base_url="http://localhost",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        assert (await client.get("/api/runs/probe")).status_code == 200
        assert (await client.post("/api/runs/run-probe/questions")).status_code == 200
        assert (await client.post("/api/runs")).status_code == create_status
        assert (await client.post("/api/cases/probe/approve")).status_code == review_status
        assert (
            await client.post("/api/runs/run-probe/cases/probe/approve")
        ).status_code == review_status


@pytest.mark.asyncio
async def test_demo_requires_explicit_mode_and_loopback_host_origin() -> None:
    config = Settings(_env_file=None, app_mode="local_demo")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(config)), base_url="http://localhost"
    ) as client:
        response = await client.get("/api/auth/me")
        assert response.json()["is_demo"] is True
        assert response.json()["subject"] == "demo.finance.operator"
        assert (
            await client.get("/api/auth/me", headers={"Host": "public.example"})
        ).status_code == 403
        assert (
            await client.get("/api/auth/me", headers={"Origin": "https://evil.example"})
        ).status_code == 403
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_mode="local_demo", web_origin="https://public.example")


@pytest.mark.asyncio
async def test_run_lookup_denies_other_subject_even_for_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = uuid.uuid4()
    run = SimpleNamespace(id=run_id, owner_subject="alice")
    monkeypatch.setattr(
        "apps.api.app.routes.helpers.RunRepository",
        lambda _: SimpleNamespace(get=AsyncMock(return_value=run)),
    )
    async with AsyncSession() as session:
        session.info["principal"] = Principal("alice", "viewer")
        assert await require_run(session, run_id) is run
        session.info["principal"] = Principal("bob", "admin")
        with pytest.raises(RunServiceError) as error:
            await require_run(session, run_id)
        assert error.value.status_code == 404
        assert error.value.code == "RUN_NOT_FOUND"
        # Legacy ownerless records are inaccessible in shared mode as well.
        run.owner_subject = None
        with pytest.raises(RunServiceError):
            await require_run(session, run_id)


def test_duplicate_token_identity_is_rejected_and_keys_are_redacted() -> None:
    config, _ = _config()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_tokens=[config.auth_tokens[0], config.auth_tokens[0]])
    assert config.auth_tokens[0].token_sha256 not in repr(config)
    secret = secrets.token_urlsafe(32)
    private = Settings(_env_file=None, ai_api_key=secret)
    assert secret not in repr(private)
    assert secret not in private.model_dump_json()


def test_token_generation_is_private_and_does_not_log_or_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["create-token", "--subject", "alice", "--role", "admin", "--output-dir", str(tmp_path)],
    )
    create_token()
    token_path = tmp_path / "access.bearer-token"
    token = token_path.read_text().strip()
    identity_path = tmp_path / "auth-tokens.json"
    identity = json.loads(identity_path.read_text())[0]
    assert len(token) >= 32
    assert identity["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in capsys.readouterr().out
    assert token_path.stat().st_mode & 0o777 == 0o600
    assert identity_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        create_token()
    assert token_path.read_text().strip() == token


@pytest.mark.asyncio
async def test_real_application_protects_run_case_cash_and_export_routes() -> None:
    from apps.api.app.main import app

    config, _ = _config()
    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.pop(get_principal, None)
    app.dependency_overrides[get_settings] = lambda: config
    run_id = uuid.uuid4()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            for path in (
                f"/api/runs/{run_id}",
                f"/api/runs/{run_id}/cash-position",
                f"/api/runs/{run_id}/exports/audit.json",
                f"/api/runs/{run_id}/cases/CASE_0001/evidence",
            ):
                response = await client.get(path)
                assert response.status_code == 401, (path, response.text)
            for path in (
                "/api/runs",
                f"/api/runs/{run_id}/cases/CASE_0001/approve",
            ):
                response = await client.post(path, json={})
                assert response.status_code == 401, (path, response.text)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved_overrides)
