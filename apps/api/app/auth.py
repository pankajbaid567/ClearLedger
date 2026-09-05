"""Configured bearer authentication and explicit loopback synthetic-demo access.

This is deliberately a small single-service access-control scheme, not SSO. Tokens
are generated out of band, never accepted in URLs, and stored only as SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.config import Settings, get_settings
from apps.api.app.errors import APIError

Role = Literal["viewer", "operator", "reviewer", "admin"]
Permission = Literal["read", "create", "review"]
_PERMISSIONS: dict[Role, tuple[Permission, ...]] = {
    "viewer": ("read",),
    "operator": ("read", "create"),
    "reviewer": ("read", "review"),
    "admin": ("read", "create", "review"),
}
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_REVIEW_ACTIONS = {"approve", "reject", "defer", "assign", "tasks"}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    is_demo: bool = False

    @property
    def permissions(self) -> tuple[Permission, ...]:
        return _PERMISSIONS[self.role]


def principal_from_session(session: AsyncSession) -> Principal:
    principal = session.info.get("principal")
    if not isinstance(principal, Principal):
        raise APIError("AUTHENTICATION_REQUIRED", "Authentication is required.", status_code=401)
    return principal


def _required_permission(request: Request) -> Permission:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return "read"
    path = request.url.path.rstrip("/")
    if path.startswith("/api/runs/") and path.endswith("/questions"):
        return "read"
    if "/cases/" in path and path.rsplit("/", 1)[-1] in _REVIEW_ACTIONS:
        return "review"
    return "create"


def get_principal(
    request: Request,
    config: Settings = Depends(get_settings),
) -> Principal:
    if config.app_mode == "local_demo":
        # Host/origin checks supplement loopback socket/Compose bindings. Never use
        # local_demo behind a public reverse proxy or trust X-Forwarded-* for this.
        origin = request.headers.get("origin")
        if request.url.hostname not in _LOOPBACK or (
            origin is not None and urlsplit(origin).hostname not in _LOOPBACK
        ):
            raise APIError(
                "DEMO_LOOPBACK_ONLY",
                "Synthetic demo access is restricted to localhost. Use shared mode for hosting.",
                status_code=403,
            )
        principal = Principal("demo.finance.operator", "admin", is_demo=True)
    else:
        if not config.auth_tokens:
            raise APIError(
                "AUTH_NOT_CONFIGURED",
                "Shared access is disabled until the operator configures authentication.",
                status_code=503,
            )
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not 32 <= len(token) <= 512 or token != token.strip():
            raise APIError(
                "AUTHENTICATION_REQUIRED", "A valid bearer token is required.", status_code=401
            )
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        identity = None
        for candidate in config.auth_tokens:
            if secrets.compare_digest(candidate.token_sha256, digest):
                identity = candidate
        if identity is None:
            raise APIError(
                "AUTHENTICATION_REQUIRED", "A valid bearer token is required.", status_code=401
            )
        principal = Principal(identity.subject, identity.role)
    if _required_permission(request) not in principal.permissions:
        raise APIError(
            "PERMISSION_DENIED", "Your role does not permit this action.", status_code=403
        )
    request.state.principal = principal
    return principal
