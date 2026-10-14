import io

from fastapi.testclient import TestClient

from app import ai
from app.main import app

client = TestClient(app)


def _no_cloud_vision():
    return None


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "ollama_model" in body


def test_cors_allows_configured_origin():
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_explain_requires_text_or_file():
    r = client.post("/api/explain", data={"level": "high", "engine": "local"})
    assert r.status_code == 400
    assert "Type the problem" in r.json()["detail"]


def test_explain_rejects_bad_level():
    r = client.post(
        "/api/explain", data={"text": "2+2", "level": "baby", "engine": "local"}
    )
    assert r.status_code == 400


def test_explain_rejects_bad_engine():
    r = client.post(
        "/api/explain", data={"text": "2+2", "level": "high", "engine": "magic"}
    )
    assert r.status_code == 400


def test_explain_text_only(monkeypatch):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", _no_cloud_vision)

    async def fake_explain(**kwargs):
        assert kwargs["extracted_text"] == "2+2"
        assert kwargs["level"] == "middle"
        return "It equals 4.", "local"

    monkeypatch.setattr(ai, "explain", fake_explain)

    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "middle", "subject": "Maths", "engine": "local"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["explanation"] == "It equals 4."
    assert body["read_method"] == "typed"
    assert body["file_count"] == 0
    assert body["engine_used"] == "local"


def test_explain_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", _no_cloud_vision)
    big = io.BytesIO(b"x" * (21 * 1024 * 1024))
    r = client.post(
        "/api/explain",
        data={"text": "x", "level": "high", "engine": "local"},
        files={"files": ("big.png", big, "image/png")},
    )
    assert r.status_code == 413


def test_explain_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", _no_cloud_vision)
    files = [
        ("files", (f"p{i}.png", io.BytesIO(b"1234"), "image/png")) for i in range(11)
    ]
    r = client.post(
        "/api/explain",
        data={"text": "x", "level": "high", "engine": "local"},
        files=files,
    )
    assert r.status_code == 400


def test_explain_cloud_without_key_is_502(monkeypatch):
    monkeypatch.setattr(ai, "make_cloud_vision_reader", _no_cloud_vision)
    # cloud_enabled is False without an API key
    r = client.post(
        "/api/explain",
        data={"text": "2+2", "level": "high", "engine": "cloud"},
    )
    assert r.status_code == 502


def test_followup_requires_messages():
    r = client.post(
        "/api/followup", json={"messages": [], "level": "high", "engine": "local"}
    )
    assert r.status_code == 400


def test_followup_ok(monkeypatch):
    async def fake_followup(**kwargs):
        assert kwargs["context"] == "2x + 3 = 11"
        assert kwargs["history"][0]["content"] == "why divide by 2?"
        return "Because 2 is the coefficient.", "local"

    monkeypatch.setattr(ai, "followup", fake_followup)

    r = client.post(
        "/api/followup",
        json={
            "context": "2x + 3 = 11",
            "messages": [{"role": "user", "content": "why divide by 2?"}],
            "level": "high",
            "engine": "local",
        },
    )
    assert r.status_code == 200
    assert r.json()["answer"] == "Because 2 is the coefficient."


def test_spa_unknown_api_path_404s():
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
