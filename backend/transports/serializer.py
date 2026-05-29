"""Custom wire-format serializer — keeps the browser client tiny.

Wire format over a single WebSocket:
  - Binary frames  →  raw PCM16 audio, little-endian. Direction implicit by
                      message direction. Sample rate fixed at the params we
                      negotiated (16 kHz in, 24 kHz out).
  - Text frames    →  JSON control messages (events, transcripts, mode).

Why custom (not the default Protobuf serializer): the browser then needs zero
generated code or runtime protobuf — just `WebSocket` + `AudioWorklet`.
"""

from __future__ import annotations

import json
from typing import Any

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    LLMTextFrame,
    OutputAudioRawFrame,
    OutputTransportMessageFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer


class JSONAudioSerializer(FrameSerializer):
    """JSON-for-events, raw-bytes-for-audio. WebSocket only.

    Inbound (client → server):
      - binary  →  InputAudioRawFrame (16 kHz)
      - text    →  {"type": "start"|"barge_in"|"client_event", ...}

    Outbound (server → client):
      - OutputAudioRawFrame   →  binary chunk
      - TranscriptionFrame    →  {"type":"transcript","role":"user","text":...}
      - BotStartedSpeaking    →  {"type":"bot_speaking","speaking":true}
      - BotStoppedSpeaking    →  {"type":"bot_speaking","speaking":false}
      - UserStartedSpeaking   →  {"type":"user_speaking","speaking":true}
      - UserStoppedSpeaking   →  {"type":"user_speaking","speaking":false}
      - InterruptionFrame     →  {"type":"interrupt"}
      - other                 →  dropped silently
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
        return

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputTransportMessageFrame):
            # Direct JSON pass-through from TranscriptForwarder etc.
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
        if isinstance(frame, TranscriptionFrame):
            return json.dumps({
                "type": "transcript",
                "role": "user",
                "interim": False,
                "text": frame.text,
                "language": getattr(frame, "language", None),
            }, ensure_ascii=False)
        if isinstance(frame, InterimTranscriptionFrame):
            return json.dumps({
                "type": "transcript",
                "role": "user",
                "interim": True,
                "text": frame.text,
                "language": getattr(frame, "language", None),
            }, ensure_ascii=False)
        if isinstance(frame, LLMTextFrame):
            # Stream the bot's text as it's generated so the UI shows it live.
            return json.dumps({
                "type": "transcript",
                "role": "assistant",
                "interim": True,
                "text": frame.text,
            }, ensure_ascii=False)
        if isinstance(frame, BotStartedSpeakingFrame):
            return json.dumps({"type": "bot_speaking", "speaking": True})
        if isinstance(frame, BotStoppedSpeakingFrame):
            return json.dumps({"type": "bot_speaking", "speaking": False})
        if isinstance(frame, UserStartedSpeakingFrame):
            return json.dumps({"type": "user_speaking", "speaking": True})
        if isinstance(frame, UserStoppedSpeakingFrame):
            return json.dumps({"type": "user_speaking", "speaking": False})
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
