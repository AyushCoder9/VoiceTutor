"use client";
import { motion } from "framer-motion";
import { ArrowDown, Headphones, Sparkles, Zap } from "lucide-react";

export default function Hero() {
  return (
    <section
      id="top"
      className="relative max-w-7xl mx-auto px-6 pt-32 pb-20 md:pt-40 md:pb-32"
    >
      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-12 items-center">
        {/* LEFT — copy */}
        <div>
          <motion.div
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            className="inline-flex items-center gap-2 mb-7 px-3 py-1.5 rounded-full glass border border-white/10"
          >
            <Sparkles className="w-3 h-3 text-accent-peach" />
            <span className="text-[11px] font-mono uppercase tracking-[0.3em] text-zinc-300">
              voice-first · hands-free · sub-1.5s latency
            </span>
          </motion.div>

          <h1 className="font-display text-[clamp(2.5rem,7vw,5.5rem)] leading-[0.95] tracking-tight">
            <span className="block word-rise" style={{ animationDelay: "0.05s" }}>
              Learn Spanish
            </span>
            <span
              className="block text-gradient word-rise"
              style={{ animationDelay: "0.20s" }}
            >
              by talking,
            </span>
            <span className="block word-rise" style={{ animationDelay: "0.35s" }}>
              not tapping.
            </span>
          </h1>

          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.55, duration: 0.6 }}
            className="mt-8 max-w-xl text-zinc-400 leading-relaxed text-[15px]"
          >
            A real-time conversational tutor. Put your phone down. Speak. The agent
            teaches lessons, runs quizzes, roleplays cafés in Madrid, and answers
            your doubts mid-sentence — all by voice.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7, duration: 0.6 }}
            className="mt-10 flex flex-wrap items-center gap-3"
          >
            <a
              href="#demo"
              className="btn-primary btn-magnetic px-6 py-3 rounded-full text-sm flex items-center gap-2"
            >
              Start talking
              <ArrowDown className="w-3.5 h-3.5" />
            </a>
            <a
              href="#features"
              className="btn-ghost btn-magnetic px-5 py-3 rounded-full text-sm flex items-center gap-2 font-medium"
            >
              See what it can do
            </a>
            <span className="hidden sm:flex items-center gap-1.5 ml-2 text-[11px] font-mono text-zinc-500">
              <Headphones className="w-3 h-3" />
              headphones recommended
            </span>
          </motion.div>

          {/* mini stats strip */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.95, duration: 0.6 }}
            className="mt-12 grid grid-cols-3 gap-4 max-w-md"
          >
            <Stat label="modes" value="4" hint="teach · quiz · convo · doubt" />
            <Stat label="lessons" value="6" hint="A1 → A2 curriculum" />
            <Stat label="P50 latency" value="<1s" hint="end-to-end measured" />
          </motion.div>
        </div>

        {/* RIGHT — preview orb */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          className="relative justify-self-center"
        >
          <PreviewOrb />
          {/* floating chips */}
          <FloatingChip className="absolute -top-2 -left-6 float-drift" icon={Zap}>
            Groq · 200 tok/s
          </FloatingChip>
          <FloatingChip
            className="absolute -bottom-3 -right-4 float-drift"
            style={{ animationDelay: "1.5s" }}
          >
            Pipecat 1.2
          </FloatingChip>
        </motion.div>
      </div>
    </section>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div>
      <div className="font-display text-3xl text-zinc-100 num-tick leading-none">
        {value}
      </div>
      <div className="mt-1.5 text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">
        {label}
      </div>
      <div className="mt-0.5 text-[10px] text-zinc-600">{hint}</div>
    </div>
  );
}

function FloatingChip({
  children,
  className = "",
  style,
  icon: Icon,
}: {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  icon?: React.ElementType;
}) {
  return (
    <div
      className={
        "glass px-3 py-1.5 rounded-full text-[10px] font-mono text-zinc-200 border border-white/10 shadow-xl flex items-center gap-1.5 " +
        className
      }
      style={style}
    >
      {Icon && <Icon className="w-3 h-3 text-accent-peach" />}
      {children}
    </div>
  );
}

function PreviewOrb() {
  return (
    <div
      className="relative w-[320px] h-[320px] rounded-full grid place-items-center"
      style={{
        background:
          "radial-gradient(circle at 30% 30%, rgba(167,139,250,0.45), transparent 55%), radial-gradient(circle at 70% 70%, rgba(255,107,107,0.25), transparent 65%), radial-gradient(circle at 50% 50%, #0a0c14, #06070d)",
        boxShadow:
          "inset 0 0 100px rgba(167,139,250,0.2), 0 40px 90px rgba(0,0,0,0.6), 0 0 80px rgba(167,139,250,0.18)",
      }}
    >
      {/* spinning conic ring */}
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
        className="absolute inset-4 rounded-full opacity-60"
        style={{
          background:
            "conic-gradient(from 0deg, rgba(167,139,250,0.5), transparent 25%, rgba(255,107,107,0.4) 50%, transparent 75%, rgba(167,139,250,0.5) 100%)",
          filter: "blur(12px)",
        }}
      />
      {/* outer pulse */}
      <span className="pulse-ring" />

      {/* inner core */}
      <div className="relative w-44 h-44 rounded-full bg-ink-900/80 backdrop-blur-md border border-white/10 grid place-items-center">
        <svg viewBox="0 0 64 64" className="w-14 h-14">
          <g fill="url(#orbGrad)">
            <rect x="13" y="26" width="5" height="12" rx="2.5">
              <animate attributeName="height" values="12;20;12" dur="1.3s" repeatCount="indefinite" />
              <animate attributeName="y" values="26;22;26" dur="1.3s" repeatCount="indefinite" />
            </rect>
            <rect x="22" y="20" width="5" height="24" rx="2.5">
              <animate attributeName="height" values="24;32;24" dur="1.1s" repeatCount="indefinite" />
              <animate attributeName="y" values="20;16;20" dur="1.1s" repeatCount="indefinite" />
            </rect>
            <rect x="30" y="14" width="5" height="36" rx="2.5">
              <animate attributeName="height" values="36;44;36" dur="0.9s" repeatCount="indefinite" />
              <animate attributeName="y" values="14;10;14" dur="0.9s" repeatCount="indefinite" />
            </rect>
            <rect x="38" y="20" width="5" height="24" rx="2.5">
              <animate attributeName="height" values="24;32;24" dur="1.2s" repeatCount="indefinite" />
              <animate attributeName="y" values="20;16;20" dur="1.2s" repeatCount="indefinite" />
            </rect>
            <rect x="46" y="26" width="5" height="12" rx="2.5">
              <animate attributeName="height" values="12;20;12" dur="1.4s" repeatCount="indefinite" />
              <animate attributeName="y" values="26;22;26" dur="1.4s" repeatCount="indefinite" />
            </rect>
          </g>
          <defs>
            <linearGradient id="orbGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#a78bfa" />
              <stop offset="50%" stopColor="#ff6b6b" />
              <stop offset="100%" stopColor="#ffb86b" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
}
