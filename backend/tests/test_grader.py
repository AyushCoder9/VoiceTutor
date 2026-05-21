"""Tests for the semantic grader.

We test the deterministic layer thoroughly here — the LLM-backed fallback is
exercised by the e2e harness with a stub LLM.
"""

import pytest

from backend.agent.grader import (
    GradeResult,
    grade_answer,
    grade_deterministic,
    normalise,
    token_jaccard,
)


def test_normalise_strips_accents_and_punct():
    assert normalise("¡Hola, María!") == "hola maria"
    assert normalise("¿Cómo estás?") == "como estas"


def test_exact_match_is_correct():
    r = grade_deterministic("hola", "hola")
    assert r and r.correct and r.method == "exact"


def test_variant_match_is_correct():
    r = grade_deterministic("Hola, me llamo Alex", "hola me llamo alex", variants=["hola me llamo alex"])
    assert r and r.correct


def test_accent_insensitive():
    r = grade_deterministic("¿Cómo te llamas?", "como te llamas")
    assert r and r.correct


def test_clearly_wrong_is_rejected():
    r = grade_deterministic("hola", "adiós completamente diferente")
    assert r and not r.correct


def test_jaccard_high_overlap_accepted_as_fuzzy():
    r = grade_deterministic("la cuenta por favor", "la cuenta, por favor", variants=["la cuenta por favor"])
    assert r and r.correct


def test_empty_input_returns_specific_feedback():
    r = grade_deterministic("hola", "")
    assert r and not r.correct and r.method == "empty"
    assert "again" in (r.feedback or "").lower()


def test_token_jaccard_basic():
    assert token_jaccard("a b c", "a b c") == 1.0
    assert token_jaccard("a b", "c d") == 0.0
    assert 0.4 <= token_jaccard("a b c", "a b d") <= 0.7


@pytest.mark.asyncio
async def test_grade_answer_async_path_falls_back_to_deterministic_when_no_llm():
    # Ambiguous → would defer to LLM, but we pass none.
    res = await grade_answer("quisiera un café", "querría un cafecito", llm_call=None)
    assert isinstance(res, GradeResult)
    # Deterministic enough to either accept or reject — must not crash.
    assert 0.0 <= res.score <= 1.0


@pytest.mark.asyncio
async def test_grade_answer_uses_llm_for_ambiguous():
    async def fake_llm(system: str, user: str) -> str:
        return '{"correct": true, "score": 0.95, "feedback": "Synonym is fine."}'

    # Mid-Jaccard answer → ambiguous → goes to LLM.
    res = await grade_answer("quisiera un café", "deseo un café", llm_call=fake_llm)
    assert res.correct and res.method == "llm"
    assert "Synonym" in (res.feedback or "")
