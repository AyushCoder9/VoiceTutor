"""Smoke tests for the wire-format serializer.

We can't fully exercise it without pipecat installed, so these tests are guarded.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("pipecat")  # Skip module if pipecat isn't installed.

from backend.transports.serializer import JSONAudioSerializer
from pipecat.frames.frames import (  # noqa: E402
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    TranscriptionFrame,
)


@pytest.mark.asyncio
async def test_audio_frame_to_bytes():
    s = JSONAudioSerializer()
    af = OutputAudioRawFrame(audio=b"\x00\x01\x02\x03", sample_rate=24000, num_channels=1)
    out = await s.serialize(af)
    assert out == b"\x00\x01\x02\x03"


@pytest.mark.asyncio
async def test_transcript_frame_to_json():
    s = JSONAudioSerializer()
    out = await s.serialize(TranscriptionFrame(text="hola", user_id="u", timestamp=""))
    assert isinstance(out, str)
    payload = json.loads(out)
    assert payload["type"] == "transcript"
    assert payload["text"] == "hola"


@pytest.mark.asyncio
async def test_bot_speaking_events():
    s = JSONAudioSerializer()
    on = json.loads(await s.serialize(BotStartedSpeakingFrame()))
    off = json.loads(await s.serialize(BotStoppedSpeakingFrame()))
    assert on["speaking"] is True and off["speaking"] is False


@pytest.mark.asyncio
async def test_interrupt_serialized():
    s = JSONAudioSerializer()
    out = json.loads(await s.serialize(InterruptionFrame()))
    assert out["type"] == "interrupt"


@pytest.mark.asyncio
async def test_inbound_bytes_become_input_frame():
    from pipecat.frames.frames import InputAudioRawFrame
    s = JSONAudioSerializer()
    out = await s.deserialize(b"\x10\x20\x30\x40")
    assert isinstance(out, InputAudioRawFrame)
    assert out.sample_rate == 16000
