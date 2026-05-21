"""Tests for the granular reset paths — memory layer + HTTP endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from backend.memory.persistent import PersistentMemory


@pytest.fixture()
def mem(tmp_path):
    return PersistentMemory(tmp_path / "reset.db")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "endpoints.db"))
    monkeypatch.setenv("DEFAULT_USER_ID", "reset-user")
    from backend.server import app
    return TestClient(app)


# ── memory layer ──
def test_reset_lesson_only_wipes_that_lesson(mem):
    mem.upsert_user("u", "Tester")
    mem.record_lesson_score("u", "greetings-001", 0.8)
    mem.record_lesson_score("u", "numbers-001", 0.7)
    mem.log_mistake("u", "vocab", "hola", "olla", lesson_id="greetings-001")
    mem.log_mistake("u", "vocab", "uno", "wun", lesson_id="numbers-001")

    res = mem.reset_lesson("u", "greetings-001")
    assert res["progress"] == 1
    assert res["mistakes"] == 1

    rows = mem.get_progress("u")
    assert any(r["lesson_id"] == "numbers-001" for r in rows)
    assert not any(r["lesson_id"] == "greetings-001" for r in rows)


def test_reset_weak_spots_keeps_mastery(mem):
    mem.upsert_user("u", "Tester")
    # Build a word with a lapse.
    mem.record_vocab_attempt("u", "perro", "es", success=True)
    mem.record_vocab_attempt("u", "perro", "es", success=False)
    mem.log_mistake("u", "vocab", "perro", "pero")

    before = mem.weak_areas("u")
    assert before, "should have a weak word"

    res = mem.reset_weak_spots("u")
    assert res["vocab_mastery_reset"] >= 1
    assert res["mistakes_cleared"] >= 1

    after = mem.weak_areas("u")
    assert not after, "weak words should be empty after reset"

    # The row still exists — mastery preserved.
    import sqlite3
    with sqlite3.connect(str(mem.db_path)) as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT lapses, ease, reps FROM vocab_mastery WHERE user_id=? AND word=?",
            ("u", "perro"),
        ).fetchone()
    assert row is not None
    assert row["lapses"] == 0
    assert row["ease"] == 2.5
    assert row["reps"] >= 1  # mastery history kept


def test_export_user_data_shape(mem):
    mem.upsert_user("u", "Tester")
    mem.record_lesson_score("u", "greetings-001", 0.5)
    mem.record_vocab_attempt("u", "hola", "es", success=True)
    mem.log_mistake("u", "vocab", "hola", "ola")

    snap = mem.export_user_data("u")
    assert snap["user_id"] == "u"
    assert snap["user"]["name"] == "Tester"
    assert len(snap["progress"]) >= 1
    assert len(snap["vocab_mastery"]) >= 1
    assert len(snap["mistakes"]) >= 1


# ── HTTP endpoints ──
def test_endpoint_reset_lesson(client):
    from backend.memory.persistent import get_memory
    mem = get_memory()
    mem.upsert_user("reset-user", "X")
    mem.record_lesson_score("reset-user", "greetings-001", 0.6)
    mem.record_lesson_score("reset-user", "numbers-001", 0.6)

    r = client.post("/reset_lesson", params={"lesson_id": "greetings-001"})
    assert r.status_code == 200
    data = r.json()
    assert data["scope"] == "lesson"
    assert data["lesson_id"] == "greetings-001"

    rows = mem.get_progress("reset-user")
    assert not any(r["lesson_id"] == "greetings-001" for r in rows)
    assert any(r["lesson_id"] == "numbers-001" for r in rows)


def test_endpoint_reset_weak_spots(client):
    from backend.memory.persistent import get_memory
    mem = get_memory()
    mem.upsert_user("reset-user", "X")
    mem.record_vocab_attempt("reset-user", "agua", "es", success=False)

    r = client.post("/reset_weak_spots")
    assert r.status_code == 200
    data = r.json()
    assert data["scope"] == "weak_spots"
    assert "updated" in data


def test_endpoint_export_progress(client):
    from backend.memory.persistent import get_memory
    mem = get_memory()
    mem.upsert_user("reset-user", "X")
    mem.record_vocab_attempt("reset-user", "agua", "es", success=True)

    r = client.get("/export_progress")
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    assert "vocab_mastery" in data
    assert "progress" in data
    assert "mistakes" in data


# ── session memory: pending confirmation ──
def test_pending_confirmation_field():
    """SessionMemory should track a pending destructive action."""
    from backend.memory.session import SessionMemory
    s = SessionMemory(user_id="u")
    assert s.pending_confirmation is None
    s.pending_confirmation = "reset_all"
    assert s.pending_confirmation == "reset_all"
