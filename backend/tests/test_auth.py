from dataclasses import replace

from fastapi.testclient import TestClient

from app import ai, main
from app.config import settings
from app.main import app

client = TestClient(app)


def _with_key(monkeypatch, key: str):
    monkeypatch.setattr(main, "settings", replace(settings, api_key=key))


def test_open_when_no_key(monkeypatch):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", lambda: None)

    async def fake_explain(**kwargs):
        return "ok", "local"

    monkeypatch.setattr(ai, "explain", fake_explain)
    r = client.post("/api/explain", data={"text": "2+2", "level": "high", "engine": "local"})
    assert r.status_code == 200


def test_health_reports_auth_required(monkeypatch):
    _with_key(monkeypatch, "secret")
    assert client.get("/api/health").json()["auth_required"] is True
    monkeypatch.setattr(main, "settings", replace(settings, api_key=""))
    assert client.get("/api/health").json()["auth_required"] is False


def test_rejects_missing_or_wrong_key(monkeypatch):
    _with_key(monkeypatch, "secret")
    body = {"text": "2+2", "level": "high", "engine": "local"}
    assert client.post("/api/explain", data=body).status_code == 401
    assert client.post("/api/explain", data=body, headers={"X-API-Key": "nope"}).status_code == 401


def test_accepts_x_api_key(monkeypatch):
    _with_key(monkeypatch, "secret")
    monkeypatch.setattr(ai, "make_cloud_vision_reader", lambda: None)

    async def fake_explain(**kwargs):
        return "ok", "local"

    monkeypatch.setattr(ai, "explain", fake_explain)
    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "high", "engine": "local"},
        headers={"X-API-Key": "secret"},
    )
    assert r.status_code == 200


def test_accepts_bearer_token(monkeypatch):
    _with_key(monkeypatch, "secret")
    monkeypatch.setattr(ai, "make_cloud_vision_reader", lambda: None)

    async def fake_explain(**kwargs):
        return "ok", "local"

    monkeypatch.setattr(ai, "explain", fake_explain)
    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "high", "engine": "local"},
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200


def test_followup_is_also_gated(monkeypatch):
    _with_key(monkeypatch, "secret")
    r = client.post(
        "/api/followup",
        json={"context": "x", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 401
