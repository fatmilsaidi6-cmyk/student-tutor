from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import rate_limit
from app.config import settings
from app.rate_limit import RateLimitMiddleware, client_ip


def _request(session=None, headers=None):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/explain",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("1.2.3.4", 1234),
        "session": session or {},
    }
    return Request(scope)


def test_client_ip_uses_socket_by_default():
    assert client_ip(_request()) == "1.2.3.4"


def test_client_ip_trusts_forwarded_header(monkeypatch):
    monkeypatch.setattr(rate_limit, "settings", replace(settings, trust_proxy=True))
    assert client_ip(_request(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})) == "9.9.9.9"
    assert client_ip(_request(headers={"fly-client-ip": "8.8.8.8"})) == "8.8.8.8"


def test_bucket_key_prefers_signed_in_user():
    req = _request(session={"user": {"email": "a@b.com"}})
    assert rate_limit._bucket_key(req) == "user:a@b.com"
    assert rate_limit._bucket_key(_request()) == "ip:1.2.3.4"


def _app(limit: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.post("/api/explain")
    def explain():
        return {"ok": True}

    return app


def test_blocks_after_limit():
    client = TestClient(_app(limit=2))
    assert client.post("/api/explain").status_code == 200
    assert client.post("/api/explain").status_code == 200
    r = client.post("/api/explain")
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_health_and_non_post_are_never_limited():
    client = TestClient(_app(limit=1))
    assert client.post("/api/explain").status_code == 200
    assert client.post("/api/explain").status_code == 429
    for _ in range(5):
        assert client.get("/api/health").status_code == 200


def test_limit_zero_disables_limiting():
    client = TestClient(_app(limit=0))
    for _ in range(10):
        assert client.post("/api/explain").status_code == 200
