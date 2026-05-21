"""System-prompt builder tests."""

from backend.agent.prompts import (
    BASE_PERSONA,
    MODE_CONVERSATION,
    MODE_DOUBT,
    MODE_QUIZ,
    MODE_TEACHING,
    greeting_for_returning_user,
    system_prompt_for,
)


def test_base_persona_constraints():
    """The persona must enforce the language-switching rule."""
    assert "ENGLISH by default" in BASE_PERSONA
    assert "Spanish ONLY" in BASE_PERSONA
    # No-tools constraint — we use IntentRouter
    assert "harness" in BASE_PERSONA.lower() or "routes" in BASE_PERSONA.lower()


def test_each_mode_overlay_present():
    for label, overlay in [
        ("TEACHING MODE", MODE_TEACHING),
        ("QUIZ MODE", MODE_QUIZ),
        ("CONVERSATION MODE", MODE_CONVERSATION),
        ("DOUBT MODE", MODE_DOUBT),
    ]:
        assert label in overlay, f"{label} missing from overlay"


def test_system_prompt_idle_returns_base_only():
    prompt = system_prompt_for("idle")
    assert BASE_PERSONA in prompt
    # Idle mode has no overlay → none of the mode tags present.
    for tag in ("TEACHING MODE", "QUIZ MODE", "CONVERSATION MODE", "DOUBT MODE"):
        assert tag not in prompt


def test_system_prompt_teaching_includes_teaching_overlay():
    prompt = system_prompt_for("teaching")
    assert "TEACHING MODE" in prompt
    assert BASE_PERSONA in prompt


def test_system_prompt_quiz_includes_quiz_overlay():
    prompt = system_prompt_for("quiz")
    assert "QUIZ MODE" in prompt


def test_system_prompt_doubt_includes_doubt_overlay():
    prompt = system_prompt_for("doubt")
    assert "DOUBT MODE" in prompt


def test_system_prompt_frustrated_adds_addendum():
    prompt = system_prompt_for("teaching", frustrated=True)
    assert "frustrated" in prompt.lower()
    assert "slow" in prompt.lower() or "encourage" in prompt.lower()


def test_system_prompt_context_summary_injected():
    prompt = system_prompt_for("teaching", context_summary="mode=teaching; confidence=0.42")
    assert "STATE:" in prompt
    assert "confidence=0.42" in prompt


def test_greeting_is_question_shaped():
    """Greeting must end with a question to prompt user response."""
    greeting = greeting_for_returning_user("Alex")
    assert greeting.strip().endswith("?")
    assert "Alex" in greeting


def test_greeting_lists_options_not_auto_acting():
    """The greeting should offer choices, NOT presume an action."""
    greeting = greeting_for_returning_user("Alex")
    lower = greeting.lower()
    # Should mention multiple modes so learner knows the options.
    assert any(w in lower for w in ("lesson", "learn"))
    assert any(w in lower for w in ("quiz", "test"))
    assert any(w in lower for w in ("conversation", "chat", "talk"))


def test_unknown_mode_falls_back_to_base():
    """Unknown mode names should not crash, just return base persona."""
    prompt = system_prompt_for("nonsense_mode")
    assert BASE_PERSONA in prompt
