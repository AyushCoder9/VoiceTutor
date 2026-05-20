"""Short-term in-memory session state.

Holds per-conversation state that does NOT need to survive a restart:
- current mode + sub-state of the FSM
- current lesson + position within it
- mistakes made *this session*
- vocab introduced this session
- recent topics
- frustration counter (bonus feature)

Why in-memory: a session is by definition transient. Anything worth keeping
gets promoted to `PersistentMemory` via tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TurnRecord:
    role: str  # "user" | "assistant"
    text: str
    mode: str
    language: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))


@dataclass
class SessionMemory:
    user_id: str
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))

    # FSM
    mode: str = "idle"  # idle | teaching | quiz | conversation | doubt
    prior_mode: str | None = None  # for returning from doubt
    persona: str = "teacher"  # teacher | examiner | companion
    current_lesson_id: str | None = None
    lesson_step: str = "intro"  # intro | explain | example | practice | check | done

    # Pedagogy
    confidence_score: float = 0.5  # 0..1 -- drives adaptive difficulty
    consecutive_failures: int = 0
    frustration_score: int = 0  # ticks up on repeated mistakes / short angry utterances

    # Quiz state
    quiz_topic: str | None = None
    quiz_questions: list[dict[str, Any]] = field(default_factory=list)
    quiz_index: int = 0
    quiz_score: int = 0
    quiz_total: int = 0

    # Memory
    introduced_vocab: list[str] = field(default_factory=list)  # ES words introduced this session
    session_mistakes: list[dict[str, Any]] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)

    # Bookkeeping for doubt return
    doubt_stack: list[dict[str, Any]] = field(default_factory=list)

    # Two-step voice confirmation for destructive actions.
    # Set when the bot asks "say yes to confirm reset". Cleared on yes/cancel.
    pending_confirmation: str | None = None  # e.g. "reset_all", "reset_weak_spots"

    # ---- mutators ----
    def add_turn(self, role: str, text: str, language: str | None = None) -> None:
        self.turns.append(TurnRecord(role=role, text=text, mode=self.mode, language=language))
        if role == "user" and len(text.strip().split()) <= 3:
            # very short user replies after a failure can indicate frustration
            self.frustration_score += 1 if self.consecutive_failures > 0 else 0

    def introduce_vocab(self, word: str) -> None:
        w = word.strip().lower()
        if w and w not in (x.lower() for x in self.introduced_vocab):
            self.introduced_vocab.append(word)

    def add_mistake(self, kind: str, expected: str | None, got: str | None, note: str | None = None) -> None:
        self.session_mistakes.append(
            {"kind": kind, "expected": expected, "got": got, "note": note,
             "at": datetime.utcnow().isoformat(timespec="seconds")}
        )
        self.consecutive_failures += 1
        # adaptive: confidence drops on mistake
        self.confidence_score = max(0.0, self.confidence_score - 0.1)

    def add_success(self) -> None:
        self.consecutive_failures = 0
        self.confidence_score = min(1.0, self.confidence_score + 0.08)
        self.frustration_score = max(0, self.frustration_score - 1)

    def push_doubt(self) -> None:
        self.doubt_stack.append({
            "mode": self.mode,
            "lesson_step": self.lesson_step,
            "current_lesson_id": self.current_lesson_id,
            "quiz_index": self.quiz_index,
        })
        self.prior_mode = self.mode
        self.mode = "doubt"

    def pop_doubt(self) -> None:
        if not self.doubt_stack:
            self.mode = self.prior_mode or "idle"
            return
        snap = self.doubt_stack.pop()
        self.mode = snap["mode"]
        self.lesson_step = snap["lesson_step"]
        self.current_lesson_id = snap["current_lesson_id"]
        self.quiz_index = snap["quiz_index"]

    def is_frustrated(self) -> bool:
        return self.frustration_score >= 3 or self.consecutive_failures >= 3

    def context_summary(self) -> str:
        """Compact summary fed into the LLM each turn."""
        bits = [
            f"mode={self.mode}",
            f"persona={self.persona}",
            f"confidence={self.confidence_score:.2f}",
        ]
        if self.current_lesson_id:
            bits.append(f"lesson={self.current_lesson_id}/{self.lesson_step}")
        if self.mode == "quiz":
            bits.append(f"quiz={self.quiz_index}/{self.quiz_total} score={self.quiz_score}")
        if self.introduced_vocab:
            bits.append(f"vocab_today={','.join(self.introduced_vocab[-8:])}")
        if self.is_frustrated():
            bits.append("frustrated=true")
        if self.session_mistakes:
            recent = self.session_mistakes[-3:]
            bits.append(f"recent_mistakes={recent}")
        return "; ".join(bits)
