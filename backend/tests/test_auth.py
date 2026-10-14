from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import ai, auth, main
from app.config import settings
from app.main import app

client = TestClient(app)


def _configure(monkeypatch, **overrides):
    """Patch the shared settings singleton seen by both main and auth."""
    new = replace(settings, **overrides)
    monkeypatch.setattr(main, "settings", new)
    monkeypatch.setattr(auth, "settings", new)
    return new


def _fake_explain(monkeypatch, result=("ok", "local")):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", lambda: None)

    async def fake_explain(**kwargs):
        return result

    monkeypatch.setattr(ai, "explain", fake_explain)


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


# --- open mode -------------------------------------------------------------
def test_open_mode_allows(monkeypatch):
    _configure(monkeypatch)  # no api key, no oauth
    _fake_explain(monkeypatch)
    r = client.post("/api/explain", data={"text": "2+2", "level": "high", "engine": "local"})
    assert r.status_code == 200
    assert client.get("/api/health").json()["auth_required"] is False


# --- API-key mode ----------------------------------------------------------
def test_api_key_required(monkeypatch):
    _configure(monkeypatch, api_key="secret")
    body = {"text": "2+2", "level": "high", "engine": "local"}
    assert client.post("/api/explain", data=body).status_code == 401
    assert (
        client.post("/api/explain", data=body, headers={"X-API-Key": "nope"}).status_code == 401
    )


def test_api_key_accepted(monkeypatch):
    _configure(monkeypatch, api_key="secret")
    _fake_explain(monkeypatch)
    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "high", "engine": "local"},
        headers={"X-API-Key": "secret"},
    )
    assert r.status_code == 200
    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "high", "engine": "local"},
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 200


# --- OAuth gating ----------------------------------------------------------
def test_oauth_requires_signin(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    r = client.post("/api/explain", data={"text": "2+2", "level": "high", "engine": "local"})
    assert r.status_code == 401


def test_health_reports_providers(monkeypatch):
    _configure(
        monkeypatch,
        google_client_id="gid",
        google_client_secret="gsec",
        github_client_id="cid",
        github_client_secret="csec",
    )
    health = client.get("/api/health").json()
    assert health["auth_required"] is True
    assert set(health["oauth_providers"]) == {"google", "github"}


def test_me_returns_null_when_signed_out(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    assert client.get("/api/auth/me").json()["user"] is None


def test_login_redirects_to_google(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    r = client.get("/api/auth/login/google", follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "state=" in loc


def test_login_unknown_provider_404(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    r = client.get("/api/auth/login/github", follow_redirects=False)
    assert r.status_code == 404


def test_callback_signs_user_in(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")

    async def fake_exchange(provider, code, redirect_uri):
        return {
            "provider": "google",
            "id": "1",
            "email": "kid@example.com",
            "name": "Kid",
            "picture": None,
        }

    monkeypatch.setattr(auth, "_exchange_code", fake_exchange)

    c = TestClient(app)  # fresh cookie jar
    loc = c.get("/api/auth/login/google", follow_redirects=False).headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]

    r = c.get(f"/api/auth/callback/google?code=abc&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert c.get("/api/auth/me").json()["user"]["email"] == "kid@example.com"

    # signed-in session now satisfies the gate
    _fake_explain(monkeypatch)
    ok = c.post("/api/explain", data={"text": "2+2", "level": "high", "engine": "local"})
    assert ok.status_code == 200

    assert c.post("/api/auth/logout").json()["ok"] is True
    assert c.get("/api/auth/me").json()["user"] is None


def test_callback_allowlist_blocks(monkeypatch):
    _configure(
        monkeypatch,
        google_client_id="gid",
        google_client_secret="gsec",
        allowed_emails="allowed@example.com",
    )

    async def fake_exchange(provider, code, redirect_uri):
        return {"provider": "google", "id": "1", "email": "other@example.com", "name": "X"}

    monkeypatch.setattr(auth, "_exchange_code", fake_exchange)

    c = TestClient(app)
    loc = c.get("/api/auth/login/google", follow_redirects=False).headers["location"]
    state = parse_qs(urlparse(loc).query)["state"][0]
    r = c.get(f"/api/auth/callback/google?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 403


def test_callback_rejects_bad_state(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    c = TestClient(app)
    r = c.get("/api/auth/callback/google?code=abc&state=wrong", follow_redirects=False)
    assert r.status_code == 400


# --- gate unit tests -------------------------------------------------------
def test_require_access_with_session(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    auth.require_access(
        _request(session={"user": {"email": "a@b.com"}}),
        x_api_key=None,
        authorization=None,
    )


def test_require_access_without_session_raises(monkeypatch):
    _configure(monkeypatch, google_client_id="gid", google_client_secret="gsec")
    with pytest.raises(HTTPException):
        auth.require_access(_request(), x_api_key=None, authorization=None)
