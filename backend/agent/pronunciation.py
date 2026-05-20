"""Pronunciation feedback heuristic.

True phoneme scoring (Azure Pronunciation Assessment, MFA) is a stretch goal we
chose to skip — see WRITEUP D11. Instead we combine:
  - Deepgram per-word confidence + alternate hypotheses
  - A small Spanish phoneme-difficulty heuristic (rr, ñ, gue/güe, j, ll)
  - An LLM-emitted explanation per detected weak word

Result: specific, actionable feedback ("your *rr* in *perro* was tapped, not rolled"),
not generic "good job".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Spanish phonemes that English speakers commonly miss.
# Each entry: regex pattern → (hint, severity-when-confidence-low)
TRICKY_PATTERNS: dict[str, str] = {
    r"rr": "Spanish *rr* is a trill — flick the tongue tip rapidly against the roof. Try lengthening it.",
    r"ñ": "Spanish *ñ* is like the *ny* in 'canyon'.",
    r"ll": "Spanish *ll* sounds like English *y* in 'yes' (in most dialects).",
    r"j": "Spanish *j* is a hard *h* — gargled at the back of the throat.",
    r"gue|gui": "Silent *u* — pronounce only *ge*/*gi*. *Guerra* sounds like 'geh-rra'.",
    r"güe|güi": "*ü* with the umlaut means the *u* IS pronounced. *Pingüino* = 'peen-GWEE-no'.",
    r"h": "Spanish *h* is always silent. *Hola* sounds like 'OH-la'.",
    r"z|ce|ci": "In Latin America, *z*, *ce*, *ci* sound like English *s*. In Spain, like English *th*.",
    r"qu": "Spanish *qu* sounds like English *k* — the *u* is silent.",
    r"v|b": "Between vowels, *v* and *b* sound almost identical, like a soft *b*.",
    r"d$": "Word-final *d* is very soft, almost like English *th* in 'the'.",
    r"ce|ci": "Soft *c* before *e* or *i*. Sounds like *s* (LatAm) or *th* (Spain).",
}


# Detailed per-word phoneme decomposition for common curriculum words.
# Each tuple: (word, expected sounds, common-mistake feedback).
WORD_PHONEME_HINTS: dict[str, list[tuple[str, str]]] = {
    "hola":          [("silent h", "Don't aspirate the H — it's silent. Start with 'OH'.")],
    "perro":         [("trilled rr", "The *rr* is rolled — try humming and tapping your tongue.")],
    "señor":         [("ñ", "*ñ* = *ny*. So it's 'seh-NYOR', not 'seh-NOR'.")],
    "gracias":       [("soft c", "Soft *c* in *gracias* = *s* (LatAm) or *th* (Spain).")],
    "llamo":         [("ll", "The *ll* sounds like English *y*. So 'me YA-mo'.")],
    "jugar":         [("hard j", "*j* is gargled — like clearing your throat.")],
    "días":          [("clear í", "The accent on *í* lengthens the i: 'DEE-as'.")],
    "agua":          [("gw cluster", "Smooth *gw* glide, like 'water' without the t.")],
    "buenos":        [("ue", "*ue* = wee-EH together, not 'boo-EH'.")],
    "café":          [("acute é", "Stress the final é: 'kah-FEH', not 'KAH-feh'.")],
}


@dataclass
class PronunciationFeedback:
    word: str
    confidence: float
    feedback: str
    severity: str  # "ok" | "minor" | "major"

    def as_dict(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "confidence": round(self.confidence, 3),
            "feedback": self.feedback,
            "severity": self.severity,
        }


def detect_tricky(word: str) -> list[str]:
    """Return list of phoneme-difficulty hints triggered by this word.
    Combines per-word hints (most specific) + general pattern hints.
    """
    hits: list[str] = []
    lower = word.lower().strip()

    # Per-word specific hints (highest priority).
    if lower in WORD_PHONEME_HINTS:
        for _, hint in WORD_PHONEME_HINTS[lower]:
            hits.append(hint)

    # General pattern hints (lower priority, dedup against above).
    for pattern, hint in TRICKY_PATTERNS.items():
        if re.search(pattern, lower) and hint not in hits:
            hits.append(hint)
    return hits


def score_word(word: str, confidence: float | None) -> PronunciationFeedback:
    """Combine STT confidence with phoneme heuristic into a feedback record."""
    conf = confidence if confidence is not None else 1.0
    tricky = detect_tricky(word)

    if conf >= 0.85 and not tricky:
        return PronunciationFeedback(word, conf, f"'{word}' sounded clear.", "ok")

    if conf >= 0.85 and tricky:
        return PronunciationFeedback(
            word, conf,
            f"'{word}' was understandable — tip: " + tricky[0],
            "minor",
        )

    if 0.55 <= conf < 0.85:
        hint = tricky[0] if tricky else "Try slowing down and over-articulating each syllable."
        return PronunciationFeedback(
            word, conf,
            f"'{word}' was a bit unclear. {hint}",
            "minor",
        )

    # conf < 0.55
    hint = tricky[0] if tricky else "Try again — say it slowly, syllable by syllable."
    return PronunciationFeedback(
        word, conf,
        f"I had trouble hearing '{word}'. {hint}",
        "major",
    )


def feedback_for_utterance(
    expected_words: list[str],
    spoken_text: str,
    word_confidences: dict[str, float] | None = None,
) -> list[PronunciationFeedback]:
    """Per-word feedback list across an expected target phrase."""
    confs = word_confidences or {}
    out: list[PronunciationFeedback] = []
    for w in expected_words:
        c = confs.get(w.lower())
        out.append(score_word(w, c))
    return out


def summarize_feedback(items: list[PronunciationFeedback]) -> str:
    """Compact one-liner suitable for the LLM to read aloud."""
    if not items:
        return "Nice pronunciation overall."
    majors = [i for i in items if i.severity == "major"]
    if majors:
        i = majors[0]
        return f"Focus on '{i.word}': {i.feedback.split('. ',1)[-1]}"
    minors = [i for i in items if i.severity == "minor"]
    if minors:
        i = minors[0]
        return f"Small tip on '{i.word}': {i.feedback.split('. ',1)[-1]}"
    return "Nice pronunciation overall!"
