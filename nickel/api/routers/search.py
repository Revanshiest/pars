"""API-роутер: поиск (numeric, filtered, compare-practices, hybrid)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import audit_action, check_permission, get_current_user
from services.logging_config import get_logger
from services.user_messages import Msg

logger = get_logger(__name__)
from services.search_filters import compare_practices, filtered_search
from services.search_runtime import run_search

router = APIRouter(prefix="/api/v1", tags=["platform"])


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


class NumericSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Например: сульфаты < 200 мг/л")
    limit: int = Field(default=50, ge=1, le=100)
    geography: Optional[str] = None
    verification_status: Optional[str] = None


@router.post("/search/numeric")
async def numeric_search(body: NumericSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.numeric_query import search_by_numeric_query
    audit_action(user, "search.numeric", details={"query": body.query})
    return search_by_numeric_query(
        body.query, limit=body.limit,
        geography=body.geography, verification_status=body.verification_status,
    )


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
        logger.warning("Hybrid search failed: %s", exc)
        raise HTTPException(503, Msg.SEARCH_UNAVAILABLE) from exc


@router.get("/search/examples")
async def search_examples_endpoint(user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.search_examples_builder import graph_search_examples
    return {"examples": graph_search_examples()}
