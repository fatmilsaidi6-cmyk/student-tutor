"""In-memory, per-client rate limiting and daily quota.

Two independent limits are enforced on the expensive AI endpoints:

- a short sliding window (``rate_limit_per_minute``) to stop bursts, and
- a daily quota (``daily_quota``) to cap cost, resetting at UTC midnight.

The bucket key is the signed-in user's email when available, otherwise the
client IP (taken from a proxy header when TRUST_PROXY is set). Both limits are
per-process and in-memory; they reset on restart and are not shared across
replicas, so put a real limiter at the proxy for multi-instance deployments.
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
DAY_SECONDS = 86400  # UTC


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
    def __init__(
        self,
        app,
        limit_per_minute: int = 30,
        daily_quota: int = 0,
    ):
        super().__init__(app)
        self.limit = limit_per_minute
        self.daily_quota = daily_quota
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[str, tuple[int, int]] = {}  # key -> (day_index, count)

    async def dispatch(self, request: Request, call_next):
        limited = (
            request.method == "POST" and request.url.path in LIMITED_PATHS
        )
        if not limited or (self.limit <= 0 and self.daily_quota <= 0):
            return await call_next(request)

        key = _bucket_key(request)
        now = time.monotonic()
        wall = time.time()
        day_index = int(wall // DAY_SECONDS)

        # --- short-window burst limit ---
        if self.limit > 0:
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

        # --- daily quota ---
        if self.daily_quota > 0:
            day, count = self._daily.get(key, (day_index, 0))
            if day != day_index:  # new UTC day -> reset
                count = 0
            if count >= self.daily_quota:
                retry_after = int(DAY_SECONDS - (wall % DAY_SECONDS)) + 1
                return JSONResponse(
                    {
                        "detail": (
                            "Daily limit reached. You can keep going after your "
                            "quota resets tomorrow (UTC)."
                        )
                    },
                    status_code=429,
                    headers={
                        "Retry-After": str(retry_after),
                        "X-Quota-Limit": str(self.daily_quota),
                        "X-Quota-Remaining": "0",
                    },
                )
            self._daily[key] = (day_index, count + 1)

        response = await call_next(request)
        if self.daily_quota > 0:
            remaining = self.daily_quota - self._daily[key][1]
            response.headers["X-Quota-Limit"] = str(self.daily_quota)
            response.headers["X-Quota-Remaining"] = str(max(remaining, 0))
        return response
