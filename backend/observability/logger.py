"""Per-turn structured logging.

Emits one JSONL line per agent turn so we can answer "why did turn 14 take 2.3s?" —
the question the spec explicitly calls out.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger as _loguru


def init_logger(log_level: str = "INFO") -> None:
    """Configure loguru once at startup."""
    _loguru.remove()
    _loguru.add(
        sys.stderr,
        level=log_level,
        colorize=True,
        format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | "
        "<cyan>{module}</cyan>:<cyan>{line}</cyan> | {message}",
    )


def log() -> Any:
    return _loguru


@dataclass
class TurnLog:
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    t_start_ms: float = field(default_factory=lambda: time.time() * 1000)
    user_speech_end_ms: float | None = None
    stt_final_ms: float | None = None
    llm_first_token_ms: float | None = None
    llm_last_token_ms: float | None = None
    tts_first_audio_ms: float | None = None
    total_ms: float | None = None
    mode: str = "idle"
    persona: str = "teacher"
    tools_called: list[str] = field(default_factory=list)
    stt_text: str = ""
    llm_text: str = ""
    language_detected: str | None = None
    errors: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def mark(self, field_name: str) -> None:
        setattr(self, field_name, time.time() * 1000)

    def add_error(self, err: str) -> None:
        self.errors.append(err)

    def finalize(self) -> None:
        self.total_ms = time.time() * 1000 - self.t_start_ms

    def write(self) -> None:
        self.finalize()
        path = Path(os.environ.get("LATENCY_LOG_PATH", "./logs/turn_latency.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(self), ensure_ascii=False, default=str) + "\n")
