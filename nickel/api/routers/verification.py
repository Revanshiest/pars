"""API-роутер: факты и их верификация (очередь, назначение, версии)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import assert_fact_access, audit_action, check_permission, get_current_user
from services.store import get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


class VerifyRequest(BaseModel):
    status: str = Field(..., pattern="^(verified|rejected|pending|in_review)$")
    notes: str = ""


class AssignFactRequest(BaseModel):
    expert_id: str
    priority: int = Field(default=0, ge=0, le=100)


class ClaimTasksRequest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)


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
