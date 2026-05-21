"use client";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { fetchMetrics, type Metrics } from "@/lib/api";

const STACK = [
  { name: "Pipecat", role: "Orchestration", url: "https://github.com/pipecat-ai/pipecat" },
  { name: "Groq", role: "LLM Llama 3.x", url: "https://groq.com" },
  { name: "AssemblyAI", role: "Streaming STT", url: "https://www.assemblyai.com" },
  { name: "ElevenLabs", role: "Multilingual TTS", url: "https://elevenlabs.io" },
  { name: "Silero", role: "VAD", url: "https://github.com/snakers4/silero-vad" },
  { name: "Next.js 14", role: "Frontend", url: "https://nextjs.org" },
  { name: "FastAPI", role: "Backend", url: "https://fastapi.tiangolo.com" },
  { name: "SQLite + FSRS", role: "Memory", url: "https://www.sqlite.org" },
];

export default function StackSection() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetchMetrics()
        .then((m) => {
          if (!cancelled) setMetrics(m);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <section
      id="stack"
      className="relative max-w-7xl mx-auto px-6 py-24 md:py-32"
    >
      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr] gap-12 mb-14">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
        >
          <div className="text-[10px] font-mono uppercase tracking-[0.4em] text-accent-mint mb-3">
            §04 · stack & latency
          </div>
          <h2 className="font-display text-4xl md:text-5xl leading-tight tracking-tight">
            <span className="text-gradient">Open</span> tools,<br />
            <span className="text-zinc-300">measured</span> performance.
          </h2>
        </motion.div>
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="grid grid-cols-2 gap-3 self-end"
        >
          <LatencyTile label="STT" stat={metrics?.stt_ms} target="< 200 ms" />
          <LatencyTile label="LLM TTFT" stat={metrics?.llm_ttft_ms} target="< 500 ms" />
          <LatencyTile label="TTS first" stat={metrics?.tts_first_ms} target="< 450 ms" />
          <LatencyTile label="E2E total" stat={metrics?.total_ms} target="< 1500 ms" accent />
        </motion.div>
      </div>

      {/* marquee strip */}
      <div className="marquee-mask overflow-hidden py-4 border-y border-white/5 bg-ink-950/40">
        <div className="marquee-track flex gap-6 w-[200%]">
          {[...STACK, ...STACK].map((s, i) => (
            <a
              key={i}
              href={s.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-full glass border border-white/10 hover:border-accent-violet/50 transition-colors whitespace-nowrap"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-accent-violet" />
              <span className="font-display text-sm text-zinc-100">{s.name}</span>
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                · {s.role}
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

function LatencyTile({
  label,
  stat,
  target,
  accent,
}: {
  label: string;
  stat?: { n: number; p50: number; p95: number };
  target: string;
  accent?: boolean;
}) {
  const p50 = stat?.p50 ?? 0;
  const p95 = stat?.p95 ?? 0;
  const live = (stat?.n ?? 0) > 0;
  return (
    <div
      className={
        "glass rounded-xl p-4 border border-white/10 " +
        (accent ? "shimmer-border" : "")
      }
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-zinc-500">
          {label}
        </span>
        <span
          className={
            "text-[9px] font-mono flex items-center gap-1 " +
            (live ? "text-accent-mint" : "text-zinc-600")
          }
        >
          <span
            className={
              "w-1 h-1 rounded-full " +
              (live ? "bg-accent-mint animate-pulse" : "bg-zinc-700")
            }
          />
          {live ? "live" : "—"}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-2xl text-zinc-100 num-tick">
          {live ? Math.round(p50) : "—"}
        </span>
        <span className="text-xs font-mono text-zinc-500">ms p50</span>
      </div>
      <div className="mt-1 text-[10px] font-mono text-zinc-500">
        p95 {live ? Math.round(p95) : "—"} ms · target {target}
      </div>
    </div>
  );
}
