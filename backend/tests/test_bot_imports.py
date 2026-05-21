"""Smoke tests for bot module imports + class construction.

These don't run a live pipeline (that needs Pipecat audio frames) but they
verify the module compiles and the LanguageTutorBot can be instantiated
without external services.
"""

from __future__ import annotations

import pytest


def test_bot_module_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "bot.db"))
    from backend.bot import LanguageTutorBot  # noqa: F401


def test_bot_constructs_with_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "bot.db"))
    from backend.bot import LanguageTutorBot

    bot = LanguageTutorBot()
    assert bot.user_id
    assert bot.session.mode == "idle"
    assert bot.fsm is not None
    assert bot.memory is not None
    assert bot.prosody is not None


def test_bot_construct_with_explicit_user(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "bot.db"))
    from backend.bot import LanguageTutorBot

    bot = LanguageTutorBot(
        user_id="explicit-user",
        user_name="Explicit",
        native_lang="en",
        target_lang="es",
    )
    assert bot.user_id == "explicit-user"
    user = bot.memory.get_user("explicit-user")
    assert user["name"] == "Explicit"


def test_bot_initial_prosody_neutral(monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "bot.db"))
    from backend.bot import LanguageTutorBot

    bot = LanguageTutorBot()
    reading = bot.prosody.reading()
    assert reading.label == "neutral"


def test_tools_schema_has_only_four_essential_tools():
    """We curated the tool set down to 4 to reduce Llama parser pressure.
    Don't accidentally regress to all 11.
    """
    from backend.agent.tools import tools_schema_for_llm
    ts = tools_schema_for_llm()
    assert len(ts.standard_tools) == 4
    names = {f.name for f in ts.standard_tools}
    assert names == {
        "start_lesson", "start_quiz", "enter_doubt_mode", "exit_doubt_mode"
    }
