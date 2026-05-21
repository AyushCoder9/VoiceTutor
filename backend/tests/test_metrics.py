"""Tests for the latency / percentile tracker."""

from backend.observability.metrics import LatencyTracker


def test_empty_tracker():
    t = LatencyTracker()
    snap = t.snapshot()
    assert snap["total_ms"]["n"] == 0


def test_single_value():
    t = LatencyTracker()
    t.record_turn(total_ms=500.0)
    snap = t.snapshot()
    assert snap["total_ms"]["n"] == 1
    assert snap["total_ms"]["p50"] == 500.0
    assert snap["total_ms"]["p95"] == 500.0


def test_p50_le_p95_two_samples():
    """Earlier bug: with n=2 the percentile indices were swapped → p50 > p95.

    Regression test: invariant p50 <= p95 always.
    """
    t = LatencyTracker()
    t.record_turn(total_ms=200.0)
    t.record_turn(total_ms=800.0)
    snap = t.snapshot()
    assert snap["total_ms"]["p50"] <= snap["total_ms"]["p95"]


def test_p50_le_p95_many_samples():
    t = LatencyTracker()
    for ms in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]:
        t.record_turn(total_ms=float(ms))
    snap = t.snapshot()
    assert snap["total_ms"]["p50"] <= snap["total_ms"]["p95"]
    assert snap["total_ms"]["max"] == 1000.0
    assert snap["total_ms"]["mean"] == 550.0


def test_each_stage_recorded_independently():
    t = LatencyTracker()
    t.record_turn(stt_ms=120.0, llm_ttft_ms=300.0, tts_first_ms=400.0, total_ms=900.0)
    snap = t.snapshot()
    assert snap["stt_ms"]["n"] == 1
    assert snap["llm_ttft_ms"]["n"] == 1
    assert snap["tts_first_ms"]["n"] == 1
    assert snap["total_ms"]["n"] == 1


def test_none_values_skipped():
    t = LatencyTracker()
    t.record_turn(stt_ms=None, total_ms=500.0)
    snap = t.snapshot()
    assert snap["stt_ms"]["n"] == 0
    assert snap["total_ms"]["n"] == 1


def test_window_slides():
    t = LatencyTracker(window=5)
    for ms in range(10):
        t.record_turn(total_ms=float(ms))
    snap = t.snapshot()
    assert snap["total_ms"]["n"] == 5
