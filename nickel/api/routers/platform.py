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


class GlossaryTermCreate(BaseModel):
    canonical: str
    synonyms_ru: List[str] = []
    synonyms_en: List[str] = []
    domain: Optional[str] = None
    definition: Optional[str] = None


class FilteredSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    limit: int = Field(default=10, ge=1, le=50)
    entity_type: Optional[str] = None
    geography: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    verification_status: Optional[str] = None
    job_id: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    year_from: Optional[int] = Field(default=None, ge=1900, le=2100)
    year_to: Optional[int] = Field(default=None, ge=1900, le=2100)
    author: Optional[str] = None
    document_kind: Optional[str] = Field(
        default=None,
        description="patent | regulation | publication | report | experiment_catalog",
    )


class ComparePracticesRequest(BaseModel):
    query: str = Field(..., min_length=3)
    limit: int = Field(default=10, ge=1, le=30)
    min_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    document_kind: Optional[str] = None
    year_from: Optional[int] = Field(default=None, ge=1900, le=2100)
    year_to: Optional[int] = Field(default=None, ge=1900, le=2100)
    author: Optional[str] = None


class VerifyRequest(BaseModel):
    status: str = Field(..., pattern="^(verified|rejected|pending|in_review)$")
    notes: str = ""


class AssignFactRequest(BaseModel):
    expert_id: str
    priority: int = Field(default=0, ge=0, le=100)


class ClaimTasksRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


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


class LitReviewRequest(BaseModel):
    topic: str = Field(..., min_length=3)
    geography: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    use_llm: Optional[bool] = Field(default=None, description="LLM-синтез через Ollama; null=auto")


class OntologyGapRequest(BaseModel):
    query: Optional[str] = Field(default=None, description="Например: холодный климат + HL + Ni")
    material: Optional[str] = None
    process: Optional[str] = None
    climate: Optional[str] = None
    domain: Optional[str] = None


class CompareRequest(BaseModel):
    technologies: List[str] = Field(..., min_length=2, max_length=10)
    parameters: Optional[List[str]] = None


class SubscriptionCreate(BaseModel):
    topic: str
    filters: dict = {}


class ExportRequest(BaseModel):
    topic: str
    format: str = Field(..., pattern="^(md|pdf|jsonld)$")


class NumericSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Например: сульфаты < 200 мг/л")
    limit: int = Field(default=50, ge=1, le=100)
    geography: Optional[str] = None
    verification_status: Optional[str] = None


class GlossaryLookupRequest(BaseModel):
    text: str = Field(..., min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


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


@router.post("/search/numeric")
async def numeric_search(body: NumericSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.numeric_query import search_by_numeric_query
    audit_action(user, "search.numeric", details={"query": body.query})
    return search_by_numeric_query(
        body.query, limit=body.limit,
        geography=body.geography, verification_status=body.verification_status,
    )


@router.post("/glossary/lookup")
async def glossary_semantic_lookup(body: GlossaryLookupRequest, user=Depends(get_current_user)):
    check_permission(user, "glossary_read")
    from services.glossary import GlossaryMatcher, glossary_use_bge, text_glossary_lookup

    matches = []
    if glossary_use_bge():
        try:
            matches = GlossaryMatcher().semantic_lookup(body.text, top_k=body.top_k)
        except Exception:
            matches = []
    if not matches:
        matches = text_glossary_lookup(body.text, top_k=body.top_k)
    return {"text": body.text, "matches": matches}


@router.get("/glossary/expand")
async def glossary_expand(q: str, user=Depends(get_current_user)):
    check_permission(user, "glossary_read")
    from services.glossary import expand_query_with_glossary
    return expand_query_with_glossary(q, use_bge=True)


@router.get("/glossary")
async def list_glossary(
    domain: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user=Depends(get_current_user),
):
    check_permission(user, "glossary_read")
    audit_action(user, "glossary.list", ip="")
    store = get_store()
    terms = store.list_glossary(domain=domain, q=q, limit=limit, offset=offset)
    return {
        "terms": terms,
        "total": store.count_glossary(domain=domain, q=q),
        "limit": limit,
        "offset": offset,
    }


@router.get("/glossary/domains")
async def list_glossary_domains(user=Depends(get_current_user)):
    check_permission(user, "glossary_read")
    return {"domains": get_store().list_glossary_domains()}


@router.post("/glossary")
async def create_glossary_term(body: GlossaryTermCreate, user=Depends(get_current_user)):
    check_permission(user, "glossary_write")
    tid = get_store().add_glossary_term(body.model_dump())
    audit_action(user, "glossary.create", tid, body.model_dump())
    return {"id": tid, **body.model_dump()}


@router.post("/search/filtered")
async def search_filtered(body: FilteredSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    audit_action(user, "search.filtered", details={"query": body.query})
    return await run_search(filtered_search, **body.model_dump(), role=user["role"])


@router.post("/search/compare-practices")
async def search_compare_practices(body: ComparePracticesRequest, user=Depends(get_current_user)):
    check_permission(user, "compare")
    audit_action(user, "search.compare_practices", details={"query": body.query})
    return await run_search(compare_practices, **body.model_dump())


@router.post("/search/hybrid")
async def search_hybrid(body: FilteredSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.hybrid_search import hybrid_ranked_search
    audit_action(user, "search.hybrid", details={"query": body.query})
    try:
        return await run_search(hybrid_ranked_search, **body.model_dump(), role=user["role"])
    except Exception as exc:
        raise HTTPException(503, f"Search unavailable: {exc}") from exc


@router.get("/facts/{fact_id}")
async def get_fact(fact_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    fact = get_store().get_fact(fact_id)
    if not fact:
        raise HTTPException(404, "Fact not found")
    assert_fact_access(user, fact)
    return fact


@router.get("/facts")
async def list_facts(
    status: Optional[str] = None,
    geography: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    return get_store().list_facts(
        status=status, geography=geography, min_confidence=min_confidence,
        limit=limit, role=user["role"],
    )


@router.post("/facts/{fact_id}/verify")
async def verify_fact_endpoint(fact_id: str, body: VerifyRequest, user=Depends(get_current_user)):
    check_permission(user, "verify")
    ok = get_store().verify_fact(fact_id, body.status, user["id"], body.notes)
    if not ok:
        raise HTTPException(404, "Fact not found")
    audit_action(user, "fact.verify", fact_id, {"status": body.status})
    return get_store().get_fact(fact_id)


@router.get("/verification/queue")
async def verification_queue(
    assigned_to: Optional[str] = None,
    unassigned_only: bool = False,
    min_priority: Optional[int] = None,
    limit: int = 50,
    user=Depends(get_current_user),
):
    check_permission(user, "verify")
    return get_store().list_verification_queue(
        assigned_to=assigned_to,
        unassigned_only=unassigned_only,
        min_priority=min_priority,
        limit=limit,
    )


@router.get("/verification/my-queue")
async def my_verification_queue(limit: int = 20, user=Depends(get_current_user)):
    check_permission(user, "verify")
    return get_store().list_verification_queue(assigned_to=user["id"], limit=limit)


@router.post("/verification/claim")
async def claim_verification_tasks(body: ClaimTasksRequest, user=Depends(get_current_user)):
    check_permission(user, "verify")
    claimed = get_store().claim_verification_tasks(user["id"], limit=body.limit)
    audit_action(user, "verification.claim", details={"count": len(claimed)})
    return {"claimed": len(claimed), "items": claimed}


@router.post("/facts/{fact_id}/assign")
async def assign_fact_to_expert(fact_id: str, body: AssignFactRequest, user=Depends(get_current_user)):
    check_permission(user, "verify")
    store = get_store()
    try:
        fact = store.assign_fact(fact_id, body.expert_id, priority=body.priority, assigner_id=user["id"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not fact:
        raise HTTPException(404, "Fact not found or not pending")
    audit_action(user, "verification.assign", fact_id, {"expert_id": body.expert_id, "priority": body.priority})
    return fact


@router.delete("/facts/{fact_id}/assign")
async def unassign_fact(fact_id: str, user=Depends(get_current_user)):
    check_permission(user, "verify")
    if not get_store().unassign_fact(fact_id):
        raise HTTPException(404, "Fact not found or not unassignable")
    audit_action(user, "verification.unassign", fact_id)
    return {"id": fact_id, "assigned_to": None}


@router.get("/facts/{fact_id}/versions")
async def fact_versions(fact_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    store = get_store()
    if not store.get_fact(fact_id):
        raise HTTPException(404, "Fact not found")
    return {"fact_id": fact_id, "versions": store.get_fact_versions(fact_id)}


@router.post("/synthesis/literature-review")
async def literature_review(body: LitReviewRequest, user=Depends(get_current_user)):
    check_permission(user, "synthesis")
    audit_action(user, "synthesis.lit_review", details={"topic": body.topic})
    return generate_literature_review(
        body.topic, body.geography, body.min_confidence, use_llm=body.use_llm
    )


@router.get("/analytics/sources-breakdown")
async def sources_breakdown(topic: Optional[str] = None, user=Depends(get_current_user)):
    check_permission(user, "read")
    from services.verification import aggregate_by_source_type, internal_vs_publication_summary
    store = get_store()
    facts = store.list_facts(limit=500, query=topic) if topic else store.list_facts(limit=500)
    return {
        "topic": topic,
        "by_source_type": aggregate_by_source_type(facts),
        "internal_vs_publication": internal_vs_publication_summary(facts),
    }


@router.get("/analytics/gaps")
async def knowledge_gaps(
    domain: Optional[str] = None,
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    audit_action(user, "analytics.gaps", details={"query": query, "domain": domain})
    return await run_search(
        find_knowledge_gaps,
        domain=domain, query=query, material=material, process=process, climate=climate,
    )


@router.post("/analytics/gaps/ontology")
async def ontology_gaps(body: OntologyGapRequest, user=Depends(get_current_user)):
    check_permission(user, "read")
    audit_action(user, "analytics.gaps.ontology", details=body.model_dump(exclude_none=True))
    return await run_search(find_knowledge_gaps, **body.model_dump(exclude_none=True))


@router.get("/analytics/recommendations")
async def recommendations(topic: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    return generate_recommendations(topic)


@router.post("/analytics/compare")
async def compare(body: CompareRequest, user=Depends(get_current_user)):
    check_permission(user, "compare")
    audit_action(user, "analytics.compare", details={"technologies": body.technologies})
    return await run_search(compare_technologies, body.technologies, body.parameters)


@router.get("/dashboard")
async def dashboard(user=Depends(get_current_user)):
    check_permission(user, "dashboard")
    return get_store().dashboard_metrics()


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
