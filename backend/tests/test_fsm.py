from backend.agent.orchestrator import MODE_TO_PERSONA, ModeFSM, VALID_MODES
from backend.memory.session import SessionMemory


def make_fsm():
    return ModeFSM(SessionMemory(user_id="test"))


def test_default_mode_is_idle():
    s = SessionMemory(user_id="x")
    assert s.mode == "idle"
    assert s.persona == "teacher"


def test_switch_modes():
    f = make_fsm()
    r = f.switch_to("teaching")
    assert r.ok and r.mode == "teaching"
    assert f.session.persona == "teacher"
    r = f.switch_to("quiz")
    assert r.ok and r.mode == "quiz"
    assert f.session.persona == "examiner"
    r = f.switch_to("conversation")
    assert r.ok and r.mode == "conversation"
    assert f.session.persona == "companion"


def test_invalid_mode_rejected():
    r = make_fsm().switch_to("rocket-launch")
    assert not r.ok


def test_doubt_push_and_pop_resumes_prior_mode():
    f = make_fsm()
    f.switch_to("teaching")
    f.session.current_lesson_id = "greetings-001"
    f.session.lesson_step = "practice"
    r = f.switch_to("doubt")
    assert r.ok and r.mode == "doubt"
    # exit returns to teaching at the same step
    r2 = f.exit_doubt()
    assert r2.ok
    assert f.session.mode == "teaching"
    assert f.session.lesson_step == "practice"
    assert f.session.current_lesson_id == "greetings-001"


def test_doubt_pop_when_not_in_doubt_fails():
    r = make_fsm().exit_doubt()
    assert not r.ok


def test_lesson_step_advances():
    f = make_fsm()
    f.switch_to("teaching")
    assert f.session.lesson_step == "intro"
    assert f.advance_lesson() == "explain"
    assert f.advance_lesson() == "example"
    assert f.advance_lesson() == "practice"
    assert f.advance_lesson() == "check"
    assert f.advance_lesson() == "done"
    assert f.lesson_complete()


def test_persona_table_covers_all_modes():
    for m in VALID_MODES:
        assert m in MODE_TO_PERSONA


def test_system_prompt_changes_with_mode():
    f = make_fsm()
    p_idle = f.current_system_prompt()
    f.switch_to("teaching")
    p_teach = f.current_system_prompt()
    f.switch_to("quiz")
    p_quiz = f.current_system_prompt()
    assert p_idle != p_teach
    assert p_teach != p_quiz
    assert "TEACHING MODE" in p_teach
    assert "QUIZ MODE" in p_quiz
