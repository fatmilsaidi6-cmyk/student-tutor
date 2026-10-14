"""A tiny in-memory, per-client sliding-window rate limiter.

The bucket key is the signed-in user's email when available, otherwise the
client IP (taken from a proxy header when TRUST_PROXY is set). It is
intentionally dependency-free and process-local; for a multi-worker deployment
put a real limiter (e.g. at the proxy) in front.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings

# Only these (expensive) endpoints are limited; health checks and static
# assets are always allowed through.
LIMITED_PATHS = ("/api/explain", "/api/followup")
WINDOW_SECONDS = 60.0


def client_ip(request: Request) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        fly = request.headers.get("fly-client-ip")
        if fly:
            return fly
    return request.client.host if request.client else "unknown"


def _bucket_key(request: Request) -> str:
    session = request.scope.get("session") or {}
    user = session.get("user")
    if user and user.get("email"):
        return f"user:{user['email']}"
    return f"ip:{client_ip(request)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int = 30):
        super().__init__(app)
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if (
            self.limit > 0
            and request.method == "POST"
            and request.url.path in LIMITED_PATHS
        ):
            key = _bucket_key(request)
            now = time.monotonic()
            hits = self._hits[key]
            while hits and now - hits[0] > WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = int(WINDOW_SECONDS - (now - hits[0])) + 1
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a moment and try again."},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
        return await call_next(request)
