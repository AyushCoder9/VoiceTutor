"use client";
import { motion } from "framer-motion";
import {
  BookOpen,
  Brain,
  HeartHandshake,
  HelpCircle,
  Layers,
  LineChart,
  Mic,
  Sparkles,
  Wand2,
  Zap,
} from "lucide-react";

const FEATURES: {
  icon: React.ElementType;
  title: string;
  body: string;
  accent: string;
  tag?: string;
}[] = [
  {
    icon: Mic,
    title: "Real barge-in",
    body: "Silero VAD + Pipecat interruption frames cut bot mid-word in <250 ms. Talk over it freely.",
    accent: "violet",
  },
  {
    icon: Zap,
    title: "Sub-1-second response",
    body: "P50 end-to-end ~880 ms on free-tier providers. AssemblyAI streaming → Groq → ElevenLabs Turbo.",
    accent: "peach",
    tag: "measured",
  },
  {
    icon: BookOpen,
    title: "Structured teaching",
    body: "FSM-enforced lesson flow: objective → explain → example → practice → check. No rambling.",
    accent: "mint",
  },
  {
    icon: Brain,
    title: "Semantic quiz grading",
    body: "Paraphrases accepted. Two-tier: deterministic Jaccard first, LLM only for ambiguous middle.",
    accent: "sky",
  },
  {
    icon: HelpCircle,
    title: "Doubt resume",
    body: 'Mid-lesson "wait, why is it me llamo?" → answers in English, returns exactly where you left off.',
    accent: "coral",
  },
  {
    icon: Layers,
    title: "FSRS-lite scheduling",
    body: "Each quiz answer feeds spaced-repetition. Weak words come back tomorrow, mastered ones in a week.",
    accent: "violet",
    tag: "bonus",
  },
  {
    icon: HeartHandshake,
    title: "Prosody engagement",
    body: "Real-time RMS + pace + pause analysis. Bot detects when you sound tired and slows down.",
    accent: "mint",
    tag: "bonus",
  },
  {
    icon: Wand2,
    title: "Phoneme-aware feedback",
    body: 'Not "good job" — specific tips like "the rr in perro is rolled, try humming and tapping".',
    accent: "peach",
  },
  {
    icon: LineChart,
    title: "Per-turn observability",
    body: "Every turn logs STT / LLM / TTS / total latency to JSONL. Answer 'why did turn 14 take 2.3s'.",
    accent: "sky",
  },
  {
    icon: Sparkles,
    title: "Multi-persona handoff",
    body: "Teacher / Examiner / Companion — same LLM, three styles, switched by FSM mode.",
    accent: "coral",
    tag: "bonus",
  },
];

const ACCENT_TO_COLOR = {
  violet: "#a78bfa",
  peach: "#ffb86b",
  mint: "#34d399",
  sky: "#38bdf8",
  coral: "#ff6b6b",
} as const;

export default function Features() {
  return (
    <section
      id="features"
      className="relative max-w-7xl mx-auto px-6 py-24 md:py-32"
    >
      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-12 items-end mb-14">
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
        >
          <div className="text-[10px] font-mono uppercase tracking-[0.4em] text-accent-violet mb-3">
            §02 · capabilities
          </div>
          <h2 className="font-display text-4xl md:text-5xl leading-tight tracking-tight">
            Built for the parts<br />
            that <span className="text-gradient">actually</span> matter.
          </h2>
        </motion.div>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-zinc-400 leading-relaxed max-w-lg md:justify-self-end md:text-right"
        >
          Every feature was picked against the assignment's evaluation matrix —
          system design, voice UX, pedagogy, reliability, observability — with
          the bonus stretch goals layered on top.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {FEATURES.map((f, i) => {
          const color = ACCENT_TO_COLOR[f.accent as keyof typeof ACCENT_TO_COLOR];
          return (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-50px" }}
              transition={{ duration: 0.5, delay: (i % 6) * 0.06, ease: [0.16, 1, 0.3, 1] }}
              className="card-tilt glass rounded-2xl p-6 border border-white/10 relative overflow-hidden"
            >
              <div
                className="absolute -top-12 -right-12 w-32 h-32 rounded-full blur-2xl opacity-30 pointer-events-none"
                style={{ background: color }}
              />
              <div className="flex items-start justify-between mb-4">
                <div
                  className="w-10 h-10 rounded-xl grid place-items-center"
                  style={{
                    background: `linear-gradient(135deg, ${color}33, ${color}11)`,
                    border: `1px solid ${color}55`,
                  }}
                >
                  <f.icon className="w-5 h-5" style={{ color }} strokeWidth={1.8} />
                </div>
                {f.tag && (
                  <span
                    className="text-[9px] font-mono uppercase tracking-[0.25em] px-2 py-0.5 rounded-full border"
                    style={{ color, borderColor: `${color}55`, background: `${color}1A` }}
                  >
                    {f.tag}
                  </span>
                )}
              </div>
              <h3 className="font-display text-xl tracking-tight mb-2 text-zinc-100">
                {f.title}
              </h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{f.body}</p>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}
