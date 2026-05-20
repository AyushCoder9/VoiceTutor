"""Function-calling tools the LLM can invoke.

Each tool is:
  - A `ToolSpec` dataclass with name, description, and JSON-schema parameters
    (so we can hand them straight to Groq's function-calling API).
  - A bound implementation that closes over the active SessionMemory + DB + LLM.

The orchestration layer (`bot.py`) wires this up and exposes the resulting tool
list to Pipecat's LLM service.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from backend.agent.grader import grade_answer
from backend.agent.orchestrator import ModeFSM
from backend.agent.pronunciation import feedback_for_utterance, summarize_feedback
from backend.curriculum.loader import CURRICULUM, Lesson
from backend.memory.persistent import PersistentMemory
from backend.memory.session import SessionMemory


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# JSON schemas for the tools the LLM may call.
TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="start_lesson",
        description="Start a structured lesson. Use when the learner asks to learn a topic.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "topic keyword e.g. greetings, numbers, food"},
            },
            "required": ["topic"],
        },
    ),
    ToolSpec(
        name="start_quiz",
        description="Start a quiz on a topic. Use when the learner asks to be tested.",
        parameters={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "n_questions": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["topic"],
        },
    ),
    ToolSpec(
        name="grade_answer",
        description="Semantically grade a learner's spoken answer against an expected target.",
        parameters={
            "type": "object",
            "properties": {
                "expected": {"type": "string"},
                "got": {"type": "string"},
                "kind": {"type": "string", "enum": ["translation", "listening", "spoken_response", "open"]},
                "variants": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["expected", "got"],
        },
    ),
    ToolSpec(
        name="save_progress",
        description="Persist the learner's score on the current lesson.",
        parameters={
            "type": "object",
            "properties": {
                "lesson_id": {"type": "string"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["lesson_id", "score"],
        },
    ),
    ToolSpec(
        name="lookup_vocab",
        description="Look up a vocabulary word in the curriculum. Returns ES, EN, phonetic.",
        parameters={
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
        },
    ),
    ToolSpec(
        name="enter_doubt_mode",
        description="Pause current activity because the learner has a question. The previous mode is remembered.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="exit_doubt_mode",
        description="Resume what we were doing before the doubt was raised.",
        parameters={"type": "object", "properties": {}},
    ),
    ToolSpec(
        name="switch_mode",
        description="Switch the active learning mode.",
        parameters={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["teaching", "quiz", "conversation", "doubt", "idle"]},
            },
            "required": ["mode"],
        },
    ),
    ToolSpec(
        name="get_due_vocab",
        description="Get vocabulary due for spaced-repetition review for this user.",
        parameters={"type": "object", "properties": {"limit": {"type": "integer", "default": 5}}},
    ),
    ToolSpec(
        name="pronunciation_feedback",
        description="Get specific pronunciation feedback for an attempted Spanish phrase.",
        parameters={
            "type": "object",
            "properties": {
                "expected": {"type": "string"},
                "got": {"type": "string"},
            },
            "required": ["expected", "got"],
        },
    ),
    ToolSpec(
        name="end_session_summary",
        description="Produce an end-of-session summary of what was learned and weak areas.",
        parameters={"type": "object", "properties": {}},
    ),
]


def specs_for_llm() -> list[dict[str, Any]]:
    """OpenAI-style raw tool schemas (kept for tests + legacy callers)."""
    return [s.to_openai_schema() for s in TOOL_SPECS]


def tools_schema_for_llm():
    """Pipecat 1.x ToolsSchema for LIVE LLM use.

    We expose only 4 mode-transition tools. Llama's function-call parser is
    much more reliable with a small, focused tool set than with 11 tools.
    Other capabilities (grade_answer, save_progress, lookup_vocab,
    pronunciation_feedback, end_session_summary) are handled by deterministic
    Python in IntentRouter / curriculum logic — no LLM token cost, no parser
    flakiness, and the LLM still produces the spoken feedback.
    """
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    fns = [
        FunctionSchema(
            name="start_lesson",
            description="Begin a structured Spanish lesson on a topic the learner asked about (e.g. 'greetings', 'numbers', 'food').",
            properties={
                "topic": {"type": "string", "description": "Lesson topic keyword (e.g. greetings, numbers, food)."},
            },
            required=["topic"],
        ),
        FunctionSchema(
            name="start_quiz",
            description="Begin a quiz on a topic when the learner asks to be tested.",
            properties={
                "topic": {"type": "string", "description": "Quiz topic keyword."},
            },
            required=["topic"],
        ),
        FunctionSchema(
            name="enter_doubt_mode",
            description="Pause the current lesson or quiz because the learner asked a clarifying question. The prior activity is remembered.",
            properties={
                "reason": {"type": "string", "description": "Brief description of the learner's question."},
            },
            required=["reason"],
        ),
        FunctionSchema(
            name="exit_doubt_mode",
            description="Resume the lesson or quiz exactly where it was paused before the doubt.",
            properties={
                "ack": {"type": "string", "description": "Short acknowledgement, e.g. 'OK back to it'."},
            },
            required=["ack"],
        ),
    ]
    return ToolsSchema(standard_tools=fns)


# -------------------------------------------------------------------------------------
# Tool implementations — each takes a JSON args dict, returns a JSON-serialisable dict.
# -------------------------------------------------------------------------------------


class ToolRunner:
    """Bound tool dispatcher. Holds references to session / DB / LLM."""

    def __init__(
        self,
        session: SessionMemory,
        fsm: ModeFSM,
        memory: PersistentMemory,
        llm_grade_call: Callable[[str, str], Awaitable[str]] | None = None,
    ):
        self.session = session
        self.fsm = fsm
        self.memory = memory
        self.llm_grade_call = llm_grade_call

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await handler(args)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    # ---- start_lesson ----
    async def _tool_start_lesson(self, args: dict[str, Any]) -> dict[str, Any]:
        topic = args.get("topic", "")
        lesson = CURRICULUM.by_topic(topic) or (CURRICULUM.all()[0] if CURRICULUM.all() else None)
        if lesson is None:
            return {"error": "no lessons available"}
        self.fsm.switch_to("teaching")
        self.session.current_lesson_id = lesson.id
        self.session.lesson_step = "intro"
        for v in lesson.vocabulary:
            self.session.introduce_vocab(v.es)
        return _lesson_brief(lesson)

    # ---- start_quiz ----
    async def _tool_start_quiz(self, args: dict[str, Any]) -> dict[str, Any]:
        topic = args.get("topic", "")
        n = int(args.get("n_questions", 5))
        lesson = CURRICULUM.by_topic(topic) or (
            CURRICULUM.get(self.session.current_lesson_id) if self.session.current_lesson_id else None
        )
        if lesson is None:
            lesson = CURRICULUM.all()[0]

        # Build a mixed quiz from the lesson's checks + vocab translations.
        pool: list[dict[str, Any]] = []
        for c in lesson.checks:
            pool.append({"type": "translation", "prompt_en": c.prompt_en,
                         "expected_es": c.expected_es, "variants": c.accept_variants})
        for v in lesson.vocabulary[:8]:
            pool.append({"type": "translation", "prompt_en": f"How do you say '{v.en}' in Spanish?",
                         "expected_es": v.es, "variants": []})
            pool.append({"type": "listening", "prompt_es": v.es,
                         "expected_en": v.en, "variants": []})

        random.shuffle(pool)
        questions = pool[: max(1, n)]
        self.fsm.switch_to("quiz")
        self.session.quiz_topic = lesson.id
        self.session.quiz_questions = questions
        self.session.quiz_index = 0
        self.session.quiz_total = len(questions)
        self.session.quiz_score = 0
        return {
            "lesson_id": lesson.id,
            "n_questions": len(questions),
            "first_question": questions[0] if questions else None,
        }

    # ---- grade_answer ----
    async def _tool_grade_answer(self, args: dict[str, Any]) -> dict[str, Any]:
        expected = args["expected"]
        got = args["got"]
        kind = args.get("kind", "translation")
        variants = args.get("variants") or []
        result = await grade_answer(expected, got, variants, llm_call=self.llm_grade_call, kind=kind)

        # Side effects on session memory.
        if result.correct:
            self.session.add_success()
            self.session.quiz_score += 1 if self.session.mode == "quiz" else 0
            self.memory.record_vocab_attempt(self.session.user_id, expected, "es", True)
        else:
            self.session.add_mistake(
                kind="vocab" if kind == "translation" else "comprehension",
                expected=expected, got=got,
            )
            self.memory.log_mistake(
                user_id=self.session.user_id,
                kind="grading",
                expected=expected, got=got,
                lesson_id=self.session.current_lesson_id,
            )
            self.memory.record_vocab_attempt(self.session.user_id, expected, "es", False)

        if self.session.mode == "quiz":
            self.session.quiz_index += 1
        return result.as_dict()

    # ---- save_progress ----
    async def _tool_save_progress(self, args: dict[str, Any]) -> dict[str, Any]:
        lesson_id = args["lesson_id"]
        score = float(args["score"])
        self.memory.record_lesson_score(self.session.user_id, lesson_id, score)
        return {"saved": True, "lesson_id": lesson_id, "score": score}

    # ---- lookup_vocab ----
    async def _tool_lookup_vocab(self, args: dict[str, Any]) -> dict[str, Any]:
        v = CURRICULUM.find_vocab(args["word"])
        if v is None:
            return {"found": False, "word": args["word"]}
        return {"found": True, "es": v.es, "en": v.en, "phonetic": v.phonetic}

    # ---- enter_doubt_mode ----
    async def _tool_enter_doubt_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self.fsm.switch_to("doubt")
        return {"ok": r.ok, "mode": r.mode, "persona": r.persona}

    # ---- exit_doubt_mode ----
    async def _tool_exit_doubt_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self.fsm.exit_doubt()
        return {"ok": r.ok, "mode": r.mode, "persona": r.persona,
                "resume_lesson_id": self.session.current_lesson_id,
                "resume_step": self.session.lesson_step}

    # ---- switch_mode ----
    async def _tool_switch_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        r = self.fsm.switch_to(args["mode"])
        return {"ok": r.ok, "mode": r.mode, "persona": r.persona, "note": r.note}

    # ---- get_due_vocab ----
    async def _tool_get_due_vocab(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = int(args.get("limit", 5))
        due = self.memory.due_vocab(self.session.user_id, limit=limit)
        return {"due": due, "count": len(due)}

    # ---- pronunciation_feedback ----
    async def _tool_pronunciation_feedback(self, args: dict[str, Any]) -> dict[str, Any]:
        expected = args["expected"]
        got = args["got"]
        items = feedback_for_utterance(expected.split(), got, word_confidences=None)
        return {
            "summary": summarize_feedback(items),
            "per_word": [i.as_dict() for i in items],
        }

    # ---- end_session_summary ----
    async def _tool_end_session_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "turns": len(self.session.turns),
            "mode": self.session.mode,
            "lesson": self.session.current_lesson_id,
            "vocab_introduced": self.session.introduced_vocab,
            "mistakes": self.session.session_mistakes,
            "confidence": round(self.session.confidence_score, 2),
            "quiz_score": f"{self.session.quiz_score}/{self.session.quiz_total}" if self.session.quiz_total else None,
        }


def _lesson_brief(lesson: Lesson) -> dict[str, Any]:
    return {
        "lesson_id": lesson.id,
        "title": lesson.title,
        "objective": lesson.objective,
        "first_vocab": [{"es": v.es, "en": v.en, "phonetic": v.phonetic} for v in lesson.vocabulary[:5]],
        "grammar_notes": lesson.grammar_notes,
        "examples": lesson.examples[:2],
    }


def safe_json(data: Any) -> str:
    """JSON-stringify a tool result for embedding in an LLM message."""
    return json.dumps(data, ensure_ascii=False)
