"""Custom wire-format serializer — keeps the browser client tiny.

Wire format over a single WebSocket:
  - Binary frames  →  raw PCM16 audio, little-endian.
  - Text frames    →  JSON control messages (events, transcripts, mode).

In Pipecat 1.4+, only OutputAudioRawFrame, OutputTransportMessageFrame, and
InterruptionFrame reach serialize() via _write_frame(). All other control
events (BotStartedSpeaking, LLMTextFrame, etc.) are injected into the pipeline
as OutputTransportMessageFrame by EventForwarder in bot.py.
"""

from __future__ import annotations

import json
from typing import Any

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    StartFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class JSONAudioSerializer(FrameSerializer):
    """JSON-for-events, raw-bytes-for-audio. WebSocket only.

    Inbound (client → server):
      - binary  →  InputAudioRawFrame (16 kHz)
      - text    →  ignored (barge-in detected via VAD on raw audio)

    Outbound (server → client):
      - OutputAudioRawFrame          →  binary PCM chunk
      - OutputTransportMessageFrame  →  JSON text (events from EventForwarder)
      - InterruptionFrame            →  {"type":"interrupt"}
      - EndFrame / CancelFrame       →  {"type":"end"}
      - ErrorFrame                   →  {"type":"error","message":...}
      - other                        →  dropped silently
    """

    def __init__(self, sample_rate_in: int = 16000, sample_rate_out: int = 24000):
        super().__init__()
        self._sr_in = sample_rate_in
        self._sr_out = sample_rate_out
        self._audio_frames_out = 0
        self._audio_bytes_out = 0

    async def setup(self, frame: StartFrame) -> None:
        self._audio_frames_out = 0
        self._audio_bytes_out = 0

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputTransportMessageFrame):
            return json.dumps(frame.message, ensure_ascii=False)
        if isinstance(frame, OutputAudioRawFrame):
            audio_bytes = bytes(frame.audio)
            self._audio_frames_out += 1
            self._audio_bytes_out += len(audio_bytes)
            if self._audio_frames_out <= 3 or self._audio_frames_out % 50 == 0:
                from loguru import logger
                logger.info(
                    f"🔊 serializer: audio frame #{self._audio_frames_out}, "
                    f"{len(audio_bytes)} bytes (total {self._audio_bytes_out} bytes sent)"
                )
            return audio_bytes
        if isinstance(frame, InterruptionFrame):
            return json.dumps({"type": "interrupt"})
        if isinstance(frame, (EndFrame, CancelFrame)):
            return json.dumps({"type": "end"})
        if isinstance(frame, ErrorFrame):
            return json.dumps({"type": "error", "message": frame.error})
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return InputAudioRawFrame(
                audio=bytes(data),
                sample_rate=self._sr_in,
                num_channels=1,
            )
        try:
            msg: dict[str, Any] = json.loads(data)
        except Exception:
            return None
        # Client control messages currently unused at the pipeline level;
        # barge-in is detected via VAD on raw audio.
        _ = msg
        return None
