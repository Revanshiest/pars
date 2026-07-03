"""Security headers и audit middleware."""

from __future__ import annotations

import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from services.store import get_store

SKIP_AUDIT_PREFIXES = (
    "/health",
    "/admin",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/auth/status",
    "/api/v1/auth/setup",
)

READ_METHODS = {"GET", "HEAD"}


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def _normalize_audit_action(method: str, path: str) -> str:
    path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{id}",
        path,
        flags=re.I,
    )
    path = re.sub(r"/[0-9a-f]{32}", "/{id}", path, flags=re.I)
    kind = "read" if method in READ_METHODS else "write"
    slug = path.strip("/").replace("/", ".") or "root"
    return f"{kind}.{slug}"


def _resolve_user(request: Request) -> Optional[dict]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        from services.jwt_auth import decode_access_token
        user = decode_access_token(auth[7:].strip())
        if user:
            return user
    api_key = request.headers.get("x-api-key")
    if api_key:
        return get_store().get_user_by_key(api_key)
    sso_email = request.headers.get("x-remote-user") or request.headers.get("x-forwarded-email")
    if sso_email and __import__("os").getenv("TRUST_SSO_HEADERS", "").lower() == "true":
        return get_store().get_user_by_email(sso_email.strip().lower())
    return None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if __import__("os").getenv("ENABLE_HSTS", "").lower() == "true":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if any(path.startswith(p) for p in SKIP_AUDIT_PREFIXES):
            return response
        if not path.startswith("/api/"):
            return response
        user = _resolve_user(request)
        if not user:
            return response
        action = _normalize_audit_action(request.method, path)
        get_store().audit(
            user,
            action,
            resource=path,
            details={
                "method": request.method,
                "status": response.status_code,
                "query": str(request.url.query)[:200] if request.url.query else None,
            },
            ip=client_ip(request),
        )
        return response
