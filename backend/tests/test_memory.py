import os
from pathlib import Path

import pytest

from backend.memory.persistent import PersistentMemory
from backend.memory.session import SessionMemory


@pytest.fixture()
def mem(tmp_path: Path) -> PersistentMemory:
    db = tmp_path / "test.db"
    return PersistentMemory(db)


def test_upsert_user_idempotent(mem: PersistentMemory):
    mem.upsert_user("u1", "Alice")
    mem.upsert_user("u1", "Alice")
    u = mem.get_user("u1")
    assert u and u["name"] == "Alice"


def test_progress_records_and_completes(mem: PersistentMemory):
    mem.upsert_user("u1", "A")
    mem.record_lesson_score("u1", "L1", 0.5)
    rows = mem.get_progress("u1")
    assert len(rows) == 1
    assert rows[0]["status"] == "in_progress"

    mem.record_lesson_score("u1", "L1", 0.9)
    rows = mem.get_progress("u1")
    assert rows[0]["status"] == "completed"
    # MAX(score) semantics
    assert rows[0]["score"] == 0.9


def test_vocab_fsrs_success_grows_interval(mem: PersistentMemory):
    mem.upsert_user("u1", "A")
    r1 = mem.record_vocab_attempt("u1", "hola", "es", success=True)
    r2 = mem.record_vocab_attempt("u1", "hola", "es", success=True)
    assert r2["interval_days"] > r1["interval_days"]
    assert r2["reps"] == 2


def test_vocab_fsrs_lapse_shrinks_interval(mem: PersistentMemory):
    mem.upsert_user("u1", "A")
    mem.record_vocab_attempt("u1", "perro", "es", success=True)
    mem.record_vocab_attempt("u1", "perro", "es", success=True)
    big = mem.record_vocab_attempt("u1", "perro", "es", success=True)
    small = mem.record_vocab_attempt("u1", "perro", "es", success=False)
    assert small["interval_days"] <= big["interval_days"]
    assert small["lapses"] == 1
    assert small["ease"] < big["ease"]


def test_weak_areas_sorted_by_lapses(mem: PersistentMemory):
    mem.upsert_user("u1", "A")
    for w in ["hola", "adios", "gracias"]:
        mem.record_vocab_attempt("u1", w, "es", success=True)
    mem.record_vocab_attempt("u1", "gracias", "es", success=False)
    mem.record_vocab_attempt("u1", "gracias", "es", success=False)
    mem.record_vocab_attempt("u1", "adios", "es", success=False)
    weak = mem.weak_areas("u1")
    assert weak[0]["word"] == "gracias"


def test_mistakes_log(mem: PersistentMemory):
    mem.upsert_user("u1", "A")
    mem.log_mistake("u1", "vocab", "hola", "olla")
    mistakes = mem.recent_mistakes("u1")
    assert len(mistakes) == 1
    assert mistakes[0]["expected"] == "hola"


# ---- session memory ----
def test_session_doubt_stack_round_trip():
    s = SessionMemory(user_id="u")
    s.mode = "teaching"
    s.current_lesson_id = "L"
    s.lesson_step = "practice"
    s.push_doubt()
    assert s.mode == "doubt"
    s.pop_doubt()
    assert s.mode == "teaching"
    assert s.lesson_step == "practice"


def test_session_confidence_moves_with_outcomes():
    s = SessionMemory(user_id="u")
    base = s.confidence_score
    s.add_mistake("vocab", "x", "y")
    assert s.confidence_score < base
    s.add_success()
    assert s.consecutive_failures == 0


def test_frustration_detection():
    s = SessionMemory(user_id="u")
    for _ in range(3):
        s.add_mistake("vocab", "x", "y")
    assert s.is_frustrated()


def test_introduced_vocab_unique():
    s = SessionMemory(user_id="u")
    s.introduce_vocab("hola")
    s.introduce_vocab("Hola")
    s.introduce_vocab("adiós")
    assert len(s.introduced_vocab) == 2


def test_context_summary_includes_mode_and_confidence():
    s = SessionMemory(user_id="u")
    s.mode = "teaching"
    s.current_lesson_id = "L"
    summary = s.context_summary()
    assert "mode=teaching" in summary
    assert "confidence=" in summary
