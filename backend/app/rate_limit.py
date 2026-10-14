"""Per-client rate limiting and daily quota for the AI endpoints.

Two independent limits are enforced on the expensive AI endpoints:

- a short sliding window (``rate_limit_per_minute``) to stop bursts, and
- a daily quota (``daily_quota``) to cap cost, resetting at UTC midnight.

The bucket key is the signed-in user's email when available, otherwise the
client IP (taken from a proxy header when TRUST_PROXY is set).

Counters live in one of two pluggable stores:

- :class:`MemoryLimiter` (default) - in-process; resets on restart and is not
  shared across replicas.
- :class:`SqliteLimiter` - used when ``LIMITS_DB`` points at a file; persists
  across restarts. It is still single-writer, so pin the deployment to a single
  instance (see ``fly.toml``) or use one store per instance.

For true horizontal scaling, replace the store with a shared backend (e.g.
Redis) behind the same :meth:`BaseLimiter.check` interface.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings

# Only these (expensive) endpoints are limited; health checks and static
# assets are always allowed through.
LIMITED_PATHS = ("/api/explain", "/api/followup")
WINDOW_SECONDS = 60.0
DAY_SECONDS = 86400  # UTC

RATE_MESSAGE = "Too many requests. Please wait a moment and try again."
QUOTA_MESSAGE = (
    "Daily limit reached. You can keep going after your quota resets tomorrow (UTC)."
)


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


@dataclass
class LimitResult:
    """Outcome of a limit check: whether the request may proceed."""

    allowed: bool
    retry_after: int = 0
    message: str = ""
    quota_limit: int = 0
    quota_remaining: int = 0


class BaseLimiter:
    async def check(
        self, key: str, *, limit: int, quota: int, now: float, wall: float
    ) -> LimitResult:  # pragma: no cover - interface
        raise NotImplementedError


class MemoryLimiter(BaseLimiter):
    """In-process store. Fresh state per instance; not persisted."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[str, tuple[int, int]] = {}  # key -> (day_index, count)

    async def check(
        self, key: str, *, limit: int, quota: int, now: float, wall: float
    ) -> LimitResult:
        if limit > 0:
            hits = self._hits[key]
            while hits and now - hits[0] > WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(WINDOW_SECONDS - (now - hits[0])) + 1
                return LimitResult(False, retry, RATE_MESSAGE)
            hits.append(now)

        if quota > 0:
            day_index = int(wall // DAY_SECONDS)
            day, count = self._daily.get(key, (day_index, 0))
            if day != day_index:  # new UTC day -> reset
                count = 0
            if count >= quota:
                retry = int(DAY_SECONDS - (wall % DAY_SECONDS)) + 1
                return LimitResult(False, retry, QUOTA_MESSAGE, quota, 0)
            self._daily[key] = (day_index, count + 1)
            return LimitResult(True, quota_limit=quota, quota_remaining=quota - count - 1)

        return LimitResult(True)


class SqliteLimiter(BaseLimiter):
    """SQLite-backed store so counters survive process restarts.

    Single-writer by design; serialize with an asyncio lock and run the blocking
    sqlite calls in a worker thread so the event loop stays responsive.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS minute_hits (key TEXT NOT NULL, ts REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_minute_hits ON minute_hits (key, ts)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS daily_counts "
            "(key TEXT PRIMARY KEY, day INTEGER NOT NULL, count INTEGER NOT NULL)"
        )
        self._conn.commit()

    def _check_sync(
        self, key: str, limit: int, quota: int, now: float, wall: float
    ) -> LimitResult:
        conn = self._conn
        conn.execute(
            "DELETE FROM minute_hits WHERE key = ? AND ts <= ?",
            (key, now - WINDOW_SECONDS),
        )

        if limit > 0:
            count, oldest = conn.execute(
                "SELECT COUNT(*), MIN(ts) FROM minute_hits WHERE key = ?", (key,)
            ).fetchone()
            if count >= limit:
                conn.commit()
                retry = int(WINDOW_SECONDS - (now - oldest)) + 1
                return LimitResult(False, retry, RATE_MESSAGE)
            conn.execute(
                "INSERT INTO minute_hits (key, ts) VALUES (?, ?)", (key, now)
            )

        if quota > 0:
            day_index = int(wall // DAY_SECONDS)
            row = conn.execute(
                "SELECT day, count FROM daily_counts WHERE key = ?", (key,)
            ).fetchone()
            day, count = (row[0], row[1]) if row else (day_index, 0)
            if day != day_index:  # new UTC day -> reset
                count = 0
            if count >= quota:
                conn.commit()
                retry = int(DAY_SECONDS - (wall % DAY_SECONDS)) + 1
                return LimitResult(False, retry, QUOTA_MESSAGE, quota, 0)
            count += 1
            conn.execute(
                "INSERT INTO daily_counts (key, day, count) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET day = excluded.day, "
                "count = excluded.count",
                (key, day_index, count),
            )
            conn.commit()
            return LimitResult(True, quota_limit=quota, quota_remaining=quota - count)

        conn.commit()
        return LimitResult(True)

    async def check(
        self, key: str, *, limit: int, quota: int, now: float, wall: float
    ) -> LimitResult:
        async with self._lock:
            return await asyncio.to_thread(
                self._check_sync, key, limit, quota, now, wall
            )


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        limit_per_minute: int = 30,
        daily_quota: int = 0,
        store_path: str | None = None,
    ):
        super().__init__(app)
        self.limit = limit_per_minute
        self.daily_quota = daily_quota
        self.limiter: BaseLimiter = (
            SqliteLimiter(store_path) if store_path else MemoryLimiter()
        )

    async def dispatch(self, request: Request, call_next):
        limited = request.method == "POST" and request.url.path in LIMITED_PATHS
        if not limited or (self.limit <= 0 and self.daily_quota <= 0):
            return await call_next(request)

        key = _bucket_key(request)
        result = await self.limiter.check(
            key,
            limit=self.limit,
            quota=self.daily_quota,
            now=time.monotonic(),
            wall=time.time(),
        )

        if not result.allowed:
            headers = {"Retry-After": str(result.retry_after)}
            if result.quota_limit > 0:
                headers["X-Quota-Limit"] = str(result.quota_limit)
                headers["X-Quota-Remaining"] = "0"
            return JSONResponse(
                {"detail": result.message}, status_code=429, headers=headers
            )

        response = await call_next(request)
        if result.quota_limit > 0:
            response.headers["X-Quota-Limit"] = str(result.quota_limit)
            response.headers["X-Quota-Remaining"] = str(result.quota_remaining)
        return response
