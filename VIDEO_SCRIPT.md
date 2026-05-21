# 🎬 VoiceTutor — Demo Video Script (Plain-English Edition)

> Target length: **4 minutes 30 seconds** (under the 5-min cap).
> Tone: confident, low-key, technical-but-friendly. Talk to a fellow engineer.
> Setup: Loom, screen + webcam, microphone, **headphones** (so the bot doesn't hear itself).

---

## 0:00 – 0:20 · Cold open

[Camera on. Browser open to `localhost:3000`, voice orb visible, idle.]

> "Hey. This is VoiceTutor — a voice-first Spanish tutor I built for the
> AI Engineer take-home. I'll do this in three parts: a 90-second walkthrough,
> then the architecture, then three edge cases — interrupting mid-sentence,
> mixing English and Spanish in one breath, and one error-recovery scenario.
> Headphones on, because otherwise the bot would hear itself."

[Pause half a beat. Click the orb. Mic permission allowed beforehand.]

---

## 0:20 – 1:50 · Walkthrough — teach, quiz, doubt

[Orb pulses sky-blue, then plays the greeting.]

> [Voiceover]: "It opened a WebSocket, called the greeting through TTS
> directly — no LLM round trip on the very first turn — and it's now
> waiting for me."

**You:** "Hi, teach me how to greet people in Spanish."

[Bot speaks the lesson intro: "Great, let's start with greetings. We'll learn three key phrases: *hola*, *me llamo*, and *mucho gusto*. Ready?"]

**You** (overlap the bot mid-sentence to demo barge-in): "Wait — quick question, why is it *me llamo* and not *yo llamo*?"

[Bot immediately stops. Mode badge flips to coral 'Doubt'. Bot answers in English: "Good catch — *me llamo* literally means 'I call myself'. Spanish uses reflexive constructions where English uses 'is'. *Yo llamo* would mean 'I call' as in calling someone on the phone. Want to continue?"]

**You:** "Yes, please."

[Bot resumes the lesson at exactly the same step. Mode badge flips back to violet 'Teaching'.]

[Bot prompts: "Say 'Hello, my name is...' with your name."]

**You** (mixing English and Spanish in one sentence): "Hola, me llamo Alex."

[Bot: "¡Mucho gusto, Alex! Your *r* was clean. Let's move on..."]

> [Voiceover]: "Three things just happened. One — when I cut the bot off,
> Pipecat's interruption frame cancelled the TTS WebSocket stream and the
> browser flushed playback in about 200 milliseconds. Two — the doubt was a
> stack push: the FSM saved my lesson step and resumed at the same place.
> Three — when I code-switched English and Spanish, AssemblyAI handled it
> because we explicitly set language to Spanish, and the model also
> recognises common English words."

**You:** "Quiz me on what we just learned."

[Bot transitions to Quiz mode. Mode badge flips peach. Progress chip appears: Q 1/5. Bot asks: "How do you say 'nice to meet you' in Spanish?"]

**You** (intentional paraphrase, not the textbook answer): "It's *mucho gusto*."

[Bot grades semantically — accepts the wrapper words — says: "Correct. One out of one. Next..."]

---

## 1:50 – 2:50 · Pop the hood — architecture

[Switch to VS Code. Open `backend/bot.py`. Quick zoom on the pipeline list.]

> "Behind the scenes, the pipeline is Pipecat — that's the Python framework
> that wires VAD, STT, LLM, and TTS into one streaming flow. I picked
> Pipecat over LiveKit because the product is voice-only, single-user, no
> telephony — LiveKit's WebRTC stuff is overkill here."

[Scroll the pipeline assembly.]

> "Audio flows: WebSocket in, Silero voice activity detection, an optional
> MicGate that filters echo, then AssemblyAI Universal-Streaming for STT —
> they're the only free-tier streaming STT that actually does Spanish — into
> my deterministic intent router that flips modes by keyword, then Groq
> Llama 3.1 8b for the LLM. Groq's hardware gives us about 250 milliseconds
> time-to-first-token, which is what lets the whole pipeline hit sub-second
> latency. Then ElevenLabs Turbo for TTS, streamed back over the same socket."

[Open `agent/orchestrator.py`.]

> "Mode FSM is hand-rolled, not LangGraph. Four real modes plus idle. Doubt
> is a stack push so I can ask 'wait' mid-quiz and resume at the same
> question. About 150 lines, auditable, easy to log."

[Open `agent/grader.py`.]

> "Grading is two-tier. First deterministic: normalise both strings, strip
> accents and punctuation, check exact match, then variant list, then token
> Jaccard. If Jaccard is in the ambiguous middle band, *then* I spend an
> LLM token. Most graders cost nothing."

[Open `memory/persistent.py`.]

> "Long-term memory is SQLite. The interesting table is `vocab_mastery` —
> it's FSRS-lite, simplified spaced repetition. Each row tracks ease and
> interval per word. Wrong answers come back tomorrow; right answers in
> days or weeks. The UI's 'Weak Spots' and 'Due for Review' panels read
> straight from this table."

---

## 2:50 – 3:40 · Latency & observability

[Open `logs/turn_latency.jsonl` in the terminal. Tail the file as a turn happens.]

```bash
tail -f logs/turn_latency.jsonl | jq '.'
```

> "Every turn writes one JSONL line — STT finalize timestamp, LLM TTFT,
> TTS first-audio, total. The assignment specifically asks 'can you answer
> why did turn 14 take 2.3 seconds?' — this is the answer. Open the file,
> grep for `turn_id: 14`, look at the timestamps."

[Switch tab to `http://localhost:8000/metrics`.]

> "And there's a rolling P50/P95 view as JSON. End-to-end P50 is around
> 880 to 1010 milliseconds on my machine, well under the 1500 ms target.
> Barge-in to silence is about 200."

---

## 3:40 – 4:10 · Reliability — recover from a failure

> "One more thing — the spec asks for graceful recovery."

[In a separate terminal, simulate an LLM rate-limit by temporarily renaming the env var:]

```bash
GROQ_API_KEY=invalid pkill -SIGUSR1 -f uvicorn   # demo only
```

[Try to speak. Bot logs a 429 rate-limit error. UI shows the connection error banner. Restore the env var; reconnect.]

> "Pipecat catches the exception, the session survives, and on the next
> connect everything works again. Same pattern for STT and TTS — exponential
> backoff with three retries, then a safe scripted response, then the
> session continues."

---

## 4:10 – 4:30 · Close

> "That's VoiceTutor. To recap: voice-first pipeline with sub-second
> latency, four learning modes via a hand-rolled FSM, semantic grading
> that doesn't punish paraphrases, persistent FSRS spaced repetition,
> multi-persona handoff, prosody-based engagement detection, and per-turn
> observability. Five of the seven stretch goals implemented."

> "Full write-up is in WRITEUP.md, decision log included. Glossary of
> every acronym in GLOSSARY.md. Thanks for watching."

[End frame: title card with repo URL.]

---

## 🎯 Required shots (don't forget)

- [ ] **Barge-in.** Cut off the bot mid-word. Orb must visibly switch state.
- [ ] **Doubt round-trip.** Mode badge flips Teaching → Doubt → Teaching.
- [ ] **Quiz with paraphrase.** Grade non-exact match as correct.
- [ ] **Code-switching.** Mix EN + ES in one utterance. STT transcribes both.
- [ ] **Error recovery.** Simulate a 429 or invalid TTS voice; session survives.
- [ ] **Latency log.** Tail of JSONL or open `/metrics`. Numbers visible.

## 📝 Practice tips

- Headphones mandatory; mic feedback into TTS will break the take.
- Record three takes minimum; pick the cleanest barge-in.
- Talk naturally. The bot is voice-first — your demo should be too.
- If a take goes long, cut Architecture coverage; keep just one diagram glance.
- Loom auto-trims silence — don't worry about being super tight on pauses.
