# 📖 Glossary

Plain-English definitions for every acronym and library name used in this project. Read this once and the rest of the docs will make sense.

---

## Audio & Voice

**STT — Speech-to-Text.** The component that listens to audio and writes down what was said. Also called ASR (Automatic Speech Recognition). We use AssemblyAI's streaming STT.

**TTS — Text-to-Speech.** The opposite of STT. Takes written text and synthesizes spoken audio. We use ElevenLabs.

**VAD — Voice Activity Detection.** A small model that watches an audio stream and detects "human is speaking" vs "silence/noise". Tells the rest of the pipeline when a turn starts and ends. We use Silero VAD.

**Endpointing.** The decision "the user has finished speaking, send their utterance to STT for the final transcript". Usually triggered by VAD after N milliseconds of silence.

**Barge-in.** The user interrupts the bot mid-sentence. The bot stops speaking and listens. Essential to feel conversational instead of like an IVR.

**AGC — Automatic Gain Control.** Browser-side mic normalization. Quiet talkers get amplified, loud ones get attenuated, so STT sees a more uniform signal. Built into `getUserMedia({audio: {autoGainControl: true}})`.

**AEC — Acoustic Echo Cancellation.** Subtracts the bot's own speaker output from the mic input so the bot doesn't transcribe itself. Browser provides a baseline via `echoCancellation: true`; we add a server-side `MicGate` as backup.

**RMS — Root Mean Square.** A way to measure how "loud" an audio chunk is. Compute the average of (sample²), then take the square root. We use it to detect echo (low RMS) vs intentional barge-in (high RMS).

**PCM — Pulse Code Modulation.** The raw, uncompressed digital audio format. `PCM16` means 16-bit signed integer samples. Used because every audio API accepts it and it's trivially easy to manipulate.

**WPM — Words Per Minute.** Speaking pace. We compute it as `total_words / total_speaking_seconds × 60` and use it as one prosody signal.

**Prosody.** The rhythm, stress, and intonation of speech. Our prosody tracker reads energy + variance + pace + pauses to guess engagement.

---

## Models & AI

**LLM — Large Language Model.** The text-generation brain. Takes a list of conversation messages and produces the next one. We use Groq's hosted Llama 3.x.

**TTFT — Time-to-First-Token.** How long the LLM takes from receiving a request to producing its first word of output. Lower is better. Groq's LPU hits ~150–300 ms for Llama 3.

**LPU — Language Processing Unit.** Groq's custom hardware for running LLMs. Drastically faster than GPUs for streaming text generation.

**Whisper.** OpenAI's open-source STT model. Multilingual and robust. We have it as a fallback (via Groq's hosting) if AssemblyAI is unavailable.

**Nova-2.** Deepgram's flagship STT model. We support it as an optional alternative.

**Universal-Streaming v3.** AssemblyAI's current streaming STT. True WebSocket streaming, multilingual (en/es/fr/de/hi/it/pt). Our primary STT.

**Llama 3.x.** Meta's open-weight LLM family. We default to `llama-3.1-8b-instant` (fastest, smaller) and recommend `llama-3.3-70b-versatile` for the final demo recording.

**Silero VAD.** Open-source ONNX-based voice activity detector. Small enough to run inline in the pipeline with negligible cost. Standard choice for voice agents.

**ElevenLabs Turbo v2.5.** ElevenLabs' fastest streaming TTS model. Multilingual on a single voice ID, ~250–400 ms first-audio-chunk latency.

**Aura 2.** Deepgram's TTS model. We don't use it by default (free-tier credit issues) but the code path exists.

---

## Architecture

**FSM — Finite State Machine.** A simple state-and-transitions model. Our agent has 5 states: idle / teaching / quiz / conversation / doubt. Transitions are validated by code, not the LLM, so we never end up in an undefined state.

**Pipecat.** The Python orchestration framework that glues VAD → STT → LLM → TTS into a single streaming pipeline. We chose it over LiveKit because we don't need WebRTC scaling.

**Pipeline.** A linked sequence of `FrameProcessor` nodes. Audio frames flow in from the transport, get transformed by each stage, and audio frames flow out to the user.

**FrameProcessor.** A Pipecat building block. Subclass it, override `process_frame(frame, direction)`, and you can intercept any frame in the pipeline. Our `MicGate`, `LatencyProbe`, `IntentRouter`, `TranscriptForwarder`, `StreamingEvaluator`, and `MicActivityProbe` are all custom processors.

**LLMContext.** The current conversation state the LLM sees: a list of `{role, content}` messages plus an optional tool schema. We trim it aggressively (system prompt + last 6 messages) to keep input tokens low.

**Function calling / Tool calling.** Mechanism where the LLM emits a structured "call this function with these args" instead of natural prose. We have it wired (4 tools: `start_lesson`, `start_quiz`, `enter_doubt_mode`, `exit_doubt_mode`) but also keep a deterministic Python `IntentRouter` as backup.

**Intent router.** A Python class that scans user transcripts for keywords ("teach", "quiz", "wait") and flips FSM modes deterministically. Belt + suspenders to LLM tool calling.

---

## Memory & Pedagogy

**SQLite.** A single-file relational database. No server, no setup. Perfect for a single-user demo. Tables: `users`, `progress`, `vocab_mastery`, `mistakes`.

**WAL — Write-Ahead Logging.** SQLite's concurrent-access mode. Lets a writer (the bot) and readers (the `/progress` endpoint polling) coexist without blocking each other.

**FSRS — Free Spaced Repetition Scheduler.** An algorithm for deciding when to review a word again based on whether you got it right last time. Words you struggle with come back tomorrow; words you've mastered come back in weeks. We use a simplified "FSRS-lite" derived from SM-2.

**SM-2 — SuperMemo 2.** The original spaced-repetition algorithm from 1985. Tracks `ease` (how easy a card is for you) and `interval` (days until next review). Inspires FSRS.

**Ease.** A number 1.3–2.5 attached to each vocab word, representing how easy it is for the learner. Higher ease = longer gap until next review.

**Lapse.** Getting a previously-mastered word wrong. Resets the interval and drops ease.

---

## Backend

**FastAPI.** A modern Python web framework. We use it to expose REST endpoints + the `/ws` WebSocket route Pipecat connects to.

**Pydantic.** Data validation library; used by FastAPI for request/response models.

**uvicorn.** The ASGI server that actually runs FastAPI.

**WS — WebSocket.** A bi-directional persistent connection between browser and server. Way more efficient than HTTP polling for real-time audio streaming.

**REST.** "Just plain HTTP endpoints". We have `/`, `/curriculum`, `/progress`, `/metrics`, `/health`, `/session_recovery`, `/reset_progress`.

**P50 / P95 (percentiles).** Statistical summaries. "P50 = 1000 ms" means half the turns took ≤1000 ms. "P95 = 1500 ms" means 95% of turns took ≤1500 ms. We track these for STT/LLM/TTS/end-to-end.

**JSONL — JSON Lines.** A file format where each line is one JSON object. We use it for per-turn observability logs because it's grep-able and append-only.

**Jaccard similarity.** A way to compare two text strings by treating each as a set of words and computing `|intersection| / |union|`. 1.0 = identical, 0.0 = no overlap. Used in our deterministic grader.

---

## Frontend

**Next.js 14.** A React framework. We use the App Router for routing and React Server Components for the static parts.

**React.** The UI library Next.js is built on. Everything in `frontend/components` is a React component.

**Tailwind CSS.** A utility-first CSS framework. Classes like `text-zinc-100`, `bg-violet-500`, `rounded-2xl`. Keeps styles in the markup, no separate `.css` files per component.

**Framer Motion.** A React animation library. Used for orb pulses, scroll-reveal cards, layout transitions.

**lucide-react.** Icon library. The chevrons, mics, brains, etc.

**AudioWorklet.** A modern Web Audio API for running custom audio processing in a separate audio-rendering thread. We use it to downsample the browser's 48 kHz mic stream to 16 kHz PCM16 chunks before sending over WebSocket.

**`getUserMedia`.** Browser API for accessing microphone (and camera). Triggers the permission prompt.

**IntersectionObserver.** Browser API for "tell me when this element scrolls into view". Used by the sticky Navbar to highlight the current section.

---

## Networking & Transports

**WebRTC.** A peer-to-peer video/audio protocol used by Daily / LiveKit. More features than WebSocket but more complexity. We don't need it.

**SIP — Session Initiation Protocol.** Phone-system signaling. LiveKit + Twilio support it for telephony integration. Not in our scope.

**Pipecat Transport.** The Pipecat layer that owns the connection to the client. Implementations exist for WebSocket, WebRTC (via Daily), and LiveKit. We use `FastAPIWebsocketTransport`.

**Frame Serializer.** Converts in-memory `Frame` objects to/from the wire format (bytes/JSON). We wrote a custom `JSONAudioSerializer` — binary = raw PCM, text = JSON events — so the browser client needs zero codegen.

---

## Build & Tooling

**pytest.** The Python test runner. All 151 of our backend tests run through it.

**TypeScript.** A typed superset of JavaScript. Our frontend is fully typed.

**npm.** Node Package Manager. Frontend deps live in `package.json` and `node_modules`.

**.env.example.** A template environment file showing which environment variables the app reads. Never commit `.env` itself (it has API keys).

**CI — Continuous Integration.** Automated test runs on every commit. We don't have CI configured yet but the test suite would slot in cleanly.

---

## Spec Vocabulary

**Take-home.** The assignment brief we built this against.

**Demo video.** A 3–5 minute screencast showing the agent in action. One of the required deliverables.

**Write-up.** The 2–4 page technical document explaining design decisions. Another required deliverable.

**Evaluation harness.** Regression-test scripts that verify the agent still works after changes. Our scripted-flow e2e tests fill this role.

**Bonus / stretch goals.** Optional features the spec lists. We hit 5 of 7 (FSRS, pronunciation feedback, multi-persona, streaming evaluation, prosody engagement). Skipped 2 (telephony, on-device Whisper) with documented rationale.
