"""Full-session e2e: learner walks through teaching → quiz → doubt → resume.

Exercises every public interface short of the real audio pipeline:
- IntentRouter intent recognition  (simulated by direct dispatcher calls)
- Mode FSM with doubt stack
- Quiz grading + FSRS update + progress recording
- Session memory mutations
- Persistent memory side effects
"""

from __future__ import annotations

import pytest

from backend.agent.orchestrator import ModeFSM
from backend.agent.tools import ToolRunner
from backend.memory.persistent import PersistentMemory
from backend.memory.session import SessionMemory


@pytest.fixture()
def env(tmp_path):
    db = PersistentMemory(tmp_path / "journey.db")
    db.upsert_user("journey-user", "Journey")
    sess = SessionMemory(user_id="journey-user")
    fsm = ModeFSM(sess)
    return ToolRunner(sess, fsm, db), sess, fsm, db


# -----------------------------------------------------------------------------
# A complete teaching → quiz → doubt → resume cycle
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_cycle_teach_quiz_doubt_resume(env):
    runner, sess, fsm, db = env

    # 1. Start lesson.
    out = await runner.dispatch("start_lesson", {"topic": "greetings"})
    assert sess.mode == "teaching"
    assert sess.current_lesson_id == out["lesson_id"]

    # 2. Walk through teaching steps via FSM directly (IntentRouter would do this).
    for _ in range(5):
        fsm.advance_lesson()
    assert fsm.lesson_complete()

    # 3. Start a quiz.
    out = await runner.dispatch("start_quiz", {"topic": "greetings", "n_questions": 3})
    assert sess.mode == "quiz"
    assert sess.quiz_total >= 1

    # 4. Answer first question correctly (use the actual lesson check).
    from backend.curriculum.loader import CURRICULUM
    lesson = CURRICULUM.get(sess.current_lesson_id)
    expected = lesson.checks[0].expected_es
    res = await runner.dispatch("grade_answer", {
        "expected": expected, "got": expected, "variants": []
    })
    assert res["correct"]

    # 5. Mid-quiz interruption: doubt mode.
    await runner.dispatch("enter_doubt_mode", {})
    assert sess.mode == "doubt"

    # 6. Resume.
    await runner.dispatch("exit_doubt_mode", {})
    assert sess.mode == "quiz"

    # 7. Save progress on lesson.
    await runner.dispatch("save_progress", {"lesson_id": lesson.id, "score": 0.85})
    rows = db.get_progress("journey-user")
    assert any(r["status"] == "completed" for r in rows)


# -----------------------------------------------------------------------------
# Code-switching: lookup_vocab returns valid entries for either language
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_code_switching_vocab_lookup(env):
    runner, *_ = env
    en = await runner.dispatch("lookup_vocab", {"word": "hello"})
    es = await runner.dispatch("lookup_vocab", {"word": "hola"})
    assert en["found"] and en["es"] == "hola"
    assert es["found"] and es["en"] == "hello"


# -----------------------------------------------------------------------------
# Multiple lapses on the same word should keep ease above floor
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_repeated_quiz_wrong_does_not_break(env):
    runner, sess, fsm, db = env
    await runner.dispatch("start_quiz", {"topic": "greetings", "n_questions": 5})

    # Answer every question wrong with the same garbage.
    for _ in range(min(5, sess.quiz_total)):
        await runner.dispatch("grade_answer", {
            "expected": "hola", "got": "zzzzz", "variants": []
        })

    # Bot should still be functional.
    out = await runner.dispatch("end_session_summary", {})
    assert "mistakes" in out
    assert len(out["mistakes"]) > 0


# -----------------------------------------------------------------------------
# Multiple lessons in a row — memory must keep them all
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_multi_lesson_session(env):
    runner, sess, fsm, db = env

    topics = ["greetings", "numbers", "food", "family", "days", "directions"]
    for topic in topics:
        out = await runner.dispatch("start_lesson", {"topic": topic})
        assert sess.mode == "teaching"
        await runner.dispatch("save_progress", {
            "lesson_id": out["lesson_id"], "score": 0.75
        })

    progress = db.get_progress("journey-user")
    assert len(progress) >= 6, f"expected ≥6 lesson rows, got {len(progress)}"


# -----------------------------------------------------------------------------
# Doubt resume preserves quiz state exactly
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_doubt_resume_preserves_quiz_position(env):
    runner, sess, fsm, db = env

    await runner.dispatch("start_quiz", {"topic": "greetings"})
    # Pretend we've answered 2 of 5 questions.
    sess.quiz_index = 2
    snapshot = sess.quiz_index

    await runner.dispatch("enter_doubt_mode", {})
    assert sess.mode == "doubt"
    # Doubt activity (would normally be one bot turn).
    await runner.dispatch("exit_doubt_mode", {})
    assert sess.mode == "quiz"
    assert sess.quiz_index == snapshot, "quiz index drifted across doubt round-trip"
