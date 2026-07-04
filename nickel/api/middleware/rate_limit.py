"""Простой in-memory rate limiter для дорогих эндпоинтов."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable, Dict, List, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Лимит запросов по IP + path (скользящее окно)."""

    LIMITED_PREFIXES = (
        "/api/v1/auth/token",
        "/api/v1/documents/upload",
        "/api/v1/search/agent",
    )

    def __init__(self, app, requests: int = 30, window_sec: int = 60):
        super().__init__(app)
        self.requests = int(os.getenv("RATE_LIMIT_REQUESTS", str(requests)))
        self.window = int(os.getenv("RATE_LIMIT_WINDOW_SEC", str(window_sec)))
        self._hits: Dict[str, List[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _allow(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window
        hits = [t for t in self._hits[key] if t > window_start]
        if len(hits) >= self.requests:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        if not any(path.startswith(p) for p in self.LIMITED_PREFIXES):
            return await call_next(request)
        key = f"{self._client_ip(request)}:{path}"
        if not self._allow(key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Слишком много запросов. Подождите минуту и попробуйте снова."},
            )
        return await call_next(request)
