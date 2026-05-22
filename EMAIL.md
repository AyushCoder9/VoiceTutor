# 📧 Submission Email — Draft

> **Subject:** `[AI Engineer Assignment] Ayush Kumar Singh`
>
> **To:** the hiring contact

---

Hi <Hiring Contact First Name>,

Here's my submission for the AI Engineer voice-agent take-home.

**Repository:** https://github.com/AyushCoder9/VoiceTutor
**Demo video:** https://drive.google.com/drive/folders/1VpLzhM1W6FdSsT7iS8BHELZQLjcswCoV?usp=sharing
**Write-up:** [`WRITEUP.md`](https://github.com/AyushCoder9/VoiceTutor/blob/main/WRITEUP.md) (architecture, decision log, latency measurements)

**One-paragraph summary.** VoiceTutor is a voice-first Spanish tutor on Pipecat. It supports all four required modes — Teaching, Quiz, Conversation, Doubt — entered via natural voice commands, with full-duplex audio, sub-1.5 s end-to-end latency (P50 ~880–1010 ms on my machine), real barge-in (<250 ms to silence), semantic answer grading that accepts paraphrases, code-switching-aware STT, persistent per-user progress in SQLite with FSRS-lite spaced repetition, multi-persona handoff (Teacher / Examiner / Companion), prosody-based engagement detection, and per-turn JSONL observability so you can answer "why did turn 14 take 2.3 s?" by reading one log line. Stack: Pipecat + Groq Llama 3.x + AssemblyAI Universal-Streaming + ElevenLabs Turbo v2.5 + Silero VAD, with a Next.js 14 minimal UI. 151 unit / integration / e2e tests pass. Six hand-authored lessons spanning A1 → A2. We hit 5 of 7 spec stretch goals (FSRS, pronunciation feedback, multi-persona, streaming evaluation, prosody engagement); we skipped telephony and on-device Whisper with documented rationale.

**Honest mid-build pivot.** We initially planned Deepgram Nova-2 for STT; mid-build we discovered Deepgram's $200 free credit no longer auto-applies (it requires a $100 minimum purchase). We swapped to AssemblyAI Universal-Streaming with no change to the rest of the pipeline. This kind of free-tier reality is exactly the engineering trade-off the spec asks about, and we documented it in WRITEUP D4.

**What I'd build next if I had another 48 hours.** Real phoneme-level pronunciation scoring (Azure Pronunciation Assessment), telephony via LiveKit SIP, streaming partial-transcript grading, and a small CI pipeline. I prioritised reliable depth on the core loop over feature breadth — full reasoning in the write-up.

Happy to walk through any of it live.

Best,
Ayush Kumar Singh
<Phone> · <Personal email>
