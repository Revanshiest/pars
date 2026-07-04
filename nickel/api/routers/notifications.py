"""API-роутер: уведомления и подписки."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import check_permission, get_current_user
from services.store import get_store

router = APIRouter(prefix="/api/v1", tags=["platform"])


class SubscriptionCreate(BaseModel):
    topic: str
    filters: dict = {}


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
    check_permission(user, "subscribe")
    return get_store().list_subscriptions(user["id"])


@router.delete("/subscriptions/{subscription_id}")
async def remove_sub(subscription_id: str, user=Depends(get_current_user)):
    check_permission(user, "subscribe")
    if not get_store().remove_subscription(subscription_id, user["id"]):
        raise HTTPException(404, "Subscription not found")
    return {"deleted": subscription_id}
