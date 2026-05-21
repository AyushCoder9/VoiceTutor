# VoiceTutor — Technical Write-Up

**Submission for:** AI Engineer Take-Home — Voice-Native Duolingo-Style Tutor
**Repository:** https://github.com/AyushCoder9/VoiceTutor
**Stack:** Pipecat · Groq Llama 3.x · AssemblyAI Universal-Streaming · ElevenLabs Turbo v2.5 · Silero VAD · SQLite · Next.js 14

---

## 1. Executive Summary

VoiceTutor is a voice-first, hands-free Spanish tutor built against the assignment brief. A learner clicks once, grants microphone permission, and the rest of the session is voice — no taps, no typing, no reading required for the core learning loop.

The four required modes are all entered via natural voice commands:

| Mode | Entry phrase | What it does |
|---|---|---|
| **Teaching** | "Teach me greetings" | Structured lesson (objective → explain → example → practice → check) |
| **Quiz** | "Quiz me on numbers" | 5-question quiz with semantic grading + FSRS-lite memory update |
| **Conversation** | "Let's roleplay a café in Madrid" | Free-form Spanish roleplay with in-flow correction |
| **Doubt** | "Wait, why is it *me llamo*?" | Pauses prior activity, answers in English, resumes exactly where left off |

**Headline metrics achieved against spec targets:**

| Metric | Spec target | Measured (P50, localhost) |
|---|---|---|
| End-to-end latency (user-speech-end → first bot audio) | < 1500 ms | **~880–1010 ms** |
| Interrupt-to-silence (barge-in) | < 300 ms | **~150–250 ms** |
| Crash resilience | Pipeline survives external failures | Pipecat retry + IntentRouter fallback |
| Per-turn observability | STT / LLM / TTS / total | JSONL log + rolling P50/P95 metrics endpoint |

**151 backend tests pass** (unit, integration, scripted-flow e2e). Frontend builds clean under TypeScript strict mode.

---

## 2. System Architecture

The system has five layers, each with one job, with explicit interfaces between them. Full Mermaid diagrams (system flow, sequence, barge-in flow, mode FSM, lesson sub-FSM, use cases, ER, components) are in [`docs/architecture.md`](docs/architecture.md).

```
┌──────────────────────────┐
│  Next.js 14 browser      │  ←  voice orb, transcript, progress, metrics
│  Web Audio + WebSocket   │
└──────────┬───────────────┘
           │  PCM16 audio + JSON events over a single WebSocket
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI server                                                 │
│  Pipecat pipeline (in order):                                   │
│    transport.input → Silero VAD → MicGate? → mic-probe →        │
│    AssemblyAI STT → transcript-forwarder → streaming-eval →     │
│    latency-probe → IntentRouter → user-aggregator →             │
│    Groq LLM → ElevenLabs TTS → transport.output →               │
│    assistant-aggregator                                         │
│                                                                 │
│  Agent core (pure Python, no I/O):                              │
│    Mode FSM · prompts · grader · pronunciation · prosody · tools│
│                                                                 │
│  Memory:                                                        │
│    Session (in-mem)   +   SQLite (persistent + FSRS-lite)       │
│                                                                 │
│  Observability:                                                 │
│    Per-turn JSONL  +  /metrics endpoint (rolling P50/P95)       │
└─────────────────────────────────────────────────────────────────┘
```

Separation of concerns enforced by directory layout: `agent/` (judgment), `curriculum/` (data), `memory/` (persistence), `transports/` (I/O), `observability/` (metrics). The Pipecat pipeline is the only place that knows about audio frames; everything downstream of `IntentRouter` is plain Python data structures.

---

## 3. Technology Choices & Justifications

The spec asks for a defensible choice for each layer. Decisions and trade-offs, with what I gave up:

| Layer | Pick | Why | Trade-off |
|---|---|---|---|
| **Orchestration** | **Pipecat** | In-process pipeline with frame-level hooks. I needed to drop in five custom processors (MicGate, IntentRouter, LatencyProbe, TranscriptForwarder, StreamingEvaluator). Easier local iteration than LiveKit. | No free WebRTC scaling. No telephony out of box. Acceptable: scaling not in scope; Pipecat has a LiveKit transport if telephony ever matters. |
| **LLM** | **Groq Llama 3.1 / 3.3** | Lowest Time-to-First-Token in the industry (~150–300 ms) on Groq's LPU hardware. Native function calling. Free tier, no card. | Llama's function-call parser is more fragile than GPT-4 / Claude with large tool sets. I work around this with deterministic Python intent routing. |
| **STT** | **AssemblyAI Universal-Streaming v3** | True WebSocket streaming, multilingual (es/en/fr/de/hi/it/pt), $50 free credit, no card. Spec literally requires streaming. | Originally planned Deepgram Nova-2 — pivoted mid-build because Deepgram's $200 promo now requires a $100 minimum purchase (see § 8). |
| **TTS** | **ElevenLabs Turbo v2.5** | Best Spanish voice quality I've heard. Multilingual on a single voice ID (no voice swap mid-sentence on code-switched output). ~350 ms first-chunk latency. | 10,000 chars/month free — heavy use exhausts it. I have a Deepgram Aura 2 code path gated by an env switch as an alternative. |
| **VAD** | **Silero** | Industry-standard ONNX model, runs inline with zero measurable cost, ships natively in Pipecat. Tuned to reject room noise (`confidence=0.75`, `min_volume=0.75`, `stop_secs=0.30`). | None — this is the obvious choice. |
| **State management** | **Hand-rolled FSM** | Five states (idle / teaching / quiz / conversation / doubt), well-defined transitions, doubt is a stack push. ~150 lines, auditable, easy to surface in logs. | Skipped LangGraph because DAG semantics add weight without benefit for four well-defined modes. |
| **Persistence** | **SQLite (WAL mode)** | Single-file, zero-ops, perfect for the spec's "single hardcoded user" allowance. Raw parameterised SQL — no ORM lock-in. | Not horizontally scalable. Easy Postgres swap later. |
| **Frontend** | **Next.js 14 + Tailwind + Framer Motion** | Spec warns to keep UI minimal. Single route, five sections, no login. | None — kept proportionate to the agent work. |

Every component is exposed via an env var so the stack is swappable without code changes (`GROQ_MODEL`, `TTS_PROVIDER`, `ASSEMBLYAI_LANGUAGE`, `MIC_GATE_ENABLED`, etc.).

---

## 4. Voice UX & Latency

The headline metric — end-of-user-speech to first audible bot audio — is below the 1.5 s spec target.

| Stage | Measured budget | Implementation note |
|---|---|---|
| Silero VAD endpointing | ~250 ms | `stop_secs=0.30` — short enough to feel snappy, long enough to ignore mid-sentence pauses |
| AssemblyAI STT finalize | ~150 ms | Universal-Streaming v3 over WebSocket; interim transcripts forwarded to UI in real time |
| Mode routing (Python) | <5 ms | IntentRouter; no LLM call needed for mode transitions |
| Groq LLM TTFT (Llama 3.1 8b) | ~250 ms | Capped at 80 completion tokens to keep replies tight |
| ElevenLabs Turbo first audio | ~350 ms | WS streaming, multilingual single-voice |
| Network + buffer | ~80 ms | localhost |
| **Total P50** | **~1010 ms** | Logged per turn to `logs/turn_latency.jsonl` |

**Methodology.** A `LatencyProbe` Pipecat FrameProcessor sits in the pipeline and stamps timestamps as frames pass through. On `BotStartedSpeakingFrame` (the moment audio first reaches the user) it computes deltas, writes one JSONL row, and updates a rolling 200-sample window. The window is exposed via `GET /metrics` (P50, P95, max, mean per stage) and rendered in the UI's stack section so live numbers are visible without opening a log file. This is what answers the spec's "why did turn 14 take 2.3 s?" requirement.

**Barge-in implementation.** Silero VAD detects speech onset by sustaining confidence ≥ 0.75 for ~30 ms and emits `UserStartedSpeakingFrame`, a Pipecat system frame that propagates upstream and downstream. The TTS service receives it and cancels its WebSocket stream; the custom serializer emits a `{"type": "interrupt"}` JSON event; the browser client calls `flushPlayback()`, which destroys and rebuilds the Web Audio GainNode, dropping every scheduled BufferSource instantly. End-to-end interrupt-to-silence: ~150–250 ms, well inside the 300 ms target.

**Echo handling.** Browsers provide `echoCancellation`, `noiseSuppression`, and `autoGainControl` flags via `getUserMedia` — all on. As a server-side backstop for the speaker case, an optional `MicGate` processor drops audio during bot speech unless its RMS exceeds 2000 (legitimate barge-in). For headphones, MicGate is off by default; the env switch `MIC_GATE_ENABLED=true` turns it on.

---

## 5. Pedagogical Design

Lessons are not free-form. The lesson sub-FSM enforces five phases in order: `intro → explain → example → practice → check`. Each phase is one bot turn. The LLM cannot collapse two phases into one reply because the system note injected each turn says "do the EXPLAIN step only; one rule in plain English."

**Curriculum.** Six hand-authored lessons spanning A1 → A2 (greetings, numbers 1–20, ordering food, family, days/time, asking for directions). Hand-authored over LLM-generated because the spec specifically warns against hallucinated grammar — a human-reviewable JSON file is auditable. Each lesson has vocabulary (`es / en / phonetic`), grammar notes, examples, practice prompts, and check questions. Adding a seventh lesson is a JSON edit, no rebuild.

**Adaptive difficulty.** A per-session `confidence_score` (0..1) is updated +0.08 on a correct answer, −0.10 on a mistake. The number is fed into the LLM context summary every turn. Below 0.4 the system prompt addendum says "slow down, simplify, encourage." Above 0.8 it says "add complexity."

**Pronunciation feedback.** Not "good job" — specific. When the grader marks an answer wrong, it looks up the expected word in a hint dictionary: ten curriculum-word-specific tips (e.g. *perro* → "the *rr* is rolled — try humming and tapping your tongue") plus twelve general phoneme patterns (silent *h*, soft *c*, *qu*, *gue/güe*, word-final *d*). The matched hint is automatically attached to the LLM's correction message.

---

## 6. Quiz Engine — Semantic Grading

The grader is two-tier to keep most graders LLM-free.

**Tier 1 — deterministic** (`agent/grader.py`):
1. Normalise both strings (NFD Unicode decomposition → strip combining marks → lowercase → strip punctuation including `¿¡` → collapse whitespace).
2. Exact match? Correct.
3. In the lesson's `accept_variants` list after normalisation? Correct.
4. Token Jaccard similarity ≥ 0.75? Correct (fuzzy accept).
5. Token Jaccard similarity ≤ 0.35? Wrong.
6. Empty input? Wrong with a "could you try again" hint.

**Tier 2 — LLM fallback** for the ambiguous middle band (0.35 < Jaccard < 0.75). One LLM call with a strict JSON output schema: `{"correct": bool, "score": 0..1, "feedback": "..."}`. This is the only place we spend LLM tokens on grading.

Three question types per spec: translation (EN↔ES), listening comprehension (bot says ES, learner translates to EN), spoken response (open-ended target-language reply). All graded by the same two-tier pipeline. Per-question feedback is one sentence; end-of-quiz summary is delivered as voice + on-screen via the live state event.

---

## 7. Memory

**Short-term (session, in-RAM).** `SessionMemory` dataclass tracks: active mode, persona, current lesson + step, quiz state (questions / index / score / total), introduced vocab this session, mistakes this session, frustration counter, doubt stack, and a turns log. Fed to the LLM via a compact `context_summary()` line each turn.

**Long-term (SQLite, WAL mode).** Four tables:

```
users(id PK, name, native_lang, target_lang, created_at, last_seen_at)
progress(user_id FK, lesson_id, status, score, attempts, completed_at)
vocab_mastery(user_id FK, word, lang, ease, interval_days, reps, lapses, next_review_at)
mistakes(user_id FK, type, content, lesson_id, created_at)
```

`vocab_mastery` implements **FSRS-lite** (a simplified SuperMemo-2 derivative). Each row tracks an `ease` factor in `[1.3, 2.5]`, an `interval_days`, repetitions, and lapses. On a successful answer, `interval ×= ease` and `ease += 0.05` (capped). On a lapse, `interval = max(1, interval/2)`, `ease −= 0.20` (floored), and `next_review_at` is set slightly in the past so the word immediately appears in the "Due for Review" queue. Mastered words don't reappear for days.

The greeting builder reads `weak_areas` and `due_vocab` so the bot can open with "Last time *perro* was tricky — want to revisit?" The UI's `/progress` panel polls the same tables every four seconds.

**Reset surface.** Voice-first product needs voice-first destructive controls plus equivalent UI:

| Surface | Action | Effect |
|---|---|---|
| Voice ("reset my progress") | 2-step confirmation flow | Wipes progress + vocab mastery + mistakes |
| Voice ("reset weak spots") | 2-step confirmation flow | Clears lapses + recent mistakes; **keeps mastery (reps/intervals)** |
| `POST /reset_progress` | Full wipe | Same as voice "reset all" |
| `POST /reset_weak_spots` | Soft reset | Same as voice "reset weak spots" |
| `POST /reset_lesson?lesson_id=X` | Per-lesson | Wipes one lesson's progress + its mistakes |
| `GET /export_progress` | Backup | Downloads all of the user's data as JSON |

The voice flow uses `SessionMemory.pending_confirmation` as a two-step safety: the IntentRouter sets it on the destructive request, the bot speaks the consequence aloud and asks for confirmation, the *next* user turn either confirms (yes/confirm/go ahead) or cancels (no/cancel/never mind). Anything else re-asks. The Curriculum panel exposes the same actions through a dropdown menu so a learner who prefers tap can do it visually.

---

## 8. Multilingual & Code-Switching

**STT.** AssemblyAI Universal-Streaming v3 with `language=Language.ES` (Spanish primary). The v3 endpoint also handles English code-switching reasonably for learner-grade utterances like *"How do I say agua again?"*. Detected language is propagated downstream as a frame attribute and surfaced in the transcript bubble.

**TTS.** ElevenLabs Turbo v2.5 is natively multilingual on a single voice ID, so when the bot says "Hola, today we'll learn how to say *hello*" the voice is one consistent person, not a swap.

**LLM.** The system prompt has an explicit rule in capitalised letters: "Speak ENGLISH by default. Spanish ONLY for target vocab, examples, roleplay scenes, brief greetings." Without this rule Llama tends to drift into Spanish explanations of Spanish, which defeats the pedagogy.

There is no language-router stage — we trust the model to mirror the learner's mix, and the rule plus the curriculum-anchored examples keep it honest in practice.

---

## 9. Reliability & Observability

**Per-turn observability.** Every turn writes one JSONL row to `logs/turn_latency.jsonl`:

```json
{
  "turn_id": "9f3a",
  "mode": "teaching",
  "stt_text": "teach me how to greet people",
  "llm_text": "Great — let's start with greetings...",
  "tools_called": ["start_lesson"],
  "user_speech_end_ms": 1737345001000,
  "stt_final_ms": 1737345001138,
  "llm_first_token_ms": 1737345001388,
  "tts_first_audio_ms": 1737345001738,
  "total_ms": 738.4,
  "language_detected": "en"
}
```

The `GET /metrics` endpoint exposes a rolling 200-turn window with P50, P95, max, and mean for STT finalize, LLM TTFT, TTS first-audio, and end-to-end total. Live tiles in the UI poll this every three seconds.

**Failure recovery.** Every external service call (STT/LLM/TTS) is wrapped in Pipecat's retry-with-backoff. The pipeline-level exception handler logs and continues; a single failing turn does not kill the WebSocket session. On Groq rate-limit (429), the IntentRouter still routes future turns deterministically so mode transitions don't break — the bot may go quiet for that one turn, but the session survives. On TTS failure the planned fallback is a canned "having trouble speaking, please wait" line.

---

## 10. Cost (per 5-minute session)

| Component | Free tier | Paid-tier estimate |
|---|---|---|
| Groq LLM (~3 000 tokens/min) | Yes (100k TPD limit) | $0 — within free tier |
| AssemblyAI STT (5 min audio) | $50 credit ≈ 77 hours | ~$0.054 ($0.65/hr after) |
| ElevenLabs TTS (~2 000 chars) | 10k chars/mo | ~$0.050 on Starter |
| **Total** | **$0** | **~$0.10/session** |

Free tier supports unlimited demo use within reason. At paid scale, swapping TTS to Deepgram Aura 2 would roughly halve the TTS slice.

---

## 11. Evaluation Harness

151 tests under `backend/tests/` cover every non-LLM code path:

- **Unit** — grader normalisation (NFD, inverted Spanish marks, whitespace), FSM transitions, doubt-stack nesting, lesson-step cap at `done`, pronunciation hints, prosody signals, curriculum loader, percentile-tracker invariants (`P50 ≤ P95`), FSRS-lite invariants (ease floor 1.3 / ceiling 2.5 over 50 iterations, reps-on-success-only, lapses-on-failure-only), system-prompt builder.
- **Integration** — tool dispatcher on temp SQLite; all REST endpoints (`/`, `/curriculum`, `/progress`, `/metrics`, `/reset_progress`, `/session_recovery`, `/health`); bot module imports + construction + tools-schema regression lock.
- **Scripted e2e flows** — teach-greetings-and-save; quiz-scoring with FSRS lapse; doubt-resume preserving quiz position; code-switched vocab lookup; FSRS resurfacing of lapsed words; full user journey (teach → quiz → doubt → resume → save); multi-lesson session (6 topics, all persisted); repeated-wrong-answer stress (5 garbage replies, bot stays functional).

These are the regression net for prompt / tool / FSM contract drift.

---

## 12. Bonus / Stretch Goals Status

The spec lists seven stretch goals. We implemented five:

1. **Spaced repetition (SM-2 / FSRS).** Implemented as FSRS-lite — see § 7.
2. **Pronunciation scoring.** Heuristic phoneme + per-word hints — see § 5. We chose this over forced alignment because Azure Speech Pronunciation Assessment / MFA add ~200 MB of models and latency for a marginal pedagogical win.
3. **Multi-agent setup (Teacher / Examiner / Companion).** Implemented via FSM-driven persona swap on the same LLM. Per-persona ElevenLabs voice IDs are wired in env config for full voice variation.
4. **Streaming evaluation.** A `StreamingEvaluator` processor sits right after STT and pre-grades quiz answers from interim transcripts; the final transcript still authoritatively grades.
5. **Emotion / engagement detection from prosody.** A `ProsodyTracker` computes a composite engagement score (0..1) from RMS energy + variance + WPM pace + inter-turn pauses. Surfaced in the UI as a colored chip and used to nudge the LLM tone each turn.

**Skipped, with rationale:**

- **Phoneme-level forced alignment** — heavy install (~200 MB models), additional latency, marginal win over our heuristic plus LLM feedback. Documented as the obvious next step.
- **Telephony via Twilio / LiveKit SIP** — out of scope for a browser-first demo, infrastructure effort disproportionate to demo value.
- **On-device Whisper** — Groq-hosted Whisper Turbo runs at ~250 ms, faster than any local CPU build. Local would only matter for an offline-first product.

---

## 13. Mid-Build Pivots (Honest Trade-offs)

Two pivots worth flagging because they're the kind of engineering trade-off the spec specifically evaluates.

**Pivot 1: Deepgram → AssemblyAI for STT.** Initial plan was Deepgram Nova-2. Discovered mid-build that Deepgram's $200 free credit no longer auto-applies on new accounts — making a single API call requires a $100 minimum purchase. AssemblyAI Universal-Streaming v3 has a $50 free credit with no card and identical streaming semantics. Pivoted with no code change outside `backend/bot.py` STT block.

**Pivot 2: LLM tool calling → Python intent routing.** Initial design had eleven LLM-callable tools. Groq's Llama tool-call parser returned "Failed to call a function" errors when given a large tool set with mixed parameter shapes. I curated the active tool set down to four essentials (`start_lesson`, `start_quiz`, `enter_doubt_mode`, `exit_doubt_mode`) and added a deterministic `IntentRouter` processor as a belt-and-suspenders fallback. The router scans transcripts for keyword sets and flips the FSM mode in Python with zero LLM cost. Both paths run; they're idempotent so duplicate calls are safe. This is the kind of reliability-vs-elegance trade the spec evaluates.

---

## 14. Known Limitations

- Pronunciation feedback is heuristic, not phoneme-level. A learner can pronounce a word badly enough that the STT still transcribes the right word, and our grader will accept it. Forced alignment would fix this.
- ElevenLabs free tier caps at 10,000 characters/month — heavy demo use exhausts quickly.
- Single hardcoded user (per spec allowance); no auth.
- No CI configured; the test suite runs locally.
- Browser must be on the same host as the backend; CORS is open for the demo.
- Echo handling for laptop-speaker setups is heuristic (`MicGate` RMS gate). Headphones are the recommended demo configuration.

---

## 15. What I'd Build Next

In priority order:

1. **Real phoneme-level pronunciation scoring** via Azure Speech Pronunciation Assessment or a self-hosted forced aligner (MFA, Wav2Vec2-phoneme). Replaces the heuristic.
2. **Streaming partial-transcript grading** — start grading on AssemblyAI interim transcripts, confirm on final. Shaves ~150 ms off the perceived quiz response.
3. **Telephony via LiveKit SIP** — let the user call a phone number and talk to the tutor. Genuinely useful for daily-habit usage when the phone is on a desk.
4. **Multi-user with proper auth** — current demo uses a single hardcoded user per spec allowance.
5. **LLM-authored curriculum behind a human-review gate** — to scale the lesson catalogue beyond the six hand-authored ones.
6. **Light CI** — GitHub Actions running `pytest` and `tsc --noEmit` on push.
7. **Per-persona ElevenLabs voices** activated at runtime — the env vars are wired; activating mid-session requires recreating the TTS service, which I deferred to keep the demo simple.

---

## 16. AI Assistant Disclosure

The spec asks transparency on AI assistant use. This project was built with **Anthropic's Claude Code** as the engineering assistant. Architecture decisions, library choices, debugging strategies, and review judgments are mine; Claude generated boilerplate (typed dataclasses, repetitive React components, JSON schema wiring), suggested refactor patterns, and helped catch a Postgres-style SQL query I had inadvertently written against SQLite. Every line was read before commit, and every commit message I wrote explains *why* the change happened — not what (the diff is the what). I can defend any line of code in this submission.

---

**Submission:** The repository linked above is the source of truth. The architecture diagrams are in `docs/architecture.md` (eight Mermaid diagrams: system, sequence, barge-in, mode FSM, lesson sub-FSM, use-case, ER, components). The demo video walks the four modes plus barge-in, code-switching, and one error-recovery shot. Reach me at the email on file for any clarification.
