"""Prosody-based engagement detection (BONUS feature).

We can't run heavy ML (librosa, Wav2Vec2) on free-tier compute, but a
lightweight RMS-variance + pause analysis catches the obvious cases:

- Low overall energy → "tired / disengaged"
- High variance + fast pace → "engaged / excited"
- Long pauses + low energy → "lost / hesitant"

Used by the FSM to nudge the system prompt: when engagement drops, the
LLM is told to speed up praise + shorten replies; when it spikes, the
LLM can add complexity.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass
class EngagementReading:
    energy: float        # 0..1 normalised RMS over recent window
    variance: float      # 0..1 — high = animated speech
    pace_wpm: float      # spoken words per minute (estimate)
    pauses_s: float      # avg silence between user turns (sec)
    score: float         # composite engagement 0..1; >0.6 = engaged
    label: str           # "engaged" | "neutral" | "low"

    def is_low(self) -> bool:
        return self.score < 0.4

    def is_high(self) -> bool:
        return self.score > 0.75


class ProsodyTracker:
    """Sliding window of recent user audio characteristics.

    Push raw int16 PCM bytes via `feed_audio` when audio reaches STT, and
    call `mark_turn(text)` when a final TranscriptionFrame arrives. The
    `reading()` method returns the current composite engagement score.
    """

    def __init__(self, window_seconds: float = 60.0):
        self._window_s = window_seconds
        self._rms_samples: deque[float] = deque(maxlen=400)        # ~16s @ 40ms chunks
        self._turn_lengths: deque[int] = deque(maxlen=20)
        self._turn_durations: deque[float] = deque(maxlen=20)
        self._pause_durations: deque[float] = deque(maxlen=20)
        self._last_turn_end: float | None = None

    @staticmethod
    def _chunk_rms(audio_bytes: bytes) -> float:
        if not audio_bytes:
            return 0.0
        import struct
        n = len(audio_bytes) // 2
        if n == 0:
            return 0.0
        samples = struct.unpack(f"<{n}h", audio_bytes[: n * 2])
        sum_sq = sum(s * s for s in samples)
        return math.sqrt(sum_sq / n)

    def feed_audio(self, audio_bytes: bytes) -> None:
        """Called for each input audio chunk going to STT (NOT echo)."""
        self._rms_samples.append(self._chunk_rms(audio_bytes))

    def mark_turn(self, text: str, duration_s: float, ended_at: float) -> None:
        """Called on each final user TranscriptionFrame.

        - text: transcript content (used for word count / pace)
        - duration_s: how long the user spoke this turn
        - ended_at: monotonic ts of end-of-speech
        """
        words = len((text or "").split())
        self._turn_lengths.append(words)
        self._turn_durations.append(max(0.3, duration_s))
        if self._last_turn_end is not None:
            gap = max(0.0, ended_at - self._last_turn_end)
            self._pause_durations.append(min(gap, 30.0))
        self._last_turn_end = ended_at

    def reading(self) -> EngagementReading:
        rms = list(self._rms_samples)
        # No data at all → return neutral baseline (don't penalise the learner
        # before they've said anything).
        if not rms and not self._turn_lengths:
            return EngagementReading(0.0, 0.0, 0.0, 0.0, 0.5, "neutral")

        if rms:
            mean_rms = sum(rms) / len(rms)
            var = sum((x - mean_rms) ** 2 for x in rms) / len(rms)
            sd = math.sqrt(var)
            energy = min(1.0, mean_rms / 4000.0)
            variance = min(1.0, sd / 2000.0)
        else:
            energy = 0.0
            variance = 0.0

        pace_wpm = 0.0
        if self._turn_lengths and self._turn_durations:
            total_words = sum(self._turn_lengths)
            total_seconds = sum(self._turn_durations)
            if total_seconds > 0:
                pace_wpm = (total_words / total_seconds) * 60.0

        pauses_s = sum(self._pause_durations) / len(self._pause_durations) if self._pause_durations else 0.0

        # Composite engagement score.
        #  + energy + variance + pace (capped) — pauses (long = disengaged)
        pace_norm = min(1.0, pace_wpm / 130.0)         # ~130 WPM = animated speech
        pause_penalty = min(1.0, pauses_s / 10.0)      # 10s+ pauses = lost
        score = max(0.0, min(1.0,
            0.35 * energy + 0.30 * variance + 0.25 * pace_norm - 0.20 * pause_penalty + 0.30
        ))

        if score < 0.4:
            label = "low"
        elif score > 0.75:
            label = "engaged"
        else:
            label = "neutral"

        return EngagementReading(
            energy=round(energy, 3),
            variance=round(variance, 3),
            pace_wpm=round(pace_wpm, 1),
            pauses_s=round(pauses_s, 1),
            score=round(score, 3),
            label=label,
        )
