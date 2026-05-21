"use client";
import { motion } from "framer-motion";

export default function Footer() {
  return (
    <footer className="relative z-10 border-t border-white/5 mt-10 bg-ink-950/60">
      <div className="max-w-7xl mx-auto px-6 py-10">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-start">
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-violet via-accent-coral to-accent-peach grid place-items-center">
                <svg viewBox="0 0 64 64" className="w-4 h-4">
                  <g fill="#fff">
                    <rect x="22" y="20" width="5" height="24" rx="2.5" />
                    <rect x="30" y="14" width="5" height="36" rx="2.5" />
                    <rect x="38" y="20" width="5" height="24" rx="2.5" />
                  </g>
                </svg>
              </div>
              <div className="font-display text-base text-zinc-100">VoiceTutor</div>
            </div>
            <p className="text-[12px] text-zinc-500 leading-relaxed max-w-xs">
              Voice-first Spanish tutor built for the AI Engineer take-home.
              Open source, free-tier stack, sub-1.5s end-to-end latency.
            </p>
          </motion.div>

          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-3">
              Sections
            </div>
            <ul className="space-y-2 text-sm">
              {["Demo", "Features", "Curriculum", "Stack"].map((l) => (
                <li key={l}>
                  <a
                    href={`#${l.toLowerCase()}`}
                    className="text-zinc-300 hover:text-white link-reveal"
                  >
                    {l}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-3">
              Built with
            </div>
            <div className="flex flex-wrap gap-2">
              {["Pipecat", "Groq", "AssemblyAI", "ElevenLabs", "Silero", "Next.js"].map((n) => (
                <span
                  key={n}
                  className="text-[11px] font-mono px-2.5 py-1 rounded-full glass border border-white/10 text-zinc-300"
                >
                  {n}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-3 text-[11px] font-mono text-zinc-500">
          <div>built for the AI Engineer take-home · {new Date().getFullYear()}</div>
          <div className="opacity-70">
            ¡hola! → me llamo Sofía. mucho gusto.
          </div>
        </div>
      </div>
    </footer>
  );
}
