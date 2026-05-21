"""Property tests for FSRS-lite scheduler invariants."""

import pytest

from backend.memory.persistent import PersistentMemory


@pytest.fixture()
def mem(tmp_path):
    m = PersistentMemory(tmp_path / "fsrs.db")
    m.upsert_user("u", "Test")
    return m


def test_ease_floor_1_3(mem):
    """No matter how many lapses, ease must not fall below 1.3."""
    for _ in range(50):
        mem.record_vocab_attempt("u", "x", "es", success=False)
    rows = [r for r in mem.weak_areas("u", limit=1)]
    assert rows
    assert rows[0]["ease"] >= 1.3


def test_ease_ceiling_2_5(mem):
    """No matter how many successes, ease must not exceed 2.5."""
    for _ in range(50):
        mem.record_vocab_attempt("u", "x", "es", success=True)
    due = mem.due_vocab("u", limit=10)  # may be 0 — that's fine
    # Direct read from DB through public API:
    weak = mem.weak_areas("u")  # would be empty (no lapses), check
    # Re-read the row to inspect ease.
    import sqlite3
    with sqlite3.connect(str(mem.db_path)) as c:
        c.row_factory = sqlite3.Row
        row = c.execute(
            "SELECT ease FROM vocab_mastery WHERE user_id=? AND word=?",
            ("u", "x"),
        ).fetchone()
    assert row is not None
    assert row["ease"] <= 2.5 + 1e-9


def test_interval_grows_with_streak(mem):
    """Successful streak should increase interval monotonically."""
    intervals = []
    for _ in range(5):
        r = mem.record_vocab_attempt("u", "y", "es", success=True)
        intervals.append(r["interval_days"])
    for a, b in zip(intervals, intervals[1:]):
        assert b >= a, f"interval went down: {a} → {b}"


def test_lapse_immediately_re_surfaces(mem):
    """After a lapse, word should appear in due_vocab on next read."""
    mem.record_vocab_attempt("u", "perro", "es", success=False)
    due = mem.due_vocab("u", limit=10)
    assert any(d["word"] == "perro" for d in due)


def test_mastered_word_not_due_soon(mem):
    """Successful repetition should defer next review."""
    for _ in range(3):
        mem.record_vocab_attempt("u", "easy", "es", success=True)
    due = mem.due_vocab("u", limit=10)
    assert not any(d["word"] == "easy" for d in due), (
        "successful word should not be due today"
    )


def test_lapse_decreases_ease(mem):
    """Lapse should drop ease below previous value."""
    mem.record_vocab_attempt("u", "z", "es", success=True)
    r_after_success = mem.record_vocab_attempt("u", "z", "es", success=True)
    r_after_lapse = mem.record_vocab_attempt("u", "z", "es", success=False)
    assert r_after_lapse["ease"] < r_after_success["ease"]


def test_reps_increment_on_success_only(mem):
    """`reps` counter should only increment on successful attempts."""
    r1 = mem.record_vocab_attempt("u", "rep", "es", success=True)
    r2 = mem.record_vocab_attempt("u", "rep", "es", success=False)
    r3 = mem.record_vocab_attempt("u", "rep", "es", success=True)
    assert r1["reps"] == 1
    assert r2["reps"] == 1   # lapse doesn't increment reps
    assert r3["reps"] == 2


def test_lapses_only_increment_on_failure(mem):
    """`lapses` counter should only increment on failed attempts."""
    r1 = mem.record_vocab_attempt("u", "lap", "es", success=True)
    r2 = mem.record_vocab_attempt("u", "lap", "es", success=False)
    r3 = mem.record_vocab_attempt("u", "lap", "es", success=False)
    assert r1["lapses"] == 0
    assert r2["lapses"] == 1
    assert r3["lapses"] == 2
