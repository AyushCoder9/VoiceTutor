"""Pipecat pipeline assembly (Pipecat 1.2.x).

This file is the *only* place where the pipeline gets wired together. The
six custom `FrameProcessor` classes are deliberately defined as inner
classes inside `LanguageTutorBot.run()` so each one captures the bot's
session / memory / FSM via closure — no constructor-injection boilerplate.
Banner comments (# ---- MicGate ----, etc.) separate them so the file
reads top-to-bottom like the architecture diagram.

╭─────────────────────────────── Pipeline order ──────────────────────────────╮
│  transport.input → VAD → [MicGate] → MicActivityProbe → AssemblyAI STT →    │
│  TranscriptForwarder → StreamingEvaluator → LatencyProbe → IntentRouter →   │
│  user_aggregator → Groq LLM → ElevenLabs TTS → transport.output →           │
│  assistant_aggregator                                                       │
╰─────────────────────────────────────────────────────────────────────────────╯

Custom processors (search the file for these banner comments to jump to them):
  · MicGate                     echo killer, gated by env (off for headphones)
  · MicActivityProbe            logs mic frames + feeds prosody tracker
  · TranscriptForwarder         re-emits transcripts as OutputTransportMessageFrame
  · StreamingEvaluator          interim-transcript pre-grader for quiz mode
  · LatencyProbe                stamps timestamps; writes per-turn JSONL
  · IntentRouter                deterministic Python FSM transitions from keywords

Side effects per turn:
  · JSONL row written to `logs/turn_latency.jsonl`
  · METRICS rolling window updated
  · WebSocket `state` event emitted (mode / quiz / engagement)
  · Mutations applied to SessionMemory + SQLite via tool dispatch
"""

from __future__ import annotations

import os
import time
from typing import Any

from .agent.orchestrator import ModeFSM
from .agent.prompts import greeting_for_returning_user, system_prompt_for
from .agent.prosody import ProsodyTracker
from .agent.tools import ToolRunner
from .memory.persistent import get_memory
from .memory.session import SessionMemory
from .observability.logger import TurnLog
from .observability.metrics import METRICS
from loguru import logger


class LanguageTutorBot:
    """Holds session state + a Pipecat pipeline runner."""

    def __init__(
        self,
        user_id: str | None = None,
        user_name: str | None = None,
        native_lang: str = "en",
        target_lang: str = "es",
    ):
        self.user_id = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
        self.user_name = user_name or os.environ.get("DEFAULT_USER_NAME", "Learner")
        self.native_lang = native_lang
        self.target_lang = target_lang

        self.memory = get_memory()
        self.memory.upsert_user(self.user_id, self.user_name, native_lang, target_lang)

        self.session = SessionMemory(user_id=self.user_id)
        self.fsm = ModeFSM(self.session)
        self.tool_runner = ToolRunner(self.session, self.fsm, self.memory)

        self._task: Any = None
        self._current_turn: TurnLog | None = None
        self.prosody = ProsodyTracker()

    # -------------------------------------------------------------------------
    async def run(self, transport: Any) -> None:
        bot = self
        # Local imports keep pipecat optional at module import time (tests).
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams
        from pipecat.frames.frames import (
            BotStartedSpeakingFrame,
            BotStoppedSpeakingFrame,
            EndFrame,
            Frame,
            InputAudioRawFrame,
            InterimTranscriptionFrame,
            LLMTextFrame,
            OutputTransportMessageFrame,
            TextFrame,
            TranscriptionFrame,
            TTSSpeakFrame,
            UserStartedSpeakingFrame,
            UserStoppedSpeakingFrame,
        )
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineParams, PipelineTask
        from pipecat.processors.aggregators.llm_context import LLMContext
        from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
        from pipecat.processors.audio.vad_processor import VADProcessor
        from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
        from pipecat.services.assemblyai.stt import AssemblyAISTTService
        from pipecat.services.elevenlabs.tts import ElevenLabsHttpTTSService
        from pipecat.services.groq.llm import GroqLLMService
        from pipecat.services.groq.stt import GroqSTTService  # noqa: F401  (kept for fallback)
        from pipecat.transcriptions.language import Language

        # ---- VAD (Silero) — tuned to reject room noise ---------------------
        # confidence=0.75  → higher threshold; ignores low-energy chatter.
        # min_volume=0.75  → utterance must exceed this normalized loudness.
        # start_secs=0.25  → must sustain ≥250 ms before we declare "speech".
        # stop_secs=0.30   → wait 300 ms of silence before ending turn.
        # All four together filter typical AC-fan / keyboard / off-camera talk
        # while still catching deliberate barge-in.
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=16000,
            params=VADParams(
                confidence=float(os.environ.get("VAD_CONFIDENCE", "0.60")),
                min_volume=float(os.environ.get("VAD_MIN_VOLUME", "0.55")),
                start_secs=float(os.environ.get("VAD_START_SECS", "0.20")),
                stop_secs=float(os.environ.get("VAD_STOP_SECS", "0.30")),
            ),
        )
        vad = VADProcessor(vad_analyzer=vad_analyzer)
        logger.info(
            f"VAD: confidence={os.environ.get('VAD_CONFIDENCE', '0.60')} "
            f"min_volume={os.environ.get('VAD_MIN_VOLUME', '0.55')} "
            f"start={os.environ.get('VAD_START_SECS', '0.20')}s "
            f"stop={os.environ.get('VAD_STOP_SECS', '0.30')}s"
        )

        # ---- STT (AssemblyAI Universal-Streaming v3) ------------------------
        # ┌──────────────────────────────────────────────────────────────────┐
        # │ TRUE streaming STT (spec-compliant: "STT must be streaming").    │
        # │                                                                  │
        # │ AssemblyAI Universal-Streaming v3 supports en, es, fr, de, hi,   │
        # │ it, pt. We set language=Spanish since this is a Spanish tutor;   │
        # │ English replies still work but may show slight accent quirks.    │
        # │                                                                  │
        # │ TTFS (finalize) ~120-180 ms after end-of-speech.                 │
        # │                                                                  │
        # │ Fallback path (commented): Groq Whisper Large v3 Turbo. Batch,   │
        # │ ~250 ms inference, multilingual auto-detect. Restore by          │
        # │ commenting AssemblyAI block + uncommenting Groq block.           │
        # └──────────────────────────────────────────────────────────────────┘
        stt_lang_code = os.environ.get("ASSEMBLYAI_LANGUAGE", "es").strip().lower()
        stt_language = (
            Language.ES if stt_lang_code == "es"
            else Language.EN if stt_lang_code == "en"
            else Language.ES  # default: Spanish (tutor's target)
        )
        stt = AssemblyAISTTService(
            api_key=os.environ["ASSEMBLYAI_API_KEY"],
            sample_rate=16000,
            language=stt_language,
        )
        logger.info(
            f"STT: AssemblyAI Universal-Streaming v3 · language={stt_language.value}"
        )

        # # ---- Fallback: Groq Whisper Large v3 Turbo (batch, multilingual) -
        # stt = GroqSTTService(
        #     api_key=os.environ["GROQ_API_KEY"],
        #     model="whisper-large-v3-turbo",
        #     language=None,
        # )

        # # ---- Alternative: Deepgram Nova-2 (requires paid credit) --------
        # from pipecat.services.deepgram.stt import DeepgramSTTService
        # stt = DeepgramSTTService(
        #     api_key=os.environ["DEEPGRAM_API_KEY"],
        #     model="nova-2-general",
        #     live_options={"language": "multi", "interim_results": True},
        # )

        # ---- LLM (Groq) -----------------------------------------------------
        # LLM produces prose only — IntentRouter (Python) handles mode
        # transitions and tool calls. This single path eliminates the
        # double-firing race that occurred when both IntentRouter AND
        # LLM tool-calls fired for the same user turn, and lets us cap
        # output at 60 tokens for fast, conversational replies.
        from pipecat.services.groq.llm import GroqLLMSettings
        llm = GroqLLMService(
            api_key=os.environ["GROQ_API_KEY"],
            settings=GroqLLMSettings(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                max_completion_tokens=80,
                temperature=0.7,
            ),
        )

        # ---- TTS (hybrid: ElevenLabs OR Deepgram Aura) ----------------------
        # ┌──────────────────────────────────────────────────────────────────┐
        # │ TO SWITCH PROVIDERS, change `TTS_PROVIDER` in backend/.env:      │
        # │   TTS_PROVIDER=elevenlabs   → best voice (10k chars/mo free)     │
        # │   TTS_PROVIDER=deepgram     → cheaper at scale, needs DG credit  │
        # │                                                                  │
        # │ ElevenLabs voice IDs (override via ELEVENLABS_VOICE_ID):         │
        # │   EXAVITQu4vr4xnSDxMaL  Sarah  (multilingual, default)           │
        # │   Nh2zY9kknu6z4pZy6FhD  Spanish-native female                    │
        # │   More: https://elevenlabs.io/app/voice-library                  │
        # │                                                                  │
        # │ Deepgram Aura voice IDs (override via DEEPGRAM_TTS_VOICE):       │
        # │   aura-2-celeste-es   Spanish female (Aura 2)                    │
        # │   aura-2-sirio-es     Spanish male                               │
        # │   aura-asteria-en     English female                             │
        # └──────────────────────────────────────────────────────────────────┘
        # HARDCODED TTS PROVIDER OVERRIDE (Change this directly in code for instant push-to-deploy!)
        # Set to "elevenlabs" or "deepgram"
        TTS_PROVIDER_OVERRIDE = "deepgram"

        tts_provider = (TTS_PROVIDER_OVERRIDE or os.environ.get("TTS_PROVIDER", "elevenlabs")).lower()

        if tts_provider == "elevenlabs":
            import aiohttp
            session = aiohttp.ClientSession()
            tts = ElevenLabsHttpTTSService(
                api_key=os.environ["ELEVENLABS_API_KEY"],
                aiohttp_session=session,
                voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
                model=os.environ.get("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5"),
            )
            logger.info(f"TTS: ElevenLabs HTTP · voice={os.environ.get('ELEVENLABS_VOICE_ID', 'default')}")

        elif tts_provider == "deepgram":
            from pipecat.services.deepgram.tts import DeepgramTTSService
            tts = DeepgramTTSService(
                api_key=os.environ["DEEPGRAM_API_KEY"],
                voice=os.environ.get("DEEPGRAM_TTS_VOICE", "aura-2-celeste-es"),
            )
            logger.info(f"TTS: Deepgram Aura · voice={os.environ.get('DEEPGRAM_TTS_VOICE', 'aura-2-celeste-es')}")

        else:
            raise ValueError(
                f"Unknown TTS_PROVIDER={tts_provider!r}. Use 'elevenlabs' or 'deepgram'."
            )

        # ---- LLM context + aggregators --------------------------------------
        weak = self.memory.weak_areas(self.user_id)
        due = self.memory.due_vocab(self.user_id)
        greeting = greeting_for_returning_user(self.user_name, weak, due)
        system = system_prompt_for(
            self.session.mode,
            frustrated=False,
            context_summary=self.session.context_summary(),
        )

        # IMPORTANT: do NOT pre-fill assistant message with the greeting.
        # The greeting will be spoken directly via TTSSpeakFrame; the LLM
        # only sees a system note recording that the bot greeted, so the
        # next LLM run treats the user as the speaker.
        context = LLMContext(
            messages=[
                {"role": "system", "content": system},
                {"role": "system", "content": f"(You greeted: '{greeting}'. WAIT for the learner. Reply in ≤25 words.)"},
            ],
            # No tools — IntentRouter (Python) routes mode transitions deterministically.
        )
        user_aggregator, assistant_aggregator = LLMContextAggregatorPair(context)
        self._llm_context = context  # used by tool handlers to refresh system prompt

        # ---- StreamingEvaluator (bonus: grade-as-you-speak) ----------------
        # When in quiz mode and an InterimTranscriptionFrame arrives that
        # already substantially matches the expected answer, we mark a
        # "pre-verdict" so the bot's feedback turn can start preparing
        # immediately on final. Pure UX optimization: still confirms on the
        # final transcript before committing the score.
        class StreamingEvaluator(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if (
                    isinstance(frame, InterimTranscriptionFrame)
                    and direction == FrameDirection.DOWNSTREAM
                    and bot.session.mode == "quiz"
                    and bot.session.quiz_index < bot.session.quiz_total
                ):
                    text = (frame.text or "").lower()
                    q = bot.session.quiz_questions[bot.session.quiz_index]
                    expected = (q.get("expected_es") or "").lower()
                    # Cheap substring/keyword check on interim transcript.
                    # If interim already looks correct, log it — final still grades.
                    if expected and (expected in text or text in expected):
                        logger.info(f"⚡ streaming-eval: interim looks correct early "
                                    f"({text[:50]!r} ~ expected {expected[:50]!r})")
                await self.push_frame(frame, direction)

        streaming_evaluator = StreamingEvaluator()

        # ---- TranscriptForwarder (guarantees UI sees transcripts) ----------
        # Sits right after STT. Re-emits each (interim) TranscriptionFrame as
        # an OutputTransportMessageFrame so the client always receives it,
        # independently of how aggregators downstream handle the original.
        class TranscriptForwarder(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                    msg = {
                        "type": "transcript",
                        "role": "user",
                        "interim": False,
                        "text": frame.text,
                        "language": getattr(frame, "language", None),
                    }
                    await self.push_frame(OutputTransportMessageFrame(message=msg), FrameDirection.DOWNSTREAM)
                elif isinstance(frame, InterimTranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                    msg = {
                        "type": "transcript",
                        "role": "user",
                        "interim": True,
                        "text": frame.text,
                        "language": getattr(frame, "language", None),
                    }
                    await self.push_frame(OutputTransportMessageFrame(message=msg), FrameDirection.DOWNSTREAM)
                await self.push_frame(frame, direction)

        transcript_forwarder = TranscriptForwarder()

        # ---- EventForwarder (converts pipeline frames → OutputTransportMessageFrame) ----
        # Pipecat 1.3.x only sends OutputTransportMessageFrame, OutputAudioRawFrame,
        # and InterruptionFrame through the serializer to the client. All other frames
        # (BotStartedSpeaking, LLMTextFrame, etc.) are silently dropped at the transport.
        # This processor wraps them so the client receives every event it needs.
        class EventForwarder(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                msg: dict | None = None
                # Bot speaking frames are pushed UPSTREAM by transport.output() —
                # must intercept regardless of direction.
                if isinstance(frame, BotStartedSpeakingFrame):
                    msg = {"type": "bot_speaking", "speaking": True}
                elif isinstance(frame, BotStoppedSpeakingFrame):
                    msg = {"type": "bot_speaking", "speaking": False}
                elif direction == FrameDirection.DOWNSTREAM:
                    if isinstance(frame, UserStartedSpeakingFrame):
                        msg = {"type": "user_speaking", "speaking": True}
                    elif isinstance(frame, UserStoppedSpeakingFrame):
                        msg = {"type": "user_speaking", "speaking": False}
                    elif isinstance(frame, LLMTextFrame) and frame.text:
                        msg = {"type": "transcript", "role": "assistant", "interim": True, "text": frame.text}
                if msg:
                    await self.push_frame(OutputTransportMessageFrame(message=msg), FrameDirection.DOWNSTREAM)
                await self.push_frame(frame, direction)

        event_forwarder = EventForwarder()

        # ---- IntentRouter (deterministic FSM transitions) ------------------
        # Listens to user transcripts and triggers mode transitions / tool
        # calls in Python — no LLM function calling required. Cleaner than
        # the previous tools-schema dance and much more reliable.
        from .curriculum.loader import CURRICULUM as _CURRICULUM

        class IntentRouter(FrameProcessor):
            INTENT_TEACH = ("teach", "lesson", "learn", "start lesson")
            INTENT_QUIZ = ("quiz", "test me", "test my", "check my")
            INTENT_CONVO = ("roleplay", "role play", "conversation", "let's chat",
                            "let's practice", "practice conversation", "speak with me")
            INTENT_DOUBT = ("wait", "doubt", "why is", "i have a question",
                            "what does", "what's the difference")
            INTENT_RESUME = ("continue", "go on", "back to", "resume", "let's continue")
            INTENT_STOP = ("stop", "end session", "goodbye", "thanks bye", "that's all")
            # Destructive — require 2-step voice confirmation.
            INTENT_RESET_ALL = ("reset my progress", "reset everything",
                                "forget my progress", "start fresh", "wipe my progress",
                                "clear all my progress", "reset all")
            INTENT_RESET_WEAK = ("reset weak spots", "clear weak spots",
                                 "forget my mistakes", "reset my mistakes")
            INTENT_CONFIRM_YES = ("yes confirm", "yes do it", "confirm", "yes please",
                                  "go ahead", "yes reset")
            INTENT_CONFIRM_NO = ("no", "cancel", "stop", "never mind", "don't")

            _emit_state_pending = False
            LESSON_STEPS = ["intro", "explain", "example", "practice", "check", "done"]

            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                self._emit_state_pending = False
                if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                    self._route(frame.text or "")
                if self._emit_state_pending:
                    eng = bot.prosody.reading()
                    state_msg = {
                        "type": "state",
                        "mode": bot.session.mode,
                        "persona": bot.session.persona,
                        "lesson_id": bot.session.current_lesson_id,
                        "lesson_step": bot.session.lesson_step,
                        "quiz_index": bot.session.quiz_index,
                        "quiz_total": bot.session.quiz_total,
                        "quiz_score": bot.session.quiz_score,
                        "engagement_score": eng.score,
                        "engagement_label": eng.label,
                        "pace_wpm": eng.pace_wpm,
                    }
                    await self.push_frame(
                        OutputTransportMessageFrame(message=state_msg),
                        FrameDirection.DOWNSTREAM,
                    )
                await self.push_frame(frame, direction)

            def _route(self, text: str) -> None:
                t = text.lower().strip()
                if not t:
                    return

                # ── Voice reset (2-step confirmation) ──────────────────
                # If a destructive action is pending, this turn either
                # confirms or cancels.
                if bot.session.pending_confirmation:
                    if any(k in t for k in self.INTENT_CONFIRM_YES):
                        action = bot.session.pending_confirmation
                        bot.session.pending_confirmation = None
                        if action == "reset_all":
                            res = bot.memory.reset_user_progress(bot.session.user_id)
                            self._announce(
                                f"Reset done. Cleared {res['progress']} lessons, "
                                f"{res['vocab_mastery']} vocab entries, {res['mistakes']} mistakes. "
                                f"Confirm in one short warm sentence and ask what they want next."
                            )
                            logger.info(f"🗑  voice reset_all → {res}")
                        elif action == "reset_weak_spots":
                            res = bot.memory.reset_weak_spots(bot.session.user_id)
                            self._announce(
                                f"Weak spots cleared: {res['vocab_mastery_reset']} vocab rows reset, "
                                f"{res['mistakes_cleared']} mistakes removed. "
                                f"Confirm in one short sentence; offer a fresh practice."
                            )
                            logger.info(f"🗑  voice reset_weak → {res}")
                        return
                    if any(k in t for k in self.INTENT_CONFIRM_NO):
                        bot.session.pending_confirmation = None
                        self._announce("Reset cancelled. One short reassurance, then ask what they'd like to do.")
                        return
                    # Anything else while waiting for confirmation: re-ask.
                    self._announce(
                        f"Still waiting for the learner to confirm "
                        f"({bot.session.pending_confirmation}). "
                        f"Ask 'say yes to confirm or no to cancel'."
                    )
                    return

                # ── New reset request → ask for confirmation ───────────
                if any(k in t for k in self.INTENT_RESET_ALL):
                    bot.session.pending_confirmation = "reset_all"
                    self._announce(
                        "Learner asked to reset ALL progress. Confirm gravity in one sentence "
                        '(lessons + vocab + mistakes will be wiped), then ask: '
                        '"say yes to confirm, or no to cancel."'
                    )
                    logger.info("⚠  reset_all requested — awaiting confirmation")
                    return

                if any(k in t for k in self.INTENT_RESET_WEAK):
                    bot.session.pending_confirmation = "reset_weak_spots"
                    self._announce(
                        "Learner asked to reset weak spots. Confirm: this will clear lapses + "
                        'recent mistakes but keep mastery. Ask: "say yes to confirm, or no to cancel."'
                    )
                    logger.info("⚠  reset_weak_spots requested — awaiting confirmation")
                    return

                if any(k in t for k in self.INTENT_DOUBT) and bot.session.mode != "doubt":
                    bot.fsm.switch_to("doubt")
                    self._announce("Doubt mode. Answer in English, briefly, then ask if they want to continue.")
                    return

                if any(k in t for k in self.INTENT_RESUME) and bot.session.mode == "doubt":
                    bot.fsm.exit_doubt()
                    self._announce(f"Resuming {bot.session.mode} at step {bot.session.lesson_step}.")
                    return

                if any(k in t for k in self.INTENT_TEACH):
                    lesson = _CURRICULUM.by_topic(t) or _CURRICULUM.all()[0]
                    bot.fsm.switch_to("teaching")
                    bot.session.current_lesson_id = lesson.id
                    bot.session.lesson_step = "intro"
                    # Seed FSRS with the lesson's vocab so Due-for-Review fills.
                    for v in lesson.vocabulary:
                        bot.session.introduce_vocab(v.es)
                        bot.memory.record_vocab_attempt(
                            bot.session.user_id, v.es, "es", success=True
                        )
                    # Mark lesson in progress (partial credit until quiz).
                    bot.memory.record_lesson_score(
                        bot.session.user_id, lesson.id, 0.3
                    )
                    self._announce(self._teaching_step_note(lesson, "intro"))
                    logger.info(f"🎓 teaching → {lesson.id} (seeded {len(lesson.vocabulary)} vocab)")
                    return

                if any(k in t for k in self.INTENT_QUIZ):
                    lesson = (_CURRICULUM.by_topic(t)
                              or (_CURRICULUM.get(bot.session.current_lesson_id)
                                  if bot.session.current_lesson_id else None)
                              or _CURRICULUM.all()[0])
                    bot.fsm.switch_to("quiz")
                    bot.session.quiz_topic = lesson.id
                    # Tight quiz: lesson checks first, then 3 vocab. 5 max.
                    qs = []
                    for c in lesson.checks:
                        qs.append({"prompt_en": c.prompt_en,
                                   "expected_es": c.expected_es,
                                   "variants": c.accept_variants})
                    for v in lesson.vocabulary[:3]:
                        qs.append({"prompt_en": f"How do you say '{v.en}' in Spanish?",
                                   "expected_es": v.es, "variants": []})
                    qs = qs[:5]
                    bot.session.quiz_questions = qs
                    bot.session.quiz_index = 0
                    bot.session.quiz_total = len(qs)
                    bot.session.quiz_score = 0
                    first = qs[0]
                    self._announce(
                        f"Quiz on {lesson.title} ({len(qs)} questions). Ask: \"{first['prompt_en']}\""
                    )
                    logger.info(f"📝 quiz → {lesson.id} n={len(qs)}")
                    return

                if any(k in t for k in self.INTENT_CONVO):
                    bot.fsm.switch_to("conversation")
                    self._announce("Conversation roleplay. Pick a simple scene from learner's request. Speak Spanish; only English to unstick.")
                    logger.info("💬 conversation")
                    return

                if any(k in t for k in self.INTENT_STOP):
                    self._announce("End-of-session: one-line warm summary.")
                    logger.info("👋 stop")
                    return

                # In quiz mode: grade deterministically (no LLM tokens used).
                if bot.session.mode == "quiz" and bot.session.quiz_index < bot.session.quiz_total:
                    self._grade_quiz_answer(text)
                    return

                # In teaching mode: any user reply = advance one step + inject next-step note.
                if bot.session.mode == "teaching" and bot.session.current_lesson_id:
                    lesson = _CURRICULUM.get(bot.session.current_lesson_id)
                    if lesson:
                        cur = bot.session.lesson_step
                        idx = self.LESSON_STEPS.index(cur) if cur in self.LESSON_STEPS else 0
                        if idx < len(self.LESSON_STEPS) - 1:
                            bot.session.lesson_step = self.LESSON_STEPS[idx + 1]
                        new_step = bot.session.lesson_step
                        self._announce(self._teaching_step_note(lesson, new_step))
                        # Lesson completed via teaching path → record partial-mastery score.
                        if new_step == "done":
                            bot.memory.record_lesson_score(
                                bot.session.user_id, lesson.id, 0.6
                            )
                            logger.info(f"✅ lesson {lesson.id} taught → score=0.6 (quiz can raise to 1.0)")

            def _teaching_step_note(self, lesson, step: str) -> str:
                """Tiny per-step prompt. ~50-100 tokens each."""
                if step == "intro":
                    return (
                        f"Lesson: {lesson.title}. Objective: {lesson.objective}. "
                        "Greet the topic in one sentence, then ask if learner is ready."
                    )
                if step == "explain":
                    note = lesson.grammar_notes[0] if lesson.grammar_notes else lesson.objective
                    return f"Explain step. Share this rule in plain English: {note}"
                if step == "example":
                    ex = lesson.examples[0] if lesson.examples else None
                    if ex:
                        return f"Example step. Say in Spanish: \"{ex['es']}\". Then translate: \"{ex['en']}\"."
                    return "Example step. Give one short example."
                if step == "practice":
                    prompt = lesson.practice_prompts[0] if lesson.practice_prompts else "Try a phrase."
                    return f"Practice step. Ask learner to: {prompt} Wait for their reply."
                if step == "check":
                    c = lesson.checks[0]
                    return f"Check step. Ask: \"{c.prompt_en}\" Expected: \"{c.expected_es}\". Listen, grade, give one-line feedback."
                return "Lesson complete. Say a warm one-line wrap-up and ask if they want a quiz."

            def _grade_quiz_answer(self, learner_text: str) -> None:
                """Deterministic semantic grading; updates FSRS-lite + lesson progress;
                injects feedback hint into LLM context. Now includes a
                pronunciation-aware tip when the learner got it wrong."""
                from .agent.grader import grade_deterministic
                from .agent.pronunciation import detect_tricky
                q = bot.session.quiz_questions[bot.session.quiz_index]
                expected = q.get("expected_es", "")
                variants = q.get("variants", [])
                result = grade_deterministic(expected, learner_text, variants)
                if result is None:
                    correct = False
                    note = f"Borderline. Expected \"{expected}\", learner said \"{learner_text}\". You decide."
                else:
                    correct = result.correct
                    if correct:
                        bot.session.quiz_score += 1
                        note = f"Correct: \"{expected}\". One specific compliment."
                    else:
                        # Add pronunciation hint for the FIRST tricky word in expected.
                        pron_hint = ""
                        for word in expected.lower().split():
                            hits = detect_tricky(word.strip(".,?!¿¡"))
                            if hits:
                                pron_hint = f" Tip: {hits[0]}"
                                break
                        note = f"Wrong. Expected \"{expected}\", learner said \"{learner_text}\".{pron_hint} One specific correction."

                # ── FSRS-lite update so weak_spots / due_vocab panels reflect reality.
                bot.memory.record_vocab_attempt(
                    bot.session.user_id, expected, "es", success=correct
                )
                if not correct:
                    bot.memory.log_mistake(
                        bot.session.user_id, "quiz",
                        expected=expected, got=learner_text,
                        lesson_id=bot.session.quiz_topic,
                    )

                # ── Lesson progress update on EVERY answer (not just last).
                if bot.session.quiz_total > 0:
                    partial_score = bot.session.quiz_score / bot.session.quiz_total
                    bot.memory.record_lesson_score(
                        bot.session.user_id,
                        bot.session.quiz_topic or "unknown",
                        partial_score,
                    )

                bot.session.quiz_index += 1
                if bot.session.quiz_index >= bot.session.quiz_total:
                    score = bot.session.quiz_score
                    total = bot.session.quiz_total
                    bot.fsm.switch_to("idle")
                    self._announce(f"{note} Then summary: \"You got {score}/{total}.\" Ask what next.")
                else:
                    next_q = bot.session.quiz_questions[bot.session.quiz_index]
                    next_prompt = next_q.get("prompt_en") or next_q.get("prompt_es") or "Try another."
                    self._announce(f"{note} Then ask: \"{next_prompt}\".")
                logger.info(f"📊 quiz {bot.session.quiz_index}/{bot.session.quiz_total} score={bot.session.quiz_score} verdict={correct}")

            def _announce(self, note: str) -> None:
                """Inject a system-role hint. Keep context small."""
                # Append a tiny prosody nudge if engagement is low or high.
                reading = bot.prosody.reading()
                tone = ""
                if reading.is_low():
                    tone = " (Engagement low — slow down, encourage, simpler phrasing.)"
                elif reading.is_high():
                    tone = " (Engagement high — feel free to add complexity.)"

                msgs = bot._llm_context.messages
                msgs.append({"role": "system", "content": note + tone})
                # Hard cap: system prompt + last 6 messages = max 7.
                if len(msgs) > 7:
                    bot._llm_context.messages[:] = [msgs[0]] + msgs[-6:]
                self._emit_state_pending = True

        intent_router = IntentRouter()

        # MicGate is OPTIONAL — only useful when user is on speakers (echo).
        # Headphone users should leave it disabled (default) so barge-in
        # works without any volume threshold.
        MIC_GATE_ENABLED = os.environ.get("MIC_GATE_ENABLED", "false").lower() == "true"
        logger.info(f"MIC_GATE_ENABLED={MIC_GATE_ENABLED} "
                    f"({'speakers — echo protection on' if MIC_GATE_ENABLED else 'headphones — barge-in unrestricted'})")

        # ---- MicGate processor (echo / feedback-loop killer) ---------------
        # When the user has the bot on speakers (not headphones), the bot's
        # own TTS audio bleeds into the microphone. Without this gate, the
        # STT transcribes the bot speaking, the LLM responds to itself, and
        # the session degenerates into a feedback loop.
        #
        # Strategy:
        #   1. Listen for BotStartedSpeakingFrame / BotStoppedSpeakingFrame
        #      (Pipecat system frames; propagate in both directions).
        #   2. While bot is speaking, swallow InputAudioRawFrame *upstream*
        #      so they never reach VAD/STT.
        #   3. After BotStoppedSpeakingFrame, keep gating for `tail_ms` extra
        #      to flush any speaker decay still echoing into the mic.
        bot = self

        class MicGate(FrameProcessor):
            """Drops mic audio while the bot is speaking — with a loudness
            override so the user can still barge in if they speak loudly.

            - While bot speaks: only pass frames whose RMS > BARGE_IN_RMS
              (= user shouting over the bot). Bot's own echo through
              speakers is usually well below this.
            - Tail window after bot stops: keep gating for TAIL_SECS to
              flush residual echo.
            """

            import numpy as _np  # local alias to avoid module-level import

            TAIL_SECS = 0.20  # short tail = snappy post-bot listening
            # Int16 RMS threshold for letting audio through during bot speech.
            # Lowered to 2000 so headphone-user speech (often softer) reliably
            # bypasses the gate. Echo from speakers typically peaks ~300-800
            # so 2000 still blocks speaker feedback.
            BARGE_IN_RMS = 2000

            def __init__(self):
                super().__init__()
                self._bot_speaking = False
                self._last_bot_stop = 0.0
                self._dropped = 0
                self._passed = 0
                self._bargein = 0
                self._last_log = 0.0
                self._last_bargein = 0.0  # debounce — only one barge-in per 500 ms

            @staticmethod
            def _rms(audio: bytes) -> float:
                if not audio:
                    return 0.0
                arr = MicGate._np.frombuffer(audio, dtype=MicGate._np.int16)
                if arr.size == 0:
                    return 0.0
                return float(MicGate._np.sqrt(MicGate._np.mean(arr.astype(MicGate._np.float32) ** 2)))

            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, BotStartedSpeakingFrame):
                    self._bot_speaking = True
                    logger.debug("MicGate: bot speaking → mic gated (loudness override active)")
                elif isinstance(frame, BotStoppedSpeakingFrame):
                    self._bot_speaking = False
                    self._last_bot_stop = time.time()
                    logger.debug(f"MicGate: bot stopped → tail {self.TAIL_SECS}s")

                if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                    now = time.time()
                    in_tail = (now - self._last_bot_stop) < self.TAIL_SECS
                    gated = self._bot_speaking or in_tail
                    if gated:
                        rms = self._rms(frame.audio)
                        if rms < self.BARGE_IN_RMS:
                            self._dropped += 1
                            if now - self._last_log > 2.0:
                                logger.debug(
                                    f"MicGate: dropped={self._dropped} "
                                    f"passed={self._passed} bargein={self._bargein}"
                                )
                                self._last_log = now
                            return  # swallow — likely speaker echo
                        else:
                            # Debounce — only one barge-in announcement per 500 ms.
                            if (now - self._last_bargein) < 0.5:
                                self._dropped += 1
                                return  # still gate, just don't log/announce
                            self._last_bargein = now
                            self._bargein += 1
                            logger.info(f"💥 barge-in: RMS={rms:.0f}")
                    self._passed += 1

                await self.push_frame(frame, direction)

        mic_gate = MicGate()

        # ---- Mic activity probe (diagnostic) -------------------------------
        # Logs every Nth audio frame so we can verify mic actually reaches
        # the backend at all. Useful during initial debug.
        class MicActivityProbe(FrameProcessor):
            EVERY = 50  # ~ every 2 seconds of audio at 40ms chunks

            def __init__(self):
                super().__init__()
                self._n = 0

            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, InputAudioRawFrame) and direction == FrameDirection.DOWNSTREAM:
                    self._n += 1
                    # Feed prosody tracker — only when audio survived MicGate
                    # (i.e., real user audio, not bot echo).
                    bot.prosody.feed_audio(frame.audio)
                    if self._n == 1 or self._n % self.EVERY == 0:
                        logger.info(
                            f"🎙  mic frame #{self._n} | "
                            f"sr={frame.sample_rate} bytes={len(frame.audio)}"
                        )
                if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
                    lang = getattr(frame, "language", None)
                    logger.info(f"📝 STT final: {frame.text!r} (lang={lang})")
                if isinstance(frame, UserStartedSpeakingFrame):
                    logger.info("🗣  user started speaking")
                if isinstance(frame, UserStoppedSpeakingFrame):
                    logger.info("🤐 user stopped speaking")
                if isinstance(frame, BotStartedSpeakingFrame):
                    logger.info("🤖 bot started speaking")
                if isinstance(frame, BotStoppedSpeakingFrame):
                    logger.info("🤐 bot stopped speaking")
                await self.push_frame(frame, direction)

        mic_probe = MicActivityProbe()

        # ---- Latency probe processor ---------------------------------------
        # Measures the spec's headline metric: end-of-user-speech → first
        # audible bot token. Marks the bot-audio start at BotStartedSpeakingFrame
        # (NOT BotStopped which is end-of-bot-speech).
        class LatencyProbe(FrameProcessor):
            async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
                await super().process_frame(frame, direction)
                if isinstance(frame, UserStartedSpeakingFrame):
                    bot._current_turn = TurnLog(mode=bot.session.mode, persona=bot.session.persona)
                elif isinstance(frame, UserStoppedSpeakingFrame):
                    if bot._current_turn:
                        bot._current_turn.mark("user_speech_end_ms")
                elif isinstance(frame, TranscriptionFrame):
                    if bot._current_turn:
                        # AssemblyAI sometimes finalises before VAD endpoint —
                        # don't overwrite a later stt_final_ms if it already set.
                        if bot._current_turn.stt_final_ms is None:
                            bot._current_turn.mark("stt_final_ms")
                        bot._current_turn.stt_text = frame.text
                        bot._current_turn.language_detected = getattr(frame, "language", None)
                        bot.session.add_turn("user", frame.text, getattr(frame, "language", None))
                        # Feed prosody tracker (text + duration).
                        t = bot._current_turn
                        if t.t_start_ms and t.user_speech_end_ms:
                            dur = (t.user_speech_end_ms - t.t_start_ms) / 1000.0
                            bot.prosody.mark_turn(
                                text=frame.text or "",
                                duration_s=dur,
                                ended_at=t.user_speech_end_ms / 1000.0,
                            )
                elif isinstance(frame, (LLMTextFrame, TextFrame)):
                    if direction == FrameDirection.DOWNSTREAM and bot._current_turn:
                        if bot._current_turn.llm_first_token_ms is None:
                            bot._current_turn.mark("llm_first_token_ms")
                        bot._current_turn.llm_text += getattr(frame, "text", "") or ""
                elif isinstance(frame, BotStartedSpeakingFrame):
                    # FIRST audible bot audio — this is the metric the spec cares about.
                    if bot._current_turn and bot._current_turn.tts_first_audio_ms is None:
                        bot._current_turn.mark("tts_first_audio_ms")
                        t = bot._current_turn
                        # End-of-user-speech → first audible bot token (spec metric).
                        ref_end = t.user_speech_end_ms or t.stt_final_ms
                        e2e_ms = _delta(ref_end, t.tts_first_audio_ms) or 0.0
                        stt_ms = _delta(t.user_speech_end_ms, t.stt_final_ms)
                        llm_ms = _delta(t.stt_final_ms, t.llm_first_token_ms)
                        tts_ms = _delta(t.llm_first_token_ms, t.tts_first_audio_ms)
                        METRICS.record_turn(
                            stt_ms=stt_ms,
                            llm_ttft_ms=llm_ms,
                            tts_first_ms=tts_ms,
                            total_ms=e2e_ms,  # the headline metric
                        )
                        logger.info(
                            f"⏱  TURN STT={_f(stt_ms)} LLM={_f(llm_ms)} TTS={_f(tts_ms)} "
                            f"E2E(speech→audio)={e2e_ms:.0f}ms  ← spec metric"
                        )
                elif isinstance(frame, BotStoppedSpeakingFrame):
                    # End of bot speech — commit the assistant turn.
                    if bot._current_turn:
                        bot._current_turn.write()
                        bot.session.add_turn("assistant", bot._current_turn.llm_text, None)
                        bot._current_turn = None
                await self.push_frame(frame, direction)

        latency_probe = LatencyProbe()

        # ---- Pipeline -------------------------------------------------------
        # Order — critical for barge-in:
        #   transport.input → VAD → [MicGate?] → mic_probe → STT →
        #   transcript_forwarder → latency_probe → intent_router →
        #   user_aggregator → LLM → TTS → transport.output → assistant_aggregator
        #
        # VAD runs FIRST so it sees ALL audio (incl. during bot speech). When
        # the user starts talking, VAD emits UserStartedSpeakingFrame, which
        # Pipecat's allow_interruptions=True uses to cancel in-flight TTS.
        # That's the barge-in path — must not be blocked.
        #
        # MicGate (if enabled) runs AFTER VAD so it only filters audio going
        # to STT (preventing bot's own echo from being transcribed) without
        # blocking the VAD interruption signal.
        stages = [
            transport.input(),
            vad,
        ]
        if MIC_GATE_ENABLED:
            stages.append(mic_gate)
        stages.extend([
            mic_probe,
            stt,
            transcript_forwarder,
            streaming_evaluator,
            latency_probe,
            intent_router,
            user_aggregator,
            llm,
            tts,
            event_forwarder,
            transport.output(),
            assistant_aggregator,
        ])
        pipeline = Pipeline(stages)

        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                enable_metrics=True,
                audio_in_sample_rate=16000,
                audio_out_sample_rate=24000,
            ),
        )

        @transport.event_handler("on_client_connected")
        async def _on_connect(_transport, _client):
            logger.info("Client connected; speaking greeting directly via TTS")
            # Speak the greeting directly. No LLM round-trip = no
            # hallucinated continuation of an imaginary conversation.
            await task.queue_frames([TTSSpeakFrame(greeting)])

        @transport.event_handler("on_client_disconnected")
        async def _on_disconnect(_transport, _client):
            logger.info("Client disconnected")
            await task.queue_frames([EndFrame()])

        self._task = task
        await PipelineRunner().run(task)

    # -------------------------------------------------------------------------
    def _make_tool_handler(self, tool_name: str):
        async def handler(params):
            # Pipecat 1.x calls handlers with a FunctionCallParams object.
            # Fields: function_name, tool_call_id, arguments, llm, context,
            # and `result_callback` (async).
            args = getattr(params, "arguments", None) or {}
            if self._current_turn:
                self._current_turn.tools_called.append(tool_name)
            t0 = time.time() * 1000
            result = await self.tool_runner.dispatch(tool_name, args)

            # Refresh system prompt if mode changed.
            # (Only the four LLM-registered tools can land here; "switch_mode"
            # was retired when we collapsed to the four mode-transition tools.)
            if tool_name in {
                "enter_doubt_mode", "exit_doubt_mode",
                "start_lesson", "start_quiz",
            }:
                new_system = system_prompt_for(
                    self.session.mode,
                    frustrated=self.session.is_frustrated(),
                    context_summary=self.session.context_summary(),
                )
                msgs = self._llm_context.messages
                if msgs:
                    first = msgs[0]
                    if isinstance(first, dict) and first.get("role") == "system":
                        first["content"] = new_system  # type: ignore
                    elif hasattr(first, "message") and isinstance(getattr(first, "message", None), dict) and getattr(first, "message").get("role") == "system":  # noqa: B009 # type: ignore
                        getattr(first, "message")["content"] = new_system  # noqa: B009 # type: ignore
                    else:
                        msgs.insert(0, {"role": "system", "content": new_system})  # type: ignore
                else:
                    msgs.insert(0, {"role": "system", "content": new_system})  # type: ignore

            dt = time.time() * 1000 - t0
            keys = list(result.keys()) if isinstance(result, dict) else result
            logger.info(f"tool {tool_name} → {dt:.0f}ms — keys={keys}")
            await params.result_callback(result)
        return handler


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return max(0.0, b - a)


def _f(x: float | None) -> str:
    return f"{x:.0f}ms" if x is not None else "—"
