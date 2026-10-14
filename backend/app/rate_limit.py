"""A tiny in-memory, per-client-IP sliding-window rate limiter.

Good enough to stop a single client from draining a cloud API key or
saturating the CPU. It is intentionally dependency-free and process-local;
for a multi-worker deployment put a real limiter (e.g. at the proxy) in front.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Only these (expensive) endpoints are limited; health checks and static
# assets are always allowed through.
LIMITED_PATHS = ("/api/explain", "/api/followup")
WINDOW_SECONDS = 60.0


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
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            hits = self._hits[client]
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
