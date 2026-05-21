from backend.agent.pronunciation import (
    WORD_PHONEME_HINTS,
    detect_tricky,
    feedback_for_utterance,
    score_word,
    summarize_feedback,
)


def test_detect_rr_returns_rolled_r_hint():
    hints = detect_tricky("perro")
    assert any("trill" in h.lower() or "rr" in h.lower() or "roll" in h.lower() for h in hints)


def test_detect_silent_h():
    hints = detect_tricky("hola")
    assert any("silent" in h.lower() or "h" in h.lower() for h in hints)


def test_per_word_hints_take_priority():
    """Specific per-word hints should appear before general pattern hints."""
    hints = detect_tricky("hola")
    assert hints, "expected some hints for hola"
    # The very first hint should be the word-specific one.
    assert "aspirate" in hints[0].lower() or "silent" in hints[0].lower()


def test_clear_word_no_hint_ok_severity():
    fb = score_word("casa", 0.99)
    assert fb.severity == "ok"


def test_low_confidence_word_major_severity():
    fb = score_word("perro", 0.3)
    assert fb.severity == "major"


def test_summary_promotes_major_to_focus():
    items = [
        score_word("hola", 0.99),
        score_word("perro", 0.3),
    ]
    summary = summarize_feedback(items)
    assert "perro" in summary


def test_feedback_for_utterance_returns_per_word():
    items = feedback_for_utterance(
        ["quisiera", "un", "café"],
        "quisiera un cafe",
        word_confidences={"quisiera": 0.9, "un": 0.95, "café": 0.6},
    )
    assert len(items) == 3


def test_word_phoneme_hints_dict_well_formed():
    """All hints should be non-empty strings."""
    for word, hints in WORD_PHONEME_HINTS.items():
        assert hints, f"{word} has no hints"
        for label, text in hints:
            assert isinstance(label, str) and label
            assert isinstance(text, str) and text
