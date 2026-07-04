"""API: глоссарий, верификация, аналитика, экспорт, RBAC, уведомления, правка графа."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import apply_search_acl, audit_action, assert_fact_access, check_permission, get_current_user
from services.analytics import (
    compare_technologies,
    find_knowledge_gaps,
    generate_literature_review,
    generate_recommendations,
)
from services.export_service import export_jsonld, export_markdown, export_pdf, save_export
from services.graph_editor import add_triple, delete_triple, list_edits, update_triple
from services.search_filters import compare_practices, filtered_search
from services.search_runtime import run_search
from services.auth_bootstrap import assignable_roles, env_admin_spec, is_env_admin_email
from services.store import ROLE_PERMISSIONS, get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


class TokenRequest(BaseModel):
    api_key: str = Field(..., min_length=16)


class DocumentAccessUpdate(BaseModel):
    access_level: str = Field(..., pattern="^(internal|partner|public)$")


class UserCreate(BaseModel):
    email: str = Field(..., min_length=5)
    name: str = Field(..., min_length=1)
    role: str = Field(default="researcher")
    api_key: Optional[str] = Field(default=None, min_length=16)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class FirstAdminSetup(BaseModel):
    email: str = Field(..., min_length=5)
    name: str = Field(..., min_length=1)
    api_key: Optional[str] = Field(default=None, min_length=16)


@router.get("/audit")
async def audit_log(limit: int = 100, user=Depends(get_current_user)):
    check_permission(user, "audit")
    return get_store().audit_log_list(limit)


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


@router.patch("/documents/{source_document}/access")
async def update_document_access(
    source_document: str,
    body: DocumentAccessUpdate,
    user=Depends(get_current_user),
):
    from api.auth import require_admin
    require_admin(user)
    store = get_store()
    try:
        ok = store.set_document_access(source_document, body.access_level)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "Document not found")
    audit_action(user, "admin.document_access", source_document, {"access_level": body.access_level})
    return {"source_document": source_document, "access_level": body.access_level}


@router.get("/documents")
async def list_documents(
    document_kind: Optional[str] = None,
    access_level: Optional[str] = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    from services.access_control import allowed_levels
    docs = get_store().list_documents(document_kind=document_kind, limit=limit)
    if user.get("role") == "external_partner":
        levels = allowed_levels(user["role"])
        docs = [d for d in docs if (d.get("access_level") or "internal") in levels]
    if access_level:
        docs = [d for d in docs if d.get("access_level") == access_level]
    return {"documents": docs}


@router.get("/admin/roles")
async def admin_list_roles(user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    roles = assignable_roles()
    return {"roles": [{"role": r, "permissions": ROLE_PERMISSIONS[r]} for r in roles]}


@router.get("/admin/users")
async def admin_list_users(user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    audit_action(user, "admin.list_users")
    return {"users": get_store().list_users_detailed()}


@router.post("/admin/users")
async def admin_create_user(body: UserCreate, user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    if body.role == "admin":
        raise HTTPException(403, "Admin role is only via AUTH_ADMIN in .env")
    if body.role not in assignable_roles():
        raise HTTPException(400, f"Invalid role: {body.role}")
    store = get_store()
    try:
        created = store.create_user(body.email, body.name, body.role, api_key=body.api_key)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit_action(user, "admin.create_user", created["id"], {"email": body.email, "role": body.role})
    return {
        "user": {k: v for k, v in created.items() if k != "api_key"},
        "api_key": created["api_key"],
    }


@router.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: UserUpdate, user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    store = get_store()
    target = store.get_user(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if is_env_admin_email(target["email"]):
        if body.role and body.role != "admin":
            raise HTTPException(403, "Cannot change env admin role")
        if body.email and body.email.strip().lower() != target["email"]:
            raise HTTPException(403, "Cannot change env admin email")
    if body.role == "admin" and env_admin_spec():
        raise HTTPException(403, "Admin role is only via AUTH_ADMIN in .env")
    try:
        updated = store.update_user(
            user_id,
            name=body.name,
            role=body.role,
            email=body.email,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not updated:
        raise HTTPException(404, "User not found")
    audit_action(user, "admin.update_user", user_id, body.model_dump(exclude_none=True))
    return updated


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    if user_id == user["id"]:
        raise HTTPException(400, "Cannot delete your own account")
    store = get_store()
    target = store.get_user(user_id)
    if target and is_env_admin_email(target["email"]):
        raise HTTPException(403, "Cannot delete env admin")
    try:
        ok = store.delete_user(user_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not ok:
        raise HTTPException(404, "User not found")
    audit_action(user, "admin.delete_user", user_id)
    return {"deleted": user_id}


@router.post("/admin/users/{user_id}/rotate-key")
async def admin_rotate_key(user_id: str, user=Depends(get_current_user)):
    from api.auth import require_admin
    require_admin(user)
    store = get_store()
    target = store.get_user(user_id)
    if target and is_env_admin_email(target["email"]):
        raise HTTPException(403, "Env admin API key is synced from AUTH_ADMIN on restart")
    new_key = store.rotate_api_key(user_id)
    if not new_key:
        raise HTTPException(404, "User not found")
    audit_action(user, "admin.rotate_key", user_id)
    return {"user_id": user_id, "api_key": new_key}
