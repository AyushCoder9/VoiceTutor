import pytest

from backend.agent.orchestrator import ModeFSM
from backend.agent.tools import ToolRunner, specs_for_llm
from backend.memory.persistent import PersistentMemory
from backend.memory.session import SessionMemory


@pytest.fixture()
def runner(tmp_path):
    db = PersistentMemory(tmp_path / "t.db")
    db.upsert_user("u1", "Test")
    sess = SessionMemory(user_id="u1")
    fsm = ModeFSM(sess)
    return ToolRunner(sess, fsm, db), sess, fsm


def test_tool_specs_well_formed():
    specs = specs_for_llm()
    assert specs
    for s in specs:
        assert s["type"] == "function"
        assert "name" in s["function"]
        assert "parameters" in s["function"]


@pytest.mark.asyncio
async def test_start_lesson_sets_session_and_returns_brief(runner):
    r, sess, fsm = runner
    out = await r.dispatch("start_lesson", {"topic": "greetings"})
    assert "lesson_id" in out
    assert sess.mode == "teaching"
    assert sess.current_lesson_id == out["lesson_id"]
    assert sess.introduced_vocab  # vocab added


@pytest.mark.asyncio
async def test_start_quiz_builds_questions(runner):
    r, sess, _ = runner
    out = await r.dispatch("start_quiz", {"topic": "numbers", "n_questions": 4})
    assert out["n_questions"] >= 1
    assert sess.mode == "quiz"
    assert sess.quiz_total >= 1


@pytest.mark.asyncio
async def test_grade_answer_records_attempt_and_session_state(runner):
    r, sess, _ = runner
    res = await r.dispatch("grade_answer", {"expected": "hola", "got": "hola"})
    assert res["correct"]
    # vocab mastery tracked
    res2 = await r.dispatch("grade_answer", {"expected": "hola", "got": "completely wrong"})
    assert not res2["correct"]
    assert sess.session_mistakes


@pytest.mark.asyncio
async def test_doubt_round_trip_via_tools(runner):
    r, sess, _ = runner
    await r.dispatch("start_lesson", {"topic": "greetings"})
    prior = sess.mode
    await r.dispatch("enter_doubt_mode", {})
    assert sess.mode == "doubt"
    await r.dispatch("exit_doubt_mode", {})
    assert sess.mode == prior


@pytest.mark.asyncio
async def test_save_progress_persists(runner):
    r, sess, _ = runner
    await r.dispatch("save_progress", {"lesson_id": "greetings-001", "score": 0.85})
    rows = r.memory.get_progress("u1")
    assert rows and rows[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_lookup_vocab_bilingual(runner):
    r, *_ = runner
    out = await r.dispatch("lookup_vocab", {"word": "hola"})
    assert out["found"]
    assert out["en"] == "hello"


@pytest.mark.asyncio
async def test_end_session_summary_shape(runner):
    r, sess, _ = runner
    sess.add_mistake("vocab", "hola", "olla")
    sess.introduce_vocab("hola")
    summary = await r.dispatch("end_session_summary", {})
    assert "vocab_introduced" in summary
    assert summary["mistakes"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(runner):
    r, *_ = runner
    out = await r.dispatch("does_not_exist", {})
    assert "error" in out
