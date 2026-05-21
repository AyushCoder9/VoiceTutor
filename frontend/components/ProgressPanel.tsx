"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Trophy, Sparkles, Clock, Activity, Trash2, Download, Eraser } from "lucide-react";
import {
  fetchCurriculum, fetchProgress, fetchMetrics,
  resetProgress, resetWeakSpots, exportProgress,
  type Curriculum, type Progress, type Metrics,
} from "@/lib/api";

export default function ProgressPanel({ refreshKey }: { refreshKey: number }) {
  const [curr, setCurr] = useState<Curriculum | null>(null);
  const [prog, setProg] = useState<Progress | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [c, p, m] = await Promise.all([fetchCurriculum(), fetchProgress(), fetchMetrics()]);
        if (!cancelled) { setCurr(c); setProg(p); setMetrics(m); }
      } catch { /* server may not be up yet — silent */ }
    }
    load();
    const t = setInterval(load, 4000);
    return () => { cancelled = true; clearInterval(t); };
  }, [refreshKey]);

  const [menuOpen, setMenuOpen] = useState(false);

  const onFullReset = async () => {
    if (!confirm("Wipe ALL progress, weak spots, and review history?")) return;
    await resetProgress();
    setProg(null);
    setMenuOpen(false);
    setTimeout(() => fetchProgress().then(setProg).catch(() => {}), 200);
  };

  const onResetWeak = async () => {
    if (!confirm("Clear weak spots and recent mistakes? (Mastered words are kept.)")) return;
    await resetWeakSpots();
    setMenuOpen(false);
    setTimeout(() => fetchProgress().then(setProg).catch(() => {}), 200);
  };

  const onExport = async () => {
    const data = await exportProgress();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `voicetutor-progress-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setMenuOpen(false);
  };

  return (
    <div className="space-y-4">
      <div className="glass rounded-2xl p-5 shimmer-border">
        <div className="flex items-center justify-between mb-3 relative">
          <div className="flex items-center gap-2">
            <Trophy className="w-4 h-4 text-accent-peach" />
            <h3 className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">Curriculum</h3>
          </div>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            title="Reset & export options"
            className="text-zinc-500 hover:text-accent-coral transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          {menuOpen && (
            <div
              onMouseLeave={() => setMenuOpen(false)}
              className="absolute right-0 top-7 z-20 glass rounded-xl border border-white/10 p-1.5 w-56 shadow-2xl shadow-black/50"
            >
              <MenuItem onClick={onExport} icon={Download} hint="JSON backup">
                Export progress
              </MenuItem>
              <MenuItem onClick={onResetWeak} icon={Eraser} hint="Keeps mastery">
                Reset weak spots only
              </MenuItem>
              <MenuItem onClick={onFullReset} icon={Trash2} hint="Everything" danger>
                Full reset
              </MenuItem>
              <div className="mt-1 pt-1 border-t border-white/5 px-2 py-1 text-[9px] font-mono text-zinc-500 leading-snug">
                Or say "reset my progress" / "reset weak spots" — bot will ask for voice confirmation.
              </div>
            </div>
          )}
        </div>
        <ul className="space-y-2">
          {curr?.lessons.map((l) => {
            const p = prog?.progress.find((x) => x.lesson_id === l.id);
            const score = p?.score ?? 0;
            return (
              <motion.li
                key={l.id}
                whileHover={{ x: 2 }}
                className="flex items-start justify-between text-sm py-1.5 px-2 rounded-lg hover:bg-white/5 cursor-default"
              >
                <div className="min-w-0">
                  <div className="font-medium text-zinc-100 truncate">{l.title}</div>
                  <div className="text-[11px] font-mono text-zinc-500">{l.level} · ~{l.estimated_minutes} min</div>
                </div>
                <div className="ml-2 text-right">
                  <div className="text-[10px] font-mono text-zinc-500">{Math.round(score * 100)}%</div>
                  <div className="h-1 mt-1 w-16 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-accent-violet to-accent-sky" style={{ width: `${score*100}%` }} />
                  </div>
                </div>
              </motion.li>
            );
          })}
          {!curr && <li className="text-xs text-zinc-500 font-mono">loading…</li>}
        </ul>
      </div>

      <div className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-accent-violet" />
          <h3 className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">Weak spots</h3>
        </div>
        {prog?.weak_areas.length ? (
          <ul className="flex flex-wrap gap-2">
            {prog.weak_areas.map((w) => (
              <li key={w.word} className="px-2 py-1 rounded-md text-xs font-mono bg-accent-coral/15 border border-accent-coral/30 text-zinc-100">
                {w.word} <span className="text-[10px] text-zinc-400">·{w.lapses}</span>
              </li>
            ))}
          </ul>
        ) : <div className="text-xs text-zinc-500 font-mono">none yet — practise to see what trips you up.</div>}
      </div>

      <div className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <Clock className="w-4 h-4 text-accent-mint" />
          <h3 className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">Due for review</h3>
        </div>
        {prog?.due_vocab.length ? (
          <ul className="flex flex-wrap gap-2">
            {prog.due_vocab.slice(0, 8).map((w) => (
              <li key={w.word} className="px-2 py-1 rounded-md text-xs font-mono bg-accent-mint/10 border border-accent-mint/30 text-zinc-100">
                {w.word}
              </li>
            ))}
          </ul>
        ) : <div className="text-xs text-zinc-500 font-mono">nothing due — FSRS scheduler is happy.</div>}
      </div>

      <div className="glass rounded-2xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-accent-sky" />
          <h3 className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">Latency (P50/P95)</h3>
        </div>
        <table className="w-full text-xs font-mono">
          <tbody className="text-zinc-400">
            <Row label="STT"  m={metrics?.stt_ms} />
            <Row label="LLM TTFT" m={metrics?.llm_ttft_ms} />
            <Row label="TTS first" m={metrics?.tts_first_ms} />
            <Row label="Total"   m={metrics?.total_ms} accent />
          </tbody>
        </table>
        <div className="text-[10px] text-zinc-500 mt-2">target: total &lt; 1500ms</div>
      </div>
    </div>
  );
}

function Row({ label, m, accent }: { label: string; m?: { p50: number; p95: number; n: number }; accent?: boolean }) {
  return (
    <tr className={accent ? "text-zinc-200" : ""}>
      <td className="py-0.5 pr-2 text-zinc-500">{label}</td>
      <td className="text-right tabular-nums">{m?.p50 ?? "—"}ms</td>
      <td className="text-right tabular-nums text-zinc-500">/ {m?.p95 ?? "—"}ms</td>
    </tr>
  );
}

function MenuItem({
  onClick,
  icon: Icon,
  children,
  hint,
  danger,
}: {
  onClick: () => void;
  icon: React.ElementType;
  children: React.ReactNode;
  hint?: string;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors " +
        (danger
          ? "hover:bg-accent-coral/10 text-zinc-200 hover:text-accent-coral"
          : "hover:bg-white/5 text-zinc-200")
      }
    >
      <Icon className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-mono">{children}</div>
        {hint && <div className="text-[9px] font-mono text-zinc-500 mt-0.5">{hint}</div>}
      </div>
    </button>
  );
}
