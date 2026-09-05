"""Public access-mode discovery and authenticated identity introspection."""

from fastapi import APIRouter, Depends, Response

from apps.api.app.auth import Principal, get_principal
from apps.api.app.config import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.get("/config")
async def access_configuration(
    response: Response, config: Settings = Depends(get_settings)
) -> dict[str, str | bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"mode": config.app_mode, "authentication_required": config.app_mode == "shared"}


@router.get("/me")
async def current_identity(
    response: Response, principal: Principal = Depends(get_principal)
) -> dict[str, str | bool | list[str]]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "subject": principal.subject,
        "role": principal.role,
        "is_demo": principal.is_demo,
        "permissions": list(principal.permissions),
    }
