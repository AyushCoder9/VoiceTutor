"""FastAPI WebSocket transport adapter (Pipecat 1.2+).

Wraps Pipecat's FastAPIWebsocketTransport. VAD is now a separate `VADProcessor`
inside the pipeline (see `backend/bot.py`), not a transport param.
"""

from __future__ import annotations

from typing import Any


def build_transport(websocket: Any) -> Any:
    """Construct a Pipecat FastAPIWebsocket transport for one client."""
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    from backend.transports.serializer import JSONAudioSerializer

    params = FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=16000,
        audio_out_sample_rate=24000,
        serializer=JSONAudioSerializer(),
        add_wav_header=False,
    )
    return FastAPIWebsocketTransport(websocket=websocket, params=params)
