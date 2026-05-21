"""Smoke tests for the FastAPI endpoints (excluding /ws which needs Pipecat)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "endpoints.db"))
    # Avoid pipecat module imports at request time — the WS route isn't hit here.
    from backend.server import app
    return TestClient(app)


def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    payload = r.json()
    assert payload["service"] == "voicetutor"
    assert payload["target_lang"] == "es"
    assert len(payload["lessons"]) >= 6


def test_curriculum_endpoint(client):
    r = client.get("/curriculum")
    assert r.status_code == 200
    data = r.json()
    assert data["language"] == "es"
    assert data["native_language"] == "en"
    assert len(data["lessons"]) >= 6
    # Every lesson exposes the fields the frontend uses.
    for l in data["lessons"]:
        assert {"id", "title", "level", "estimated_minutes", "objective", "vocab_count"} <= set(l.keys())


def test_progress_endpoint_returns_shape(client):
    r = client.get("/progress")
    assert r.status_code == 200
    data = r.json()
    assert "user_id" in data
    assert "progress" in data
    assert "weak_areas" in data
    assert "due_vocab" in data
    assert "recent_mistakes" in data


def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    for k in ("stt_ms", "llm_ttft_ms", "tts_first_ms", "total_ms"):
        assert k in data
        assert set(["n", "p50", "p95", "max", "mean"]) <= set(data[k].keys())


def test_reset_progress_endpoint(client):
    # First create some state.
    from backend.memory.persistent import get_memory
    mem = get_memory()
    uid = "demo-user-001"
    mem.upsert_user(uid, "Test")
    mem.log_mistake(uid, "vocab", "hola", "ola")
    assert mem.recent_mistakes(uid), "should have created a mistake"

    r = client.post("/reset_progress")
    assert r.status_code == 200
    data = r.json()
    assert "deleted" in data

    assert not mem.recent_mistakes(uid), "mistakes should be cleared"


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "checks" in data
    assert "sqlite" in data["checks"]


def test_session_recovery_endpoint(client):
    r = client.get("/session_recovery")
    assert r.status_code == 200
    data = r.json()
    assert "user_id" in data
    assert "has_recent_session" in data
    assert "suggested_next" in data
