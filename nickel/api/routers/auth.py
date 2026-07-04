"""API-роутер: аутентификация (статус, первичная настройка, токен, профиль)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import audit_action, get_current_user
from services.auth_bootstrap import env_admin_spec
from services.store import get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


class TokenRequest(BaseModel):
    api_key: str = Field(..., min_length=16)


class FirstAdminSetup(BaseModel):
    email: str = Field(..., min_length=5)
    name: str = Field(..., min_length=1)
    api_key: Optional[str] = Field(default=None, min_length=16)


@router.get("/auth/status")
async def auth_status():
    return get_store().auth_status()


@router.post("/auth/setup")
async def auth_setup(body: FirstAdminSetup):
    if env_admin_spec():
        raise HTTPException(403, "Admin is configured via AUTH_ADMIN in .env")
    store = get_store()
    if store.count_users() > 0:
        raise HTTPException(403, "Setup already completed. Use /admin to manage users.")
    try:
        created = store.create_user(body.email, body.name, "admin", api_key=body.api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "message": "First admin created. Save the API key — it will not be shown again.",
        "user": {k: v for k, v in created.items() if k != "api_key"},
        "api_key": created["api_key"],
    }


@router.post("/auth/token")
async def auth_token(body: TokenRequest):
    store = get_store()
    user = store.get_user_by_key(body.api_key)
    if not user:
        raise HTTPException(401, "Invalid or expired API key")
    try:
        from services.jwt_auth import create_access_token
        token = create_access_token(user)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    audit_action(user, "auth.token", details={"method": "api_key_exchange"})
    return token


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user
