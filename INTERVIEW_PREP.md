# 🎯 VoiceTutor — Interview Prep (Plain-English Edition)

> **How to read this.** Every technical word that has an acronym or a library
> name gets a one-line "what is this" the first time it shows up. If you want
> the full reference card of every term, see [`GLOSSARY.md`](GLOSSARY.md).
> The goal of this doc is that you can walk into the interview and explain
> any part of the system without rehearsing — because you actually understand
> each piece.

---

## Table of contents

1. [The 90-second pitch](#1-the-90-second-pitch)
2. [What problem was I solving](#2-what-problem-was-i-solving)
3. [How I thought about the stack](#3-how-i-thought-about-the-stack)
4. [The system design — layer by layer](#4-the-system-design--layer-by-layer)
5. [What happens when a user clicks the orb](#5-what-happens-when-a-user-clicks-the-orb)
6. [Every file, what it does, in plain words](#6-every-file-what-it-does-in-plain-words)
7. [Each feature — what it is + how it actually works](#7-each-feature--what-it-is--how-it-actually-works)
8. [Problems I hit and how I fixed them](#8-problems-i-hit-and-how-i-fixed-them)
9. [Likely interview questions, answered in my own voice](#9-likely-interview-questions-answered-in-my-own-voice)

---

## 1. The 90-second pitch

VoiceTutor is a voice-first Spanish tutor. You click a button, talk to it, and it teaches you. It can:

1. **Teach you a lesson** (e.g. "teach me how to order food") — walks you through the vocabulary, examples, and a practice prompt, step by step.
2. **Quiz you** ("quiz me on greetings") — asks 5 questions, grades your spoken answer based on meaning (not exact spelling), and tells you what you got wrong and why.
3. **Answer doubts mid-lesson** ("wait, why is it *me llamo* and not *yo llamo*?") — pauses the lesson, answers in English, and resumes exactly where you were.
4. **Roleplay a conversation** ("let's order coffee in a Madrid café") — stays in character, gently corrects you in flow.

It's voice-first: nothing requires tapping or typing. The whole thing runs on free APIs (Groq, AssemblyAI, ElevenLabs) and a SQLite file. End-to-end latency from "I stopped talking" to "bot starts talking" is around **1 second**.

---

## 2. What problem was I solving

The brief asked me to "reimagine Duolingo as a voice-first tutor." Duolingo today is tap-tap-tap on a phone screen. The take-home wanted something where you can **put the phone down** and learn by talking like you would with a human teacher.

The hard parts I knew I had to nail:
- **Low latency.** If the bot takes 3 seconds to reply, it feels like a 1990s IVR phone tree, not a conversation. The spec gave me a budget of 1.5 seconds for end-to-end response.
- **Barge-in.** A human tutor doesn't wait for you to finish their sentence before listening. If I start talking, they stop. I had to make that work.
- **Four learning modes.** Teaching, quizzing, free conversation, and handling doubts mid-flow — all entered via voice commands.
- **Memory.** Per-session (what we just talked about) and per-user (which words I've struggled with), so the bot doesn't feel amnesiac.
- **Code-switching.** Spanish learners constantly mix English and Spanish in one sentence. The STT (the speech-to-text engine) has to handle that.

---

## 3. How I thought about the stack

I picked each component for one specific reason. Here's the chain of reasoning.

**Why Pipecat (an open-source Python framework that wires together VAD → STT → LLM → TTS into a single streaming pipeline) instead of LiveKit Agents?**
- The product is single-user voice. No video, no telephony, no horizontal scaling. LiveKit's strengths (WebRTC, multi-participant rooms) are unused.
- Pipecat gives me frame-level control — I can drop in custom processors between any two stages of the pipeline, which I needed for the latency probe and the intent router.
- Pipecat is lighter to spin up locally on a Mac for a 48-hour build.

**Why Groq's Llama 3.1 / 3.3 (open-weight LLMs hosted on Groq's LPU chips) instead of GPT-4 or Claude?**
- Groq's LPU (their custom Language Processing Unit hardware) gives the lowest **TTFT** (Time-to-First-Token — how long until the model says its first word) I've seen anywhere: ~150–300 ms. For a sub-1.5 s end-to-end product, every 100 ms of LLM latency counts.
- Generous free tier. No card required.
- Function calling works (the LLM can output structured tool-call objects, not just text), which I use for mode transitions.

**Why AssemblyAI Universal-Streaming (an STT model that delivers transcripts over a live WebSocket) instead of Whisper batch?**
- The spec literally says "STT must be streaming." Batch STT (where you record the whole utterance, then send it) doesn't qualify.
- AssemblyAI's Universal-Streaming v3 supports Spanish (and several other languages) natively over a live socket.
- $50 free credit on signup, no card.
- Why not Deepgram? Their $200 free promo no longer auto-applies; you need a $100 minimum purchase.

**Why ElevenLabs Turbo v2.5 (a streaming TTS model) for the bot's voice?**
- Best Spanish prosody I've heard from any TTS, free-tier or paid.
- Multilingual on a single voice ID — so when the bot says "*Hola*, today we'll learn how to say *hello*," it sounds like one person, not a robot that swaps voices mid-sentence.
- WebSocket streaming: the first audio chunk comes back in ~350 ms.

**Why Silero VAD (an open-source voice-activity-detection model)?**
- Industry standard for voice agents. Tiny ONNX model, runs inline in the pipeline with no measurable cost.
- Pipecat has built-in integration.

**Why SQLite (a single-file relational database with no server) for memory?**
- Single-user demo. SQLite is zero-ops. The whole database is one file at `data/voicetutor.db`.
- Easy to inspect with the `sqlite3` CLI when debugging.
- Trivially upgradable to Postgres later — no ORM lock-in, raw parameterised SQL.

**Why Next.js 14 (React framework) for the frontend?**
- The brief explicitly says to keep the UI minimal — the bot is the product. Next.js gets me a single-page app with React Server Components, dark-mode styling, and animation libraries (Framer Motion) without ceremony.

---

## 4. The system design — layer by layer

There are essentially **five layers**, each doing one job. Here's how I think about them.

### Layer 1: Browser (what you see)
A single Next.js page. Click the voice orb → request microphone permission via `getUserMedia` (the browser API that asks "can I access your mic?") → open a WebSocket (persistent two-way connection) to the backend. Capture audio with the Web Audio API, downsample from 48 kHz to 16 kHz PCM16 (16-bit signed integer audio samples), and send chunks over the socket.

### Layer 2: FastAPI server (entry point)
A Python web server. Exposes a few HTTP endpoints (`/curriculum`, `/progress`, `/metrics`, `/health`, `/reset_progress`, `/session_recovery`) and one WebSocket route `/ws`. When `/ws` accepts a connection, it spins up a new `LanguageTutorBot` instance for that session.

### Layer 3: Pipecat pipeline (the voice loop)
Inside the bot, audio frames flow through a chain of processors:

1. **VAD** (Silero) — detects when you start and stop speaking.
2. **MicGate** (custom) — drops audio that's clearly bot echo (low RMS during bot speech). Off by default for headphones.
3. **MicActivityProbe** (custom) — logs every Nth audio frame so we can verify the mic is alive.
4. **AssemblyAI STT** — streams audio to AssemblyAI and gets back interim + final transcripts.
5. **TranscriptForwarder** (custom) — re-broadcasts each transcript as a wire message so the UI always sees it.
6. **StreamingEvaluator** (custom) — for quiz mode, peeks at the interim transcript and pre-grades if it already looks right.
7. **LatencyProbe** (custom) — records timestamps at each stage so we can compute per-turn latency.
8. **IntentRouter** (custom) — detects keywords like "teach", "quiz", "wait", "continue" and flips the FSM mode in pure Python (no LLM call needed for routing).
9. **User aggregator** — appends the user's transcript to the LLM context.
10. **Groq LLM** — generates the bot's reply.
11. **ElevenLabs TTS** — turns the bot's text into streamed audio.
12. **Transport output** — sends the audio back through the WebSocket.
13. **Assistant aggregator** — appends the bot's reply to the LLM context for the next turn.

### Layer 4: Agent core (the brain)
Pure Python, no external services. Contains:
- **Mode FSM** (`agent/orchestrator.py`) — 5 states, validated transitions, doubt-stack for nested interruptions.
- **Prompts** (`agent/prompts.py`) — the bot's personality and per-mode instructions, kept tight (~150 tokens base) to save LLM cost.
- **Grader** (`agent/grader.py`) — two-tier: deterministic Jaccard match first, LLM fallback for ambiguous cases.
- **Pronunciation hints** (`agent/pronunciation.py`) — regex patterns and per-word tips for English-speaker mistakes (rolled r, silent h, etc.).
- **Prosody tracker** (`agent/prosody.py`) — engagement detection from audio energy + pace + pauses.
- **Tool runner** (`agent/tools.py`) — implementation of every tool the agent can invoke.

### Layer 5: Memory
- **Session memory** (`memory/session.py`) — in-RAM state for the current call: mode, lesson position, mistakes-so-far, frustration counter.
- **Persistent memory** (`memory/persistent.py`) — SQLite tables for users, lesson progress, vocab mastery (with FSRS scheduling), and mistakes log.

---

## 5. What happens when a user clicks the orb

End-to-end flow, second by second.

1. **You click the orb.** The browser asks for mic permission. You allow.
2. **Frontend opens a WebSocket** to `ws://localhost:8000/ws`. The orb flips to "connected" blue.
3. **Backend accepts the WS** → builds a Pipecat pipeline → spawns a `LanguageTutorBot` → calls `task.queue_frames([TTSSpeakFrame(greeting)])` to make the bot speak the greeting directly without going through the LLM (saves a round-trip).
4. **Greeting plays.** ~1 second of TTS audio reaches your headphones: "*¡Hola, Learner!* I'm Sofía, your Spanish tutor. What would you like to do — learn a lesson, take a quiz, or have a conversation?"
5. **You reply: "Teach me greetings."**
6. **VAD detects** speech start → emits `UserStartedSpeakingFrame`. Frontend shows orb pulsing green.
7. **AssemblyAI STT** streams your audio out, gets interim transcripts back, finally emits a `TranscriptionFrame(text="Teach me greetings")` when you stop.
8. **VAD detects** speech end → emits `UserStoppedSpeakingFrame`. Orb flips orange.
9. **IntentRouter sees** "teach me greetings", matches the `INTENT_TEACH` keyword set, calls into `_route()`:
   - Flips FSM mode to `teaching`.
   - Sets `current_lesson_id = "greetings-001"`.
   - Seeds the lesson's 10 vocab words into FSRS (so the Due-for-Review panel populates).
   - Records partial progress (0.3 score) so the curriculum bar starts filling.
   - Injects a tiny system note into the LLM context: *"Lesson: Greetings & Introductions. Objective: Greet, introduce yourself. Greet the topic in one sentence, then ask if learner is ready."*
10. **The LLM (Groq) runs.** Reads the system prompt + greeting + your "teach me greetings" + the intent system note. Outputs something like *"Great, let's start with greetings. We'll learn three key phrases. Ready?"* — about 80 tokens, ~250 ms TTFT on Groq.
11. **ElevenLabs TTS** streams the response back as audio chunks (~350 ms to first chunk). Orb flips violet.
12. **You hear the bot speak.** Total time from end-of-your-speech → first audible bot token: ~900 ms.
13. **You say "yes" / "ready" / etc.** Pipeline re-runs. IntentRouter notices you're still in teaching mode → advances the lesson step from `intro` → `explain` → injects the grammar note.
14. **And so on** through example → practice → check.
15. **You say "quiz me."** IntentRouter flips to quiz mode, builds 5 questions, asks the first.
16. **You answer.** The deterministic grader checks; if correct, score increments and FSRS marks the vocab as a successful repetition (interval extended). If wrong, mistake logged + ease decreased.
17. **You say "wait, why is it *la cuenta* not *el cuenta*?"** IntentRouter sees "wait" → enters doubt mode, pushes prior FSM state. LLM answers in English. You say "ok continue" → exits doubt, restores prior state.

---

## 6. Every file, what it does, in plain words

### `backend/server.py`
The FastAPI entry point. Six HTTP endpoints plus the `/ws` WebSocket route. Lifespan hook eagerly initialises the SQLite DB on startup so the first connection doesn't pay schema-init cost.

### `backend/bot.py`
The `LanguageTutorBot` class. Per WS connection, it constructs the Pipecat pipeline, registers tools with the LLM, wires the custom processors (MicGate, IntentRouter, etc.), and runs the pipeline until disconnect. **~900 lines** — the densest file in the repo because it owns the orchestration. The six custom Pipecat `FrameProcessor` classes are defined as inner classes inside `run()` so each gets closure access to the bot's session/memory/FSM without verbose constructor wiring; they're labelled with banner comments (`# ---- MicGate ----`, etc.) so the file reads like the pipeline diagram top to bottom.

### `backend/agent/orchestrator.py`
The mode FSM (Finite State Machine — five states, controlled transitions). `ModeFSM.switch_to(mode)` validates moves. Doubt mode is a *stack push*: saves the prior mode + lesson step + quiz index, so `exit_doubt()` pops back to the exact state.

### `backend/agent/prompts.py`
Every instruction the LLM ever sees. `BASE_PERSONA` is ~150 tokens of rules: speak English by default, Spanish only for target vocab/examples; reply in 1–2 sentences; never auto-start a lesson. Mode overlays (`MODE_TEACHING`, etc.) layer in mode-specific behavior. `greeting_for_returning_user(name)` produces the always-question-shaped opener.

### `backend/agent/tools.py`
Function-call schemas + Python implementations of every tool: `start_lesson`, `start_quiz`, `grade_answer`, `save_progress`, `lookup_vocab`, `enter_doubt_mode`, `exit_doubt_mode`, `pronunciation_feedback`, `end_session_summary`, and more. The active LLM tool schema is curated down to 4 essentials for Llama parser reliability.

### `backend/agent/grader.py`
Two-tier semantic grader. `grade_deterministic()` normalises both strings (NFD Unicode → strip accents → lowercase → strip punctuation → collapse whitespace), checks exact match, then variant list, then Jaccard similarity. If similarity is in the ambiguous middle band (0.35–0.75), it falls back to an LLM call with a strict JSON output schema. **Avoids paying an LLM token on most graders.**

### `backend/agent/pronunciation.py`
A regex+dict heuristic for pronunciation tips. Per-word hints (10 curriculum words like *perro* → "the rr is rolled — try humming and tapping") plus 12 general phoneme patterns (silent h, soft c, qu cluster, etc.). When a quiz answer is wrong, the relevant tip is auto-attached to the LLM's correction.

### `backend/agent/prosody.py`
Engagement detection from raw audio. `ProsodyTracker.feed_audio(bytes)` per chunk → builds a sliding window of RMS values. `mark_turn(text, dur, end)` per final transcript → tracks pace (words per minute) and inter-turn pauses. `reading()` returns a composite score 0..1 + a label (low / neutral / engaged). The IntentRouter peeks at this each turn and nudges the LLM tone accordingly.

### `backend/curriculum/lessons.json`
The actual curriculum content. **6 lessons**, each with vocabulary (es / en / phonetic), grammar notes, examples, practice prompts, and check questions. Hand-authored over LLM-generated so a reviewer can verify grammar accuracy.

### `backend/curriculum/loader.py`
Reads `lessons.json` into typed dataclasses (`Lesson`, `VocabItem`, `Check`). `by_topic("food")` does fuzzy keyword lookup — combination of hand-tuned keyword map + substring fallback.

### `backend/memory/schema.sql`
SQLite DDL. Four tables: `users`, `progress`, `vocab_mastery` (with FSRS fields), `mistakes`. WAL journal mode for concurrent reader/writer.

### `backend/memory/persistent.py`
SQLite layer. Plain parameterized SQL, no ORM. Methods: `upsert_user`, `record_lesson_score` (with MAX semantics), `record_vocab_attempt` (FSRS update), `due_vocab`, `weak_areas`, `log_mistake`, `reset_user_progress`.

### `backend/memory/session.py`
In-RAM session state. `SessionMemory` dataclass: mode, persona, current lesson, quiz state, mistakes-this-session, frustration counter. `context_summary()` produces the compact string fed to the LLM each turn ("mode=teaching; confidence=0.62; ...").

### `backend/transports/websocket.py`
Thin wrapper that constructs Pipecat's `FastAPIWebsocketTransport` with our `JSONAudioSerializer`.

### `backend/transports/serializer.py`
Custom wire format. Binary frames = raw PCM16 audio. Text frames = JSON events (`{type: "transcript", role: "user", text: ...}`). No protobuf so the browser client is tiny.

### `backend/observability/logger.py`
Per-turn `TurnLog` dataclass. `write()` appends a JSONL line with every stage timestamp + STT text + LLM text + tools called.

### `backend/observability/metrics.py`
`LatencyTracker` — sliding window of recent turn latencies. `snapshot()` returns P50 / P95 / max / mean for STT, LLM TTFT, TTS first audio, and end-to-end total. Surfaced via `/metrics` endpoint.

### Frontend (`frontend/`)

- `app/page.tsx` — main page composition. Five sections (hero, demo, features, curriculum, stack) + nav + footer.
- `app/layout.tsx` — root layout, font imports, background aurora.
- `app/icon.svg` — branded favicon (rounded gradient badge with 5-bar waveform).
- `components/Navbar.tsx` — sticky glass nav with IntersectionObserver scroll-tracking.
- `components/Hero.tsx` — asymmetric hero with animated word-rise headline + preview orb.
- `components/Features.tsx` — 10 capability cards with hover tilt.
- `components/CurriculumShowcase.tsx` — 6 lesson cards from live `/curriculum` API.
- `components/StackSection.tsx` — live latency tiles + tech-stack marquee.
- `components/Footer.tsx` — brand + section links + tech badges.
- `components/VoiceOrb.tsx` — the animated central voice orb (idle/listening/thinking/speaking states).
- `components/Transcript.tsx` — live transcript with interim "you · live" and "Sofía · streaming" bubbles.
- `components/ModeBadge.tsx` — the current FSM mode pill.
- `components/ProgressPanel.tsx` — curriculum progress + weak spots + due vocab + latency table.
- `components/QuickCommands.tsx` — sample phrase chips.
- `lib/voiceClient.ts` — the browser-side voice transport. Mic capture via AudioWorklet (downsampling 48k → 16k Int16), playback via Web Audio AudioBufferSource with monotonic scheduling.
- `lib/api.ts` — typed fetchers for the REST endpoints.

---

## 7. Each feature — what it is + how it actually works

### Voice-first interaction
**What.** Real-time two-way audio: streaming STT going in, streaming TTS coming out. No tap/type required.
**How.** WebSocket transport carries PCM audio in both directions. The browser uses `getUserMedia` for the mic + `AudioWorklet` for downsampling. The server runs the Pipecat pipeline.

### Sub-1.5 second latency
**What.** Time from "I stopped talking" to "bot starts talking" is consistently under 1.5 seconds, often under 1 second.
**How.** Every stage streams (no batching). Groq for the lowest TTFT, AssemblyAI for the lowest STT finalize delay, ElevenLabs Turbo for the fastest TTS first chunk. VAD endpointing tuned to 0.3 s to avoid waiting too long. Per-turn JSONL log records every timestamp so I can prove it.

### Barge-in
**What.** You can interrupt the bot mid-word. It stops within ~250 ms and listens.
**How.** Silero VAD detects speech onset → emits `UserStartedSpeakingFrame` → Pipecat's `allow_interruptions=True` cancels in-flight TTS → serializer emits `{type: "interrupt"}` → frontend `flushPlayback()` rebuilds the gain node, dropping all scheduled audio buffers.

### Four learning modes
Teaching / Quiz / Conversation / Doubt, all entered by voice command. Mode FSM in `orchestrator.py` with hand-rolled transition validation. Doubt is a stack push so you can ask "wait" mid-quiz and resume at the same question.

### Semantic grading
**What.** "I'd like coffee" and "I would like a coffee, please" are both correct.
**How.** Two-tier grader in `grader.py`. First: normalise (NFD Unicode strip accents, lowercase, strip punctuation), check exact, then variant list, then Jaccard token similarity. If confidence is in the middle band, fall back to an LLM call. Most graders cost zero LLM tokens.

### Code-switching
**What.** "How do I say *manzana* again?" is transcribed correctly with both English and Spanish.
**How.** AssemblyAI Universal-Streaming v3 with `language=Language.ES` handles Spanish + most English code-switching. ElevenLabs Turbo speaks both languages on one voice ID.

### Pronunciation feedback
**What.** Not "good job" — specific tips like "the *rr* in *perro* is rolled, try humming and tapping your tongue".
**How.** `pronunciation.py` has a dict of 10 curriculum-word-specific hints plus 12 general phoneme regex patterns. When the grader marks an answer wrong, the relevant hint is auto-attached to the LLM's correction.

### Memory (short + long term)
**Short term:** `SessionMemory` in RAM — mode, current lesson position, mistakes this session, frustration counter, recent topics.
**Long term:** SQLite tables — users, progress, vocab_mastery (FSRS fields), mistakes. Survives restarts.

### FSRS-lite spaced repetition
**What.** Words you struggle with come back tomorrow. Words you've mastered come back in days/weeks.
**How.** Each quiz answer calls `record_vocab_attempt(word, lang, success)`. Success → interval ×= ease, reps++; lapse → interval = max(1, interval/2), lapses++, ease decreased. `due_vocab()` returns rows where `next_review_at <= now`. Lapsed words are scheduled with a slight negative offset so they surface immediately.

### Frustration detection
Counter of `consecutive_failures` + a `frustration_score` that ticks up on repeated short angry-sounding replies. `is_frustrated()` returns true at threshold 3. The system prompt builder injects an addendum: "learner seems frustrated — slow down, encourage."

### Adaptive difficulty
`confidence_score` (0..1) — starts at 0.5, +0.08 per success, -0.10 per mistake. Surfaced in the per-turn context summary. The LLM sees the number and can choose easier or harder vocab.

### Prosody engagement detection (bonus)
RMS energy + pace WPM + inter-turn pauses → composite score → engaged / neutral / low label. Surfaced in the UI as a colored chip and used to nudge the LLM's tone each turn.

### Observability
Every turn writes one JSONL line: `STT text`, `LLM text`, `mode`, `tools called`, and every-stage timestamp. The `/metrics` endpoint exposes P50/P95 across STT, LLM TTFT, TTS first-audio, and total. Sufficient to answer the spec's "why did turn 14 take 2.3 s?" question.

### Reliability
Every external service is called inside try/except with Pipecat's built-in retry/backoff. If TTS fails, we fall back to a canned line and the session survives. If the LLM rate-limits, IntentRouter still routes future turns (so mode transitions don't break).

---

## 8. Problems I hit and how I fixed them

### Problem 1: AssemblyAI silently dropped Spanish
With `language=None`, the default is English-only mode. Spanish utterances → no transcript. Fix: explicit `language=Language.ES`. Documented because the failure mode (silent empty transcripts) is hard to debug.

### Problem 2: Bot kept hearing itself
On laptop speakers, the bot's own voice leaked back into the mic. STT transcribed the bot's words. The LLM thought the user was saying that. Infinite loop. Fix: server-side `MicGate` processor that drops audio during bot speech, allowing only loud barge-in (RMS > 2000) through. Default off because headphones already kill the loop.

### Problem 3: VAD fired on background noise
Default thresholds caught keyboard typing, AC hum. Fix: `confidence=0.75`, `min_volume=0.75`, `start_secs=0.25`, `stop_secs=0.30` — all env-overridable.

### Problem 4: Groq LLM rate-limit (100k tokens/day on free tier)
Initial prompts were ~2000 tokens per turn — burned through quota in ~50 turns. Fix: cut prompts to ~150 tokens, trim context to last 6 messages, cap LLM output at 80 completion tokens.

### Problem 5: Transcripts weren't reaching the UI
The aggregator was consuming `TranscriptionFrame` before it reached the serializer. Fix: added a `TranscriptForwarder` processor right after STT that re-emits the transcript as an `OutputTransportMessageFrame` (which the transport sends straight to the WebSocket).

### Problem 6: Latency UI showed "TTS 8 seconds"
I had marked `tts_first_audio_ms` at `BotStoppedSpeakingFrame` (end of bot speech) instead of `BotStartedSpeakingFrame` (start of audio output). The "8s" was measuring TTS duration, not TTFT. Fix: mark at `BotStartedSpeakingFrame`.

### Problem 7: Percentile bug — P50 > P95 with small samples
For n=2: `int(0.95*2) - 1 = 0` (lowest), `n//2 = 1` (highest). Fix: nearest-rank percentile (`min(n-1, round((n-1)*0.95))`).

### Problem 8: Llama tool-call parser kept failing with 11 tools
Got "Failed to call a function" errors. Fix: curated down to 4 essential tools (mode transitions only) and put a deterministic Python `IntentRouter` in the pipeline as a belt-and-suspenders.

### Problem 9: Bot auto-started lessons before user asked
Initial greeting was "You have 3 words due — want to review?" which primed the LLM to immediately act. Fix: greeting is always question-shaped, listing all options but not picking one. Plus a system note: "WAIT for user — do not proactively pick."

### Problem 10: Lesson didn't advance after "yes"
The intent router only handled mode entry, not within-mode navigation. Fix: in teaching mode, every user reply that isn't an intent keyword advances the lesson step (intro → explain → example → practice → check → done).

---

## 9. Likely interview questions, answered in my own voice

### Q. Why Pipecat over LiveKit?
The product is single-user, browser-only, no telephony. LiveKit's WebRTC SFU is overkill. Pipecat's in-process pipeline gives me frame-level hooks where I dropped in MicGate, IntentRouter, LatencyProbe, etc. If we needed to add telephony later, Pipecat has a LiveKit transport — we'd keep the pipeline and just swap the transport layer.

### Q. Why hand-rolled FSM instead of LangGraph?
Four modes, well-defined transitions, single agent. LangGraph's DAG semantics add ceremony — extra deps, opinionated state merging — without benefit. A 150-line FSM in `orchestrator.py` is auditable and easy to surface in logs.

### Q. How does barge-in actually work?
Silero VAD (running inline in the pipeline) detects speech onset by sustaining confidence ≥ 0.75 for ~30 ms. It fires `UserStartedSpeakingFrame`, which is a Pipecat system frame propagating both upstream and downstream. The TTS service sees it and cancels its WebSocket stream, dropping all pending audio. The transport serializer emits a `{type: "interrupt"}` JSON event. The browser client receives that and calls `flushPlayback()`, which destroys and recreates the GainNode — instantly silencing all scheduled BufferSource nodes. Total latency: ~150–250 ms.

### Q. How does the agent know when to switch modes?
Two paths. The LLM can call one of four tools (`start_lesson`, `start_quiz`, `enter_doubt_mode`, `exit_doubt_mode`) — that's the canonical path. The deterministic `IntentRouter` is a safety net: it scans every user transcript for keyword sets and triggers the same Python handlers. If both fire for the same utterance, the tool runner is idempotent so no harm done.

### Q. How do you grade answers semantically?
Two tiers. First, deterministic: normalise both strings (NFD Unicode → strip accents → lowercase → strip punctuation → collapse whitespace), check exact match, then variant list (from the curriculum), then token Jaccard similarity. If Jaccard is in the middle band (0.35 < J < 0.75), fall back to an LLM call with a strict JSON output schema. Most graders never hit the LLM.

### Q. How do you handle code-switching?
AssemblyAI Universal-Streaming v3 with `language=Language.ES` handles primary Spanish plus most English code-switched phrases. The transcript carries a language tag downstream. The LLM prompt explicitly says "explanations in English, Spanish only for target vocab and examples." ElevenLabs Turbo speaks both on one voice ID so the bot's reply never has voice-swap artifacts.

### Q. Walk me through long-term memory.
SQLite, four tables. `vocab_mastery` is the interesting one — implements FSRS-lite (a simplified version of the FSRS / SM-2 spaced-repetition algorithm). Each row has `ease` (1.3–2.5), `interval_days`, `reps`, `lapses`, `next_review_at`. Quiz grader writes here. The "Due for Review" panel reads here. Lapsed words get scheduled with a slight negative offset so they immediately appear.

### Q. What's your latency budget?
Headline metric is end-of-user-speech → first audible bot token. Budget: 1500 ms. Measured P50: ~880–1010 ms on localhost. Stage breakdown: VAD endpoint ~250 ms, STT finalize ~150 ms, LLM TTFT ~300 ms (Llama 3.1 8b on Groq), TTS first chunk ~350 ms, network ~50 ms. Logged per turn in `logs/turn_latency.jsonl` so any regression shows up.

### Q. How do you debug a slow turn?
Read one JSONL line. It has every stage timestamp. `total_ms - tts_first_audio_ms` isolates TTS. `llm_first_token_ms - stt_final_ms` isolates LLM. The spec specifically asks for the ability to answer "why did turn 14 take 2.3 s?" — this JSONL is the answer.

### Q. What's the cost story?
Free tier covers the demo. Paid: roughly $0.10 per 5-minute session — AssemblyAI STT at $0.65/hr (~$0.054 for 5 min) plus ElevenLabs Starter TTS (~$0.05). Groq is pennies/session at paid tier. Documented in WRITEUP.

### Q. Where would this fail at scale?
SQLite WAL is fine to hundreds of writes/sec on a single box but not horizontal — Postgres replacement is straightforward (no ORM). ElevenLabs free tier caps 10k chars/month — easy to blow through. Each WS connection holds a Python process; scaling needs Kubernetes + a worker pool. No auth currently; single hardcoded user.

### Q. What would you build next with more time?
Real phoneme-level pronunciation scoring (Azure Pronunciation Assessment), telephony via LiveKit SIP, streaming partial-transcript grading (start grading on interim transcripts), LLM-authored lessons with a human-review gate, multi-user with auth + per-user voice preferences, frontend support for visual progress charts.

### Q. Where did AI help in writing this?
Anthropic's Claude Code acted as the assistant. I drove all the architecture, decision-making, and review judgments. Claude generated boilerplate (typed dataclasses, repetitive React components), suggested patterns, and helped catch a Postgres-style SQL query I'd inadvertently written. Every line was read before commit. Disclosed up front in the write-up.

### Q. Why did you skip telephony and on-device Whisper?
Telephony via Twilio/LiveKit SIP would require infrastructure work disproportionate to demo value — the product is browser-first. On-device Whisper (whisper.cpp) would matter for offline-first apps; Groq's hosted Whisper Turbo runs at ~250 ms, faster than any local CPU build, so the trade-off is wrong for this product.

### Q. What did you cut?
Nothing in the core 4-mode loop. Skipped 2 of 7 stretch goals (telephony, on-device Whisper) with documented rationale. Curriculum kept at 6 lessons (spec minimum 3) — adding more is a JSON edit, didn't want to bloat for the sake of bloat.

---

## One-paragraph close

The thing I'm most proud of isn't any single feature — it's that the whole loop *feels* like talking to a human teacher. Sub-1-second latency, barge-in that actually cuts the bot off mid-word, mistakes that come back in tomorrow's review, and a transcript bubble that updates live as you speak. The engineering trade-offs are documented honestly — I picked AssemblyAI over Deepgram because of free-tier reality, I dropped LLM function calling for IntentRouter when Llama's parser flaked, I shrank prompts 70 % when the rate limit hit. Each decision is recorded in the WRITEUP decision log. That's the actual interview material: not what I built, but *why* and *what I traded for what*.
