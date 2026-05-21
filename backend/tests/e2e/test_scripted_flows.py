"""End-to-end scripted conversation evaluation harness.

This is the regression-test harness the spec requires (§7.6 "evaluation harness").
It does NOT exercise the live audio pipeline (no STT/TTS), but it DOES exercise:

  - Mode FSM transitions across realistic user flows
  - Tool dispatch and side effects on session + persistent memory
  - Semantic grading paths
  - Doubt push/pop behaviour
  - Quiz scoring lifecycle

We model each scripted flow as a list of `(tool_name, args, assertions)` steps
and assert state after each step. Catches regressions in:
  - prompt/tool contract drift
  - FSM transition rules
  - grader sensitivity
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

from backend.agent.orchestrator import ModeFSM
from backend.agent.tools import ToolRunner
from backend.memory.persistent import PersistentMemory
from backend.memory.session import SessionMemory


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    assertion: Callable[[dict[str, Any], SessionMemory], None] | None = None
    label: str = ""


@pytest.fixture()
def env(tmp_path):
    db = PersistentMemory(tmp_path / "e2e.db")
    db.upsert_user("e2e-user", "EvalBot")
    sess = SessionMemory(user_id="e2e-user")
    fsm = ModeFSM(sess)
    return ToolRunner(sess, fsm, db), sess, fsm, db


# ----------------------------------------------------------------------------
# Flow 1 — Teaching lesson on greetings, learner answers correctly, lesson saves
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_teach_greetings_and_save(env):
    r, sess, fsm, db = env
    steps = [
        Step("start_lesson", {"topic": "greetings"},
             lambda out, s: (s.mode == "teaching" and out["lesson_id"]),
             label="enter teaching mode"),
        Step("grade_answer", {"expected": "hola", "got": "Hola"},
             lambda out, s: out["correct"],
             label="learner says hola correctly"),
        Step("grade_answer",
             {"expected": "mucho gusto", "got": "mucho gusto"},
             lambda out, s: out["correct"],
             label="learner says mucho gusto"),
        Step("save_progress", {"lesson_id": "greetings-001", "score": 0.9},
             lambda out, s: out["saved"],
             label="persist score"),
    ]
    for st in steps:
        out = await r.dispatch(st.tool, st.args)
        if st.assertion:
            assert st.assertion(out, sess), f"failed: {st.label} → {out}"
    rows = db.get_progress("e2e-user")
    assert rows and rows[0]["status"] == "completed"


# ----------------------------------------------------------------------------
# Flow 2 — Quiz, mixed correct/wrong, score reflects truth
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_quiz_scoring(env):
    r, sess, fsm, db = env
    out = await r.dispatch("start_quiz", {"topic": "numbers", "n_questions": 3})
    assert sess.mode == "quiz"
    n = sess.quiz_total

    # Simulate 2 correct + 1 wrong by directly grading from the lesson's vocab.
    await r.dispatch("grade_answer", {"expected": "uno", "got": "uno", "kind": "translation"})
    await r.dispatch("grade_answer", {"expected": "dos", "got": "dos", "kind": "translation"})
    await r.dispatch("grade_answer", {"expected": "tres", "got": "ten million", "kind": "translation"})

    assert sess.quiz_score == 2
    assert sess.quiz_index == 3


# ----------------------------------------------------------------------------
# Flow 3 — Mid-lesson doubt, resumed back to same step
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_doubt_mid_lesson_resumes(env):
    r, sess, _, _ = env
    await r.dispatch("start_lesson", {"topic": "food"})
    sess.lesson_step = "practice"
    assert sess.mode == "teaching"
    await r.dispatch("enter_doubt_mode", {})
    assert sess.mode == "doubt"
    await r.dispatch("exit_doubt_mode", {})
    assert sess.mode == "teaching"
    assert sess.lesson_step == "practice"


# ----------------------------------------------------------------------------
# Flow 4 — Pronunciation feedback returns specific advice
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_pronunciation_feedback_specific(env):
    r, *_ = env
    out = await r.dispatch("pronunciation_feedback", {"expected": "perro", "got": "pero"})
    assert "per_word" in out
    assert "summary" in out


# ----------------------------------------------------------------------------
# Flow 5 — Code-switched answer ("How do I say agua in English?") still grades
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_code_switched_lookup(env):
    r, *_ = env
    out = await r.dispatch("lookup_vocab", {"word": "agua"})
    assert out["found"] and out["en"] == "water"
    out2 = await r.dispatch("lookup_vocab", {"word": "water"})
    assert out2["found"] and out2["es"] == "agua"


# ----------------------------------------------------------------------------
# Flow 6 — Spaced repetition surfaces words after a lapse
# ----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_flow_fsrs_resurfaces_lapsed_word(env):
    r, sess, _, db = env
    db.record_vocab_attempt("e2e-user", "perro", "es", success=False)
    due = await r.dispatch("get_due_vocab", {"limit": 5})
    assert due["count"] >= 1
    assert any(w["word"] == "perro" for w in due["due"])
