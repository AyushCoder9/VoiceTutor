"""Semantic answer grading.

Two-tier strategy:
1. Cheap deterministic checks first (normalization + variant match) — instant, no token cost.
2. LLM fallback for ambiguous cases — semantic similarity check via prompt.

Why two-tier: per spec, answers must be graded semantically (not exact-string), but we
don't want to spend an LLM round-trip on "yes, that matches the variants list".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass
class GradeResult:
    correct: bool
    score: float          # 0.0 .. 1.0
    method: str           # "exact" | "variant" | "fuzzy" | "llm" | "empty"
    expected: str
    got: str
    feedback: str | None = None  # short specific note for the learner

    def as_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "score": round(self.score, 3),
            "method": self.method,
            "expected": self.expected,
            "got": self.got,
            "feedback": self.feedback,
        }


_PUNCT_RX = re.compile(r"[¿¡!?,;:.\"'()\[\]]")
_WS_RX = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Lowercase, strip accents, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    # NFD splits accents off — drop the combining marks.
    nfd = unicodedata.normalize("NFD", text)
    no_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    no_punct = _PUNCT_RX.sub(" ", no_accents.lower())
    return _WS_RX.sub(" ", no_punct).strip()


def token_jaccard(a: str, b: str) -> float:
    ta = set(normalise(a).split())
    tb = set(normalise(b).split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def grade_deterministic(expected: str, got: str, variants: list[str] | None = None) -> GradeResult | None:
    """Return a GradeResult only if confidence is high; else None to defer to LLM."""
    got_norm = normalise(got)
    if not got_norm:
        return GradeResult(False, 0.0, "empty", expected, got, feedback="I didn't catch that — could you try again?")

    expected_norm = normalise(expected)
    if got_norm == expected_norm:
        return GradeResult(True, 1.0, "exact", expected, got)

    candidates = [expected_norm] + [normalise(v) for v in (variants or [])]
    if got_norm in candidates:
        return GradeResult(True, 1.0, "variant", expected, got)

    # Jaccard above 0.75 = near match, accept; below 0.35 = clearly wrong.
    j = max(token_jaccard(got, c) for c in candidates)
    if j >= 0.75:
        return GradeResult(True, j, "fuzzy", expected, got, feedback="Very close — that works.")
    if j <= 0.35:
        return GradeResult(False, j, "fuzzy", expected, got, feedback=f"I was looking for: '{expected}'.")
    return None  # ambiguous — let LLM decide


async def grade_with_llm(
    expected: str,
    got: str,
    *,
    llm_call,  # async callable: (system_prompt, user_prompt) -> str
    kind: str = "translation",
) -> GradeResult:
    """Async LLM-backed grade for ambiguous answers. Caller injects llm_call."""
    system = (
        "You are a Spanish language tutor grading a learner's answer. "
        "Return ONLY a JSON object: "
        '{"correct": true/false, "score": 0.0-1.0, "feedback": "<one short specific sentence>"}. '
        "Equivalent paraphrases ARE correct. Minor accents / capitalization do NOT matter."
    )
    user = (
        f"Question type: {kind}\n"
        f"Expected answer: {expected}\n"
        f"Learner's answer: {got}\n"
        "Grade it."
    )

    raw = await llm_call(system, user)
    import json as _json

    try:
        # tolerate a stray code-fence
        body = raw.strip()
        if body.startswith("```"):
            body = body.strip("`")
            body = body.split("\n", 1)[1] if "\n" in body else body
        data = _json.loads(body)
        return GradeResult(
            correct=bool(data.get("correct", False)),
            score=float(data.get("score", 0.0)),
            method="llm",
            expected=expected,
            got=got,
            feedback=data.get("feedback"),
        )
    except Exception:
        # last-ditch heuristic
        j = token_jaccard(expected, got)
        return GradeResult(j >= 0.5, j, "llm", expected, got, feedback="(grader fell back to heuristic)")


async def grade_answer(
    expected: str,
    got: str,
    variants: list[str] | None = None,
    *,
    llm_call=None,
    kind: str = "translation",
) -> GradeResult:
    """Top-level grading: deterministic first, LLM only for ambiguous."""
    fast = grade_deterministic(expected, got, variants)
    if fast is not None:
        return fast
    if llm_call is None:
        # Defensive fallback when no LLM is wired — middle of the road.
        return GradeResult(False, 0.5, "fuzzy", expected, got,
                           feedback=f"Almost — try: '{expected}'.")
    return await grade_with_llm(expected, got, llm_call=llm_call, kind=kind)
