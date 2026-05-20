"""Curriculum loader — reads `lessons.json` and exposes typed access helpers.

Why a separate loader: we want the curriculum content to live as data (JSON), not
code, so non-engineers (or LLM-authored extensions) can add lessons without
touching Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CURRICULUM_PATH = Path(__file__).parent / "lessons.json"


@dataclass(frozen=True)
class VocabItem:
    es: str
    en: str
    phonetic: str


@dataclass(frozen=True)
class Check:
    prompt_en: str
    expected_es: str
    accept_variants: list[str]


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    level: str
    estimated_minutes: int
    objective: str
    vocabulary: list[VocabItem]
    grammar_notes: list[str]
    examples: list[dict[str, str]]
    practice_prompts: list[str]
    checks: list[Check]

    def vocab_words(self) -> list[str]:
        return [v.es for v in self.vocabulary]


class Curriculum:
    """In-memory curriculum cache. Loaded once at import time."""

    def __init__(self, payload: dict[str, Any]):
        self.language: str = payload["language"]
        self.native_language: str = payload["native_language"]
        self.version: int = payload["version"]
        self._lessons: dict[str, Lesson] = {}
        for raw in payload["lessons"]:
            lesson = Lesson(
                id=raw["id"],
                title=raw["title"],
                level=raw["level"],
                estimated_minutes=raw["estimated_minutes"],
                objective=raw["objective"],
                vocabulary=[VocabItem(**v) for v in raw["vocabulary"]],
                grammar_notes=list(raw["grammar_notes"]),
                examples=list(raw["examples"]),
                practice_prompts=list(raw["practice_prompts"]),
                checks=[Check(**c) for c in raw["checks"]],
            )
            self._lessons[lesson.id] = lesson

    def get(self, lesson_id: str) -> Lesson | None:
        return self._lessons.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._lessons.values())

    # Hand-tuned topic-keyword index so the user's free-form utterance
    # ("teach me about my family", "let's count", etc.) maps to a lesson.
    _TOPIC_KEYWORDS = {
        "greetings-001":     ["greeting", "greetings", "hello", "hi ", "introduce", "introduction", "name", "saludo", "saludos"],
        "numbers-001":       ["number", "numbers", "count", "counting", "numero", "numeros", "1 to", "1-20", "twenty"],
        "ordering-food-001": ["food", "restaurant", "order", "menu", "coffee", "eat", "comida", "pedir", "drink"],
        "family-001":        ["family", "familia", "parents", "brother", "sister", "mother", "father", "siblings", "relatives"],
        "days-time-001":     ["day", "days", "week", "time", "hour", "clock", "lunes", "today", "tomorrow", "schedule"],
        "directions-001":    ["direction", "directions", "where is", "way", "left", "right", "turn", "lost", "find"],
    }

    def by_topic(self, topic: str) -> Lesson | None:
        """Fuzzy lookup by keyword. Falls back to substring match on id/title."""
        t = topic.lower().strip()
        if not t:
            return None
        # Pass 1: hand-tuned keywords (more accurate).
        for lesson_id, keywords in self._TOPIC_KEYWORDS.items():
            if any(kw in t for kw in keywords):
                lesson = self._lessons.get(lesson_id)
                if lesson:
                    return lesson
        # Pass 2: substring match on id/title (catch-all).
        for lesson in self._lessons.values():
            haystack = f"{lesson.id} {lesson.title}".lower()
            if t in haystack or any(w in haystack for w in t.split() if len(w) > 2):
                return lesson
        return None

    def find_vocab(self, word: str) -> VocabItem | None:
        word = word.lower().strip()
        for lesson in self._lessons.values():
            for v in lesson.vocabulary:
                if v.es.lower() == word or v.en.lower() == word:
                    return v
        return None


def load_curriculum(path: Path | None = None) -> Curriculum:
    src = path or _CURRICULUM_PATH
    with src.open("r", encoding="utf-8") as f:
        return Curriculum(json.load(f))


# Module-level singleton — cheap, immutable.
CURRICULUM = load_curriculum()
