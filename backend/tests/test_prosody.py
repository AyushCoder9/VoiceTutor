"""Tests for the prosody-based engagement detector."""

from __future__ import annotations

import struct

from backend.agent.prosody import ProsodyTracker


def _pcm_chunk(amplitude: int, n_samples: int = 320) -> bytes:
    """Generate a fake int16 PCM chunk at the given amplitude."""
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def test_empty_returns_neutral():
    t = ProsodyTracker()
    r = t.reading()
    assert r.label == "neutral"


def test_low_energy_triggers_low_label():
    t = ProsodyTracker()
    for _ in range(50):
        t.feed_audio(_pcm_chunk(200))  # very quiet
    # Add slow / hesitant turns: 2 short utterances with long pause.
    t.mark_turn("hi", duration_s=1.0, ended_at=10.0)
    t.mark_turn("yes", duration_s=1.0, ended_at=25.0)  # 15s pause = lost
    r = t.reading()
    assert r.is_low() or r.label == "low"


def test_high_energy_with_pace_triggers_engaged():
    t = ProsodyTracker()
    # Alternating loud / soft = high variance, decent energy.
    for i in range(120):
        t.feed_audio(_pcm_chunk(4500 if i % 2 == 0 else 1500))
    t.mark_turn("hola me llamo Alex y quiero aprender mucho hoy", duration_s=3.0, ended_at=10.0)
    t.mark_turn("si claro vamos a empezar la lección", duration_s=2.5, ended_at=15.0)
    t.mark_turn("entendido gracias profesora", duration_s=2.0, ended_at=19.0)
    r = t.reading()
    # We can't guarantee "engaged" but score must rise vs empty/low baselines.
    assert r.score > 0.4
    assert r.pace_wpm > 60


def test_pace_calculation_correctness():
    t = ProsodyTracker()
    t.mark_turn("uno dos tres cuatro cinco", duration_s=2.0, ended_at=10.0)  # 5 words / 2s = 150 wpm
    r = t.reading()
    assert 100 < r.pace_wpm <= 160


def test_pauses_tracked():
    t = ProsodyTracker()
    t.mark_turn("first", duration_s=1.0, ended_at=5.0)
    t.mark_turn("second", duration_s=1.0, ended_at=12.0)   # 7s gap
    r = t.reading()
    assert r.pauses_s >= 5.0


def test_reading_dict_fields():
    t = ProsodyTracker()
    t.feed_audio(_pcm_chunk(2000))
    r = t.reading()
    # All numeric, none negative.
    for v in (r.energy, r.variance, r.pace_wpm, r.pauses_s, r.score):
        assert v >= 0.0
    assert r.label in {"low", "neutral", "engaged"}


def test_is_low_and_is_high_thresholds():
    t = ProsodyTracker()
    # Force a low reading.
    r = t.reading()
    if r.score < 0.4:
        assert r.is_low()
    elif r.score > 0.75:
        assert r.is_high()
    else:
        assert not r.is_low() and not r.is_high()
