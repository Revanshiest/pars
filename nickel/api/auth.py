"""RBAC: API-key, JWT Bearer, SSO headers, document ACL."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, Request

from services.access_control import can_access_level
from services.store import get_store


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    store = get_store()
    user = None

    if authorization and authorization.lower().startswith("bearer "):
        from services.jwt_auth import decode_access_token
        user = decode_access_token(authorization[7:].strip())

    if not user and x_api_key:
        user = store.get_user_by_key(x_api_key)

    if not user and os.getenv("TRUST_SSO_HEADERS", "").lower() == "true":
        sso_email = request.headers.get("x-remote-user") or request.headers.get("x-forwarded-email")
        if sso_email:
            user = store.get_user_by_email(sso_email.strip().lower())

    if not user:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication required: Authorization: Bearer <token>, "
                "X-API-Key, or SSO header (if TRUST_SSO_HEADERS=true)"
            ),
        )
    return user


def check_permission(user: dict, permission: str):
    if not get_store().has_permission(user["role"], permission):
        raise HTTPException(
            status_code=403,
            detail=f"Permission '{permission}' required for role '{user['role']}'",
        )


def require_admin(user: dict):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def assert_fact_access(user: dict, fact: dict):
    if user.get("role") != "external_partner":
        return
    level = get_store().get_document_access(fact.get("source_document") or "")
    if not can_access_level(user["role"], level):
        raise HTTPException(status_code=403, detail="Access denied: internal document")


def apply_search_acl(user: dict, result: dict) -> dict:
    from services.access_control import filter_search_result
    if user.get("role") != "external_partner":
        return result
    doc_access = get_store().get_document_access_map()
    return filter_search_result(result, user["role"], doc_access)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def audit_action(
    user: Optional[dict],
    action: str,
    resource: str = "",
    details: Optional[dict] = None,
    ip: str = "",
    request: Optional[Request] = None,
):
    if request and not ip:
        ip = client_ip(request)
    get_store().audit(user, action, resource, details, ip)
