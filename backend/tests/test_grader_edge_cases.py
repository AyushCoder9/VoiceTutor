"""Boundary + adversarial cases for the semantic grader."""

import pytest

from backend.agent.grader import (
    grade_answer,
    grade_deterministic,
    normalise,
    token_jaccard,
)


def test_normalise_unicode_accents():
    assert normalise("café") == "cafe"
    assert normalise("Mañana") == "manana"
    assert normalise("¡Hola, María!") == "hola maria"


def test_normalise_inverted_spanish_marks():
    assert normalise("¿Cómo estás?") == "como estas"
    assert normalise("¡Qué bien!") == "que bien"


def test_normalise_multiple_whitespace_collapsed():
    assert normalise("   Hola   mundo   ") == "hola mundo"
    assert normalise("\tHola\nmundo\n") == "hola mundo"


def test_normalise_none_returns_empty():
    assert normalise(None) == ""
    assert normalise("") == ""


def test_token_jaccard_symmetric():
    a, b = "uno dos tres", "tres dos uno"
    assert token_jaccard(a, b) == token_jaccard(b, a) == 1.0


def test_token_jaccard_empty_strings():
    assert token_jaccard("", "") == 1.0
    assert token_jaccard("uno", "") == 0.0
    assert token_jaccard("", "uno") == 0.0


def test_grade_exact_case_insensitive():
    r = grade_deterministic("HOLA", "hola")
    assert r and r.correct


def test_grade_with_accent_difference():
    """Accents should not block acceptance."""
    r = grade_deterministic("café", "cafe")
    assert r and r.correct


def test_grade_with_punctuation_difference():
    r = grade_deterministic("¿Cómo estás?", "como estas")
    assert r and r.correct


def test_grade_empty_input_returns_empty_method():
    r = grade_deterministic("hola", "")
    assert r and not r.correct
    assert r.method == "empty"


def test_grade_variant_match_normalised():
    r = grade_deterministic(
        "Hola, me llamo Alex",
        "hola me llamo alex",
        variants=["hola, me llamo alex"],
    )
    assert r and r.correct
    assert r.method in {"exact", "variant", "fuzzy"}


def test_grade_obvious_wrong():
    r = grade_deterministic("hola", "goodbye forever")
    assert r and not r.correct


@pytest.mark.asyncio
async def test_grade_answer_returns_feedback_string_or_none():
    """API contract: feedback is always None or a string."""
    r = await grade_answer("hola", "hola")
    assert r.feedback is None or isinstance(r.feedback, str)


def test_grade_feedback_on_empty_input_has_hint():
    r = grade_deterministic("hola", "")
    assert r and r.feedback and len(r.feedback) > 0
