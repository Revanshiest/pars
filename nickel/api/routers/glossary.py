"""API-роутер: глоссарий (поиск, разворачивание запроса, список, создание)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.auth import audit_action, check_permission, get_current_user
from services.store import get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


class GlossaryTermCreate(BaseModel):
    canonical: str
    synonyms_ru: List[str] = []
    synonyms_en: List[str] = []
    domain: Optional[str] = None
    definition: Optional[str] = None


class GlossaryLookupRequest(BaseModel):
    text: str = Field(..., min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


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
