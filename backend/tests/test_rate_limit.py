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


def _app(limit: int, daily_quota: int = 0, store_path=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=limit,
        daily_quota=daily_quota,
        store_path=store_path,
    )

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


def test_daily_quota_blocks_after_limit():
    client = TestClient(_app(limit=0, daily_quota=2))
    assert client.post("/api/explain").status_code == 200
    assert client.post("/api/explain").status_code == 200
    r = client.post("/api/explain")
    assert r.status_code == 429
    assert "Daily limit" in r.json()["detail"]
    assert r.headers["X-Quota-Remaining"] == "0"


def test_quota_remaining_header_counts_down():
    client = TestClient(_app(limit=0, daily_quota=5))
    r1 = client.post("/api/explain")
    assert r1.headers["X-Quota-Limit"] == "5"
    assert r1.headers["X-Quota-Remaining"] == "4"
    r2 = client.post("/api/explain")
    assert r2.headers["X-Quota-Remaining"] == "3"


def test_quota_zero_disables_quota():
    client = TestClient(_app(limit=0, daily_quota=0))
    for _ in range(12):
        assert client.post("/api/explain").status_code == 200


def test_disabled_quota_sends_no_header():
    client = TestClient(_app(limit=0, daily_quota=0))
    assert "X-Quota-Remaining" not in client.post("/api/explain").headers


def test_sqlite_store_persists_across_instances(tmp_path):
    db = str(tmp_path / "limits.db")

    client1 = TestClient(_app(limit=0, daily_quota=2, store_path=db))
    assert client1.post("/api/explain").status_code == 200
    assert client1.post("/api/explain").status_code == 200

    # New app + middleware, same DB file -> quota still exhausted (persisted).
    client2 = TestClient(_app(limit=0, daily_quota=2, store_path=db))
    r = client2.post("/api/explain")
    assert r.status_code == 429
    assert "Daily limit" in r.json()["detail"]


def test_sqlite_store_tracks_remaining_header(tmp_path):
    db = str(tmp_path / "limits.db")

    client1 = TestClient(_app(limit=0, daily_quota=5, store_path=db))
    assert client1.post("/api/explain").headers["X-Quota-Remaining"] == "4"

    client2 = TestClient(_app(limit=0, daily_quota=5, store_path=db))
    assert client2.post("/api/explain").headers["X-Quota-Remaining"] == "3"


def test_sqlite_store_enforces_minute_limit(tmp_path):
    db = str(tmp_path / "limits.db")
    client = TestClient(_app(limit=2, daily_quota=0, store_path=db))
    assert client.post("/api/explain").status_code == 200
    assert client.post("/api/explain").status_code == 200
    assert client.post("/api/explain").status_code == 429


def test_sqlite_store_creates_parent_directory(tmp_path):
    db = str(tmp_path / "nested" / "dir" / "limits.db")
    client = TestClient(_app(limit=0, daily_quota=1, store_path=db))
    assert client.post("/api/explain").status_code == 200
    assert (tmp_path / "nested" / "dir" / "limits.db").is_file()
