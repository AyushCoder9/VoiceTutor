"""Mode FSM — the brain of the agent.

Why a hand-rolled FSM (chose over LangGraph) — see WRITEUP D7. Single-agent,
small set of modes, transitions auditable in observability logs.

Transitions:
    idle ─→ teaching, quiz, conversation
    teaching ─→ quiz, idle, doubt(push)
    quiz ─→ teaching, idle, doubt(push)
    conversation ─→ idle, doubt(push)
    doubt ─→ pops back to prior mode

The FSM doesn't drive the LLM — it tracks state, returns the appropriate system
prompt, and validates transitions. The LLM emits a switch_mode() tool call when
it wants to change modes (e.g. user said "let's do a quiz").
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.agent.prompts import system_prompt_for
from backend.memory.session import SessionMemory

VALID_MODES = {"idle", "teaching", "quiz", "conversation", "doubt"}
VALID_PERSONAS = {"teacher", "examiner", "companion"}

# Persona naturally maps from mode for our 3-persona handoff bonus feature.
MODE_TO_PERSONA = {
    "idle": "teacher",
    "teaching": "teacher",
    "quiz": "examiner",
    "conversation": "companion",
    "doubt": "teacher",
}


@dataclass
class TransitionResult:
    ok: bool
    mode: str
    persona: str
    note: str | None = None


class ModeFSM:
    """Wraps a SessionMemory and enforces legal mode transitions."""

    def __init__(self, session: SessionMemory):
        self.session = session

    def current_system_prompt(self) -> str:
        return system_prompt_for(
            mode=self.session.mode,
            frustrated=self.session.is_frustrated(),
            context_summary=self.session.context_summary(),
        )

    def switch_to(self, mode: str) -> TransitionResult:
        if mode not in VALID_MODES:
            return TransitionResult(False, self.session.mode, self.session.persona,
                                    note=f"Unknown mode '{mode}'.")
        if mode == "doubt":
            self.session.push_doubt()
        else:
            # Leaving a non-doubt mode resets sub-state cleanly.
            self.session.mode = mode
            self.session.persona = MODE_TO_PERSONA.get(mode, "teacher")
            self.session.lesson_step = "intro"
            if mode != "quiz":
                self.session.quiz_questions.clear()
                self.session.quiz_index = 0
                self.session.quiz_score = 0
                self.session.quiz_total = 0
        return TransitionResult(True, self.session.mode, self.session.persona)

    def exit_doubt(self) -> TransitionResult:
        if self.session.mode != "doubt":
            return TransitionResult(False, self.session.mode, self.session.persona,
                                    note="Not in doubt mode.")
        self.session.pop_doubt()
        self.session.persona = MODE_TO_PERSONA.get(self.session.mode, "teacher")
        return TransitionResult(True, self.session.mode, self.session.persona)

    # ---- teaching sub-FSM ----
    LESSON_STEPS = ["intro", "explain", "example", "practice", "check", "done"]

    def advance_lesson(self) -> str:
        idx = self.LESSON_STEPS.index(self.session.lesson_step)
        if idx < len(self.LESSON_STEPS) - 1:
            self.session.lesson_step = self.LESSON_STEPS[idx + 1]
        return self.session.lesson_step

    def repeat_lesson_step(self) -> str:
        # Adaptive: on low confidence, we explicitly do NOT advance.
        return self.session.lesson_step

    def lesson_complete(self) -> bool:
        return self.session.lesson_step == "done"
