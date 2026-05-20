"""In-memory rolling metrics — exposed via the /metrics HTTP endpoint."""

from __future__ import annotations

import statistics
from collections import deque
from threading import Lock
from typing import Any


class LatencyTracker:
    """Sliding window of recent turn latencies."""

    def __init__(self, window: int = 200):
        self._window = window
        self._stt: deque[float] = deque(maxlen=window)
        self._llm_ttft: deque[float] = deque(maxlen=window)
        self._tts_first: deque[float] = deque(maxlen=window)
        self._total: deque[float] = deque(maxlen=window)
        self._lock = Lock()

    def record_turn(
        self,
        *,
        stt_ms: float | None = None,
        llm_ttft_ms: float | None = None,
        tts_first_ms: float | None = None,
        total_ms: float | None = None,
    ) -> None:
        with self._lock:
            if stt_ms is not None:
                self._stt.append(stt_ms)
            if llm_ttft_ms is not None:
                self._llm_ttft.append(llm_ttft_ms)
            if tts_first_ms is not None:
                self._tts_first.append(tts_first_ms)
            if total_ms is not None:
                self._total.append(total_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            def s(d: deque[float]) -> dict[str, float | int]:
                if not d:
                    return {"n": 0, "p50": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
                xs = sorted(d)
                n = len(xs)
                # Correct percentile indices (Type 7, nearest-rank style):
                # p50 = median, p95 = 95th-percentile element.
                p50_idx = min(n - 1, max(0, int(round((n - 1) * 0.50))))
                p95_idx = min(n - 1, max(0, int(round((n - 1) * 0.95))))
                return {
                    "n": n,
                    "p50": round(xs[p50_idx], 1),
                    "p95": round(xs[p95_idx], 1),
                    "max": round(xs[-1], 1),
                    "mean": round(statistics.fmean(xs), 1),
                }
            return {
                "stt_ms": s(self._stt),
                "llm_ttft_ms": s(self._llm_ttft),
                "tts_first_ms": s(self._tts_first),
                "total_ms": s(self._total),
            }


METRICS = LatencyTracker()
