import asyncio
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
import os
from dotenv import load_dotenv
load_dotenv("backend/.env")

async def main():
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
        model="eleven_turbo_v2_5",
        output_format="pcm_24000",
    )
    # We will simulate pushing a frame to TTS
    frame = TTSSpeakFrame("Hello world!")
    # TTSService has a _push_tts_frames but it requires a pipeline task attached.
    print("Testing ElevenLabs TTS Service directly is hard without a pipeline, but API key is", bool(os.getenv("ELEVENLABS_API_KEY")))

asyncio.run(main())
