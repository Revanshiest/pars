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


class TripleCreate(BaseModel):
    subject: str
    subject_type: str
    relation: str
    object: str
    object_type: str
    properties: dict = {}
    confidence: Optional[float] = None
    geography: Optional[str] = None
    comment: str = ""


class TripleUpdate(BaseModel):
    subject: Optional[str] = None
    object: Optional[str] = None
    relation: Optional[str] = None
    properties: Optional[dict] = None
    confidence: Optional[float] = None
    geography: Optional[str] = None
    verification_status: Optional[str] = None
    notes: Optional[str] = None
    comment: str = ""


class SubscriptionCreate(BaseModel):
    topic: str
    filters: dict = {}


class ExportRequest(BaseModel):
    topic: str
    format: str = Field(..., pattern="^(md|pdf|jsonld)$")


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


@router.post("/export")
async def export_report(body: ExportRequest, user=Depends(get_current_user)):
    check_permission(user, "export")
    audit_action(user, "export", body.format, {"topic": body.topic})
    path = save_export(body.topic, body.format)
    if body.format == "md":
        return {"format": "md", "content": export_markdown(body.topic), "path": str(path)}
    if body.format == "jsonld":
        return {"format": "jsonld", "content": export_jsonld(body.topic), "path": str(path)}
    return {"format": "pdf", "path": str(path), "size_bytes": path.stat().st_size}


@router.get("/export/{topic}/download")
async def download_export(topic: str, format: str = "md", user=Depends(get_current_user)):
    check_permission(user, "export")
    if format == "pdf":
        content = export_pdf(topic)
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{topic}.pdf"'})
    if format == "jsonld":
        return Response(export_jsonld(topic), media_type="application/ld+json")
    return Response(export_markdown(topic), media_type="text/markdown")


@router.get("/graph/view")
async def graph_view(
    limit: int = 0,
    full: bool = False,
    entity_name: Optional[str] = None,
    source_document: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Данные графа из SQLite для HTML-визуализации во frontend (без Neo4j Browser)."""
    check_permission(user, "read")
    from services.graph_view import load_graph_view

    audit_action(user, "graph.view", details={"entity": entity_name, "source": source_document, "full": full})
    return load_graph_view(
        entity_name=entity_name,
        source_document=source_document,
        limit=limit if limit > 0 else 0,
        role=user.get("role"),
        full=full,
    )


@router.get("/graph/html")
async def graph_html(
    source_document: Optional[str] = None,
    entity_name: Optional[str] = None,
    limit: int = 500,
    user=Depends(get_current_user),
):
    """Полноэкранный интерактивный HTML-граф (PyVis) из SQLite."""
    check_permission(user, "read")
    from services.graph_view import load_graph_view, view_to_triples
    from services.html_visualizer import render_triples_html

    view = load_graph_view(
        entity_name=entity_name,
        source_document=source_document,
        limit=min(max(limit, 1), 500),
        role=user.get("role"),
    )
    triples = view_to_triples(view)
    title = entity_name or source_document or "Nickel Knowledge Graph"
    html = render_triples_html(triples, title=title)
    audit_action(user, "graph.html", details={"source": source_document, "entity": entity_name, "triples": len(triples)})
    return Response(html, media_type="text/html; charset=utf-8")


@router.post("/graph/triples")
async def create_triple(body: TripleCreate, user=Depends(get_current_user)):
    check_permission(user, "edit_graph")
    triple = add_triple(body.model_dump(exclude={"comment"}), user["id"], body.comment)
    audit_action(user, "graph.add", details=triple)
    return triple


@router.patch("/graph/triples/{fact_id}")
async def patch_triple(fact_id: str, body: TripleUpdate, user=Depends(get_current_user)):
    check_permission(user, "edit_graph")
    result = update_triple(fact_id, body.model_dump(exclude_none=True), user["id"], body.comment)
    if not result:
        raise HTTPException(404, "Fact not found")
    audit_action(user, "graph.update", fact_id)
    return result


@router.delete("/graph/triples/{fact_id}")
async def remove_triple(fact_id: str, comment: str = "", user=Depends(get_current_user)):
    check_permission(user, "edit_graph")
    if not delete_triple(fact_id, user["id"], comment):
        raise HTTPException(404, "Fact not found")
    audit_action(user, "graph.delete", fact_id)
    return {"deleted": fact_id}


@router.post("/graph/sync")
async def sync_graph_from_store(user=Depends(get_current_user)):
    """Синхронизация фактов SQLite → Neo4j (после сбоя загрузки)."""
    check_permission(user, "edit_graph")
    from services.neo4j_loader import Neo4jLoader

    audit_action(user, "graph.sync", details={})
    with Neo4jLoader() as loader:
        result = loader.sync_from_store()
    return result


@router.get("/graph/edits")
async def graph_edit_history(limit: int = 50, user=Depends(get_current_user)):
    check_permission(user, "read")
    return list_edits(limit)


@router.get("/notifications")
async def notifications(unread_only: bool = False, user=Depends(get_current_user)):
    check_permission(user, "read")
    return get_store().list_notifications(user["id"], unread_only)


@router.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user=Depends(get_current_user)):
    get_store().mark_notification_read(notification_id, user["id"])
    return {"read": notification_id}


@router.post("/subscriptions")
async def subscribe(body: SubscriptionCreate, user=Depends(get_current_user)):
    check_permission(user, "subscribe")
    sid = get_store().add_subscription(user["id"], body.topic, body.filters)
    return {"id": sid, "topic": body.topic}


@router.get("/subscriptions")
async def list_subs(user=Depends(get_current_user)):
    return get_store().list_subscriptions(user["id"])


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
