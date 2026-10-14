from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.rate_limit import RateLimitMiddleware


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
