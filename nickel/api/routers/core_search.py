"""API-роутер: базовый поиск — semantic (Qdrant), graph (Neo4j), agent (LLM).

Без тегов/префикса — пути сохранены как были в main."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth import apply_search_acl, audit_action, check_permission, get_current_user
from api.models import (
    AgentQueryRequest,
    AgentQueryResponse,
    GraphQueryRequest,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from api.runtime import search_agent
from services.logging_config import get_logger
from services.neo4j_loader import Neo4jLoader
from services.user_messages import Msg

logger = get_logger(__name__)

router = APIRouter()


@router.post("/api/v1/search/semantic", response_model=SemanticSearchResponse)
async def semantic_search(req: SemanticSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_vector"):
        raise HTTPException(503, Msg.VECTOR_SEARCH_DOWN)
    audit_action(user, "search.semantic", details={"query": req.query})
    from services.search_filters import filtered_search
    from services.search_runtime import run_search
    result = await run_search(
        filtered_search,
        req.query, limit=req.limit, entity_type=req.entity_type, job_id=req.job_id,
        role=user["role"],
    )
    result = apply_search_acl(user, result)
    return SemanticSearchResponse(
        query=req.query, chunks=result["chunks"], entities=result["entities"]
    )


@router.post("/api/v1/search/graph")
async def graph_search(req: GraphQueryRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_graph"):
        raise HTTPException(503, Msg.GRAPH_SEARCH_DOWN)
    audit_action(user, "search.graph", details={"entity": req.entity_name}, request=None)
    if user.get("role") == "external_partner":
        raise HTTPException(403, Msg.GRAPH_PARTNER_FORBIDDEN)
    with Neo4jLoader() as loader:
        neighbors = loader.search_neighbors(req.entity_name, depth=req.depth)
    return {"entity": req.entity_name, "neighbors": neighbors}


@router.post("/api/v1/search/agent", response_model=AgentQueryResponse)
async def agent_search(req: AgentQueryRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    audit_action(user, "search.agent", details={"question": req.question})

    role = user.get("role")
    try:
        result = await search_agent.query(req.question, max_iterations=req.max_iterations, role=role)
    except RuntimeError as exc:
        logger.warning("Agent runtime error: %s", exc)
        raise HTTPException(503, Msg.AGENT_UNAVAILABLE) from exc
    except Exception as exc:
        logger.exception("Agent search failed")
        raise HTTPException(503, Msg.AGENT_UNAVAILABLE) from exc
    result = apply_search_acl(user, result)
    return AgentQueryResponse(**result)
