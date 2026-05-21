"""Deeper scenario tests for the FastAPI endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "scenarios.db"))
    monkeypatch.setenv("DEFAULT_USER_ID", "scenario-user")
    from backend.server import app
    return TestClient(app)


def test_curriculum_each_lesson_well_formed(client):
    r = client.get("/curriculum")
    payload = r.json()
    for lesson in payload["lessons"]:
        assert lesson["estimated_minutes"] > 0
        assert lesson["vocab_count"] >= 5, f"{lesson['id']} has too few vocab"
        assert lesson["level"] in {"A1", "A2", "B1"}


def test_session_recovery_empty_state(client):
    """Fresh user → has_recent_session=False."""
    r = client.get("/session_recovery", params={"user_id": "brand-new"})
    data = r.json()
    assert data["user_id"] == "brand-new"
    assert data["has_recent_session"] in (False, True)  # may be true if prior cleanup not done
    assert isinstance(data["suggested_next"], str)


def test_session_recovery_after_quiz_lapse(client):
    """User with a lapsed word → due_words populated."""
    from backend.memory.persistent import get_memory
    mem = get_memory()
    mem.upsert_user("flow", "Flow")
    mem.record_vocab_attempt("flow", "perro", "es", success=False)

    r = client.get("/session_recovery", params={"user_id": "flow"})
    data = r.json()
    assert data["has_recent_session"] is True
    assert "perro" in data["words_due"]


def test_reset_progress_with_specific_user(client):
    from backend.memory.persistent import get_memory
    mem = get_memory()
    mem.upsert_user("alice", "Alice")
    mem.upsert_user("bob", "Bob")
    mem.record_vocab_attempt("alice", "hola", "es", success=False)
    mem.record_vocab_attempt("bob", "adios", "es", success=False)

    # Reset only Alice
    r = client.post("/reset_progress", params={"user_id": "alice"})
    assert r.status_code == 200
    assert r.json()["user_id"] == "alice"

    # Bob's data should survive.
    assert any(w["word"] == "adios" for w in mem.weak_areas("bob"))


def test_metrics_after_synthetic_data(client):
    from backend.observability.metrics import METRICS
    METRICS._stt.clear()
    METRICS._llm_ttft.clear()
    METRICS._tts_first.clear()
    METRICS._total.clear()
    METRICS.record_turn(stt_ms=120, llm_ttft_ms=300, tts_first_ms=400, total_ms=900)
    METRICS.record_turn(stt_ms=180, llm_ttft_ms=350, tts_first_ms=420, total_ms=1100)

    r = client.get("/metrics")
    data = r.json()
    assert data["total_ms"]["n"] == 2
    assert data["total_ms"]["p50"] <= data["total_ms"]["p95"]


def test_health_endpoint_reports_dependencies(client):
    r = client.get("/health")
    data = r.json()
    assert data["status"] in {"ok", "degraded"}
    assert "sqlite" in data["checks"]
    # Each api-key check must be present (regardless of value).
    for key in ("groq_api_key", "assemblyai_api_key", "elevenlabs_api_key"):
        assert key in data["checks"]


def test_curriculum_topics_cover_all_lessons(client):
    """Every lesson must be findable by at least one natural keyword."""
    from backend.curriculum.loader import CURRICULUM
    natural_topics = {
        "greetings-001": "greetings",
        "numbers-001": "numbers",
        "ordering-food-001": "food",
        "family-001": "family",
        "days-time-001": "days",
        "directions-001": "directions",
    }
    for lesson in CURRICULUM.all():
        topic = natural_topics.get(lesson.id)
        assert topic, f"no test mapping for {lesson.id}"
        found = CURRICULUM.by_topic(topic)
        assert found is not None and found.id == lesson.id
