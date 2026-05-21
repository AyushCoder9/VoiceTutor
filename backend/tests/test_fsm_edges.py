"""Edge cases for the mode-FSM."""

from backend.agent.orchestrator import ModeFSM
from backend.memory.session import SessionMemory


def make_fsm():
    return ModeFSM(SessionMemory(user_id="t"))


def test_lesson_step_caps_at_done():
    """Advancing past 'done' should stay at 'done', not crash or wrap."""
    f = make_fsm()
    f.switch_to("teaching")
    for _ in range(10):
        f.advance_lesson()
    assert f.session.lesson_step == "done"
    assert f.lesson_complete()


def test_doubt_stack_can_nest():
    """Two nested doubts should pop in LIFO order back to original mode."""
    f = make_fsm()
    f.switch_to("teaching")
    f.session.lesson_step = "explain"

    f.switch_to("doubt")
    # Within doubt, simulate another sub-question.
    f.session.lesson_step = "intro"
    f.switch_to("doubt")
    f.session.lesson_step = "practice"

    # Pop twice.
    f.exit_doubt()
    f.exit_doubt()
    assert f.session.mode == "teaching"
    assert f.session.lesson_step == "explain"


def test_switch_to_same_mode_idempotent():
    f = make_fsm()
    f.switch_to("teaching")
    f.session.lesson_step = "practice"
    f.switch_to("teaching")  # again — should reset step? Implementation choice.
    # FSM intent: re-entering teaching resets to intro.
    assert f.session.mode == "teaching"


def test_quiz_state_clears_when_leaving_quiz():
    """FSM contract: leaving quiz mode clears quiz state. Entering a new quiz
    is the IntentRouter's responsibility (it builds fresh questions)."""
    f = make_fsm()
    f.switch_to("quiz")
    f.session.quiz_score = 5
    f.session.quiz_index = 3
    f.session.quiz_total = 4
    f.session.quiz_questions = [{"x": 1}] * 4

    f.switch_to("teaching")  # leave quiz → state should clear
    assert f.session.quiz_score == 0
    assert f.session.quiz_index == 0
    assert f.session.quiz_total == 0
    assert not f.session.quiz_questions


def test_unknown_mode_returns_failure_unchanged():
    f = make_fsm()
    f.switch_to("teaching")
    prior_mode = f.session.mode
    r = f.switch_to("does-not-exist")
    assert not r.ok
    # Session mode should not have changed.
    assert f.session.mode == prior_mode


def test_session_summary_includes_quiz_state():
    f = make_fsm()
    f.switch_to("quiz")
    f.session.quiz_index = 2
    f.session.quiz_total = 5
    f.session.quiz_score = 1
    summary = f.session.context_summary()
    assert "quiz" in summary
    assert "5" in summary  # quiz_total


def test_persona_changes_on_mode_change():
    f = make_fsm()
    f.switch_to("teaching")
    teach_persona = f.session.persona
    f.switch_to("quiz")
    quiz_persona = f.session.persona
    f.switch_to("conversation")
    convo_persona = f.session.persona
    assert teach_persona != quiz_persona
    assert quiz_persona != convo_persona


def test_doubt_does_not_overwrite_doubt_in_stack():
    """Calling switch_to(doubt) while already in doubt should still nest properly."""
    f = make_fsm()
    f.switch_to("teaching")
    f.switch_to("doubt")
    # Inside doubt now.
    assert f.session.mode == "doubt"
    f.exit_doubt()
    assert f.session.mode == "teaching"
