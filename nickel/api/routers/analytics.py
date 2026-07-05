"""API-роутер: синтез, аналитика (пробелы, рекомендации, сравнение), дашборд."""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import audit_action, check_permission, get_current_user
from services.analytics import (
    compare_technologies,
    find_knowledge_gaps,
    generate_literature_review,
    generate_recommendations,
)
from services.gap_analysis import iter_ontology_gaps
from services.search_runtime import run_search
from services.store import get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


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
    auto: bool = Field(default=False, description="Авто-обнаружение пробелов из графа")


class CompareRequest(BaseModel):
    technologies: List[str] = Field(..., min_length=2, max_length=10)
    parameters: Optional[List[str]] = None


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
    auto: bool = True,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    audit_action(user, "analytics.gaps", details={"query": query, "domain": domain, "auto": auto})
    return await run_search(
        find_knowledge_gaps,
        domain=domain, query=query, material=material, process=process, climate=climate,
        auto=auto,
    )


@router.get("/analytics/gaps/stream")
async def knowledge_gaps_stream(
    domain: Optional[str] = None,
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    auto: bool = True,
    user=Depends(get_current_user),
):
    """NDJSON-поток: пробелы появляются по мере анализа сценариев."""
    check_permission(user, "read")
    audit_action(user, "analytics.gaps.stream", details={"query": query, "domain": domain, "auto": auto})

    def event_stream():
        try:
            for event in iter_ontology_gaps(
                query=query,
                material=material,
                process=process,
                climate=climate,
                domain=domain,
                auto=auto,
            ):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@router.post("/analytics/gaps/stream")
async def knowledge_gaps_stream_post(body: OntologyGapRequest, user=Depends(get_current_user)):
    check_permission(user, "read")
    audit_action(user, "analytics.gaps.stream", details=body.model_dump(exclude_none=True))

    def event_stream():
        try:
            for event in iter_ontology_gaps(**body.model_dump(exclude_none=True)):
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


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
