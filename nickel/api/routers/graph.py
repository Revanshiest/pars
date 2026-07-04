"""API-роутер: граф знаний (просмотр, HTML, правка троек, синхронизация, история)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from api.auth import audit_action, check_permission, get_current_user
from services.graph_editor import add_triple, delete_triple, list_edits, update_triple

router = APIRouter(prefix="/api/v1", tags=["platform"])


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
