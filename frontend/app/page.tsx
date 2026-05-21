"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { RotateCcw } from "lucide-react";
import VoiceOrb from "@/components/VoiceOrb";
import Transcript, { type Turn } from "@/components/Transcript";
import ModeBadge from "@/components/ModeBadge";
import ProgressPanel from "@/components/ProgressPanel";
import QuickCommands from "@/components/QuickCommands";
import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import Features from "@/components/Features";
import CurriculumShowcase from "@/components/CurriculumShowcase";
import StackSection from "@/components/StackSection";
import Footer from "@/components/Footer";
import { VoiceClient, type VoiceEvent } from "@/lib/voiceClient";

type OrbState = "idle" | "listening" | "thinking" | "speaking";
type Mode = "idle" | "teaching" | "quiz" | "conversation" | "doubt";

export default function Page() {
  const [connected, setConnected] = useState(false);
  const [orb, setOrb] = useState<OrbState>("idle");
  const [mode, setMode] = useState<Mode>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [micLevel, setMicLevel] = useState(0); // 0..1 normalised
  const [connError, setConnError] = useState<string | null>(null);
  const [userInterim, setUserInterim] = useState("");
  const [assistantInterim, setAssistantInterim] = useState("");
  const [quiz, setQuiz] = useState({ index: 0, total: 0, score: 0 });
  const [engagement, setEngagement] = useState<{ score: number; label: string; paceWpm: number } | null>(null);
  const clientRef = useRef<VoiceClient | null>(null);
  const assistantBuf = useRef("");

  const wsUrl = useMemo(() => {
    const env = process.env.NEXT_PUBLIC_WS_URL;
    if (env) return env;
    if (typeof window !== "undefined") {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${window.location.hostname}:8000/ws`;
    }
    return "ws://localhost:8000/ws";
  }, []);

  const onEvent = useCallback((e: VoiceEvent) => {
    switch (e.type) {
      case "connection":
        if (e.status === "connected") { setConnected(true); setConnError(null); }
        else if (e.status === "disconnected") {
          setConnected(false); setOrb("idle");
        }
        else if (e.status === "error") { setConnError(e.message || "connection error"); }
        break;
      case "mic_level":
        // 32768 = full-scale int16. ~3000 ≈ confident speech. Clamp to 0..1.
        setMicLevel(Math.min(1, e.rms / 3000));
        break;
      case "user_speaking":
        if (e.speaking) {
          setOrb("listening");
          // Flush any in-flight assistant text from the previous turn.
          if (assistantBuf.current.trim()) {
            const text = assistantBuf.current;
            assistantBuf.current = "";
            setAssistantInterim("");
            setTurns((t) => [...t, { id: id(), role: "assistant", text, at: Date.now() }]);
          }
        } else {
          setOrb("thinking");
        }
        break;
      case "bot_speaking":
        setOrb(e.speaking ? "speaking" : connected ? "idle" : "idle");
        if (!e.speaking) {
          // Bot finished — commit whatever we buffered.
          if (assistantBuf.current.trim()) {
            const text = assistantBuf.current;
            assistantBuf.current = "";
            setAssistantInterim("");
            setTurns((t) => [...t, { id: id(), role: "assistant", text, at: Date.now() }]);
          }
          setRefreshKey((k) => k + 1);
        }
        break;
      case "transcript":
        if (e.role === "user") {
          if (e.interim) {
            // Live preview as user speaks.
            setUserInterim(e.text);
          } else if (e.text.trim()) {
            // Final transcription. Commit + clear interim.
            setUserInterim("");
            setTurns((t) => [
              ...t,
              { id: id(), role: "user", text: e.text, language: e.language, at: Date.now() },
            ]);
          }
        } else if (e.role === "assistant" && e.interim) {
          // Bot text streaming in.
          assistantBuf.current += e.text;
          setAssistantInterim(assistantBuf.current);
        }
        break;
      case "interrupt":
        // visual cue handled by orb state
        break;
      case "state":
        setMode(e.mode as Mode);
        setQuiz({ index: e.quiz_index, total: e.quiz_total, score: e.quiz_score });
        if (typeof e.engagement_score === "number") {
          setEngagement({
            score: e.engagement_score,
            label: e.engagement_label || "neutral",
            paceWpm: e.pace_wpm || 0,
          });
        }
        setRefreshKey((k) => k + 1);
        break;
      case "end":
        setConnected(false); setOrb("idle");
        break;
    }
  }, [connected]);

  const toggle = useCallback(async () => {
    if (connected) {
      await clientRef.current?.disconnect();
      clientRef.current = null;
      return;
    }
    const c = new VoiceClient({ url: wsUrl, onEvent });
    clientRef.current = c;
    try {
      await c.connect();
    } catch (err: any) {
      console.error("connect failed", err);
      setConnected(false);
    }
  }, [connected, wsUrl, onEvent]);

  useEffect(() => () => { clientRef.current?.disconnect(); }, []);

  return (
    <main className="relative z-10 min-h-screen text-zinc-100">
      <Navbar />
      <Hero />

      <section
        id="demo"
        className="relative max-w-7xl mx-auto px-6 pb-24"
      >
        <div className="mb-10 flex items-end justify-between flex-wrap gap-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.4em] text-accent-violet mb-3">
              §01 · live demo
            </div>
            <h2 className="font-display text-4xl md:text-5xl leading-tight tracking-tight">
              Click the orb. <span className="text-gradient">Talk.</span>
            </h2>
          </div>
          <p className="text-sm text-zinc-400 max-w-md leading-relaxed">
            Mic permission needed. Headphones recommended (kills bot-echo feedback).
            All processing local except STT / LLM / TTS calls.
          </p>
        </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-8">
        <div className="space-y-8">
          <div className="glass rounded-3xl p-8 md:p-10 flex flex-col items-center gap-8 shimmer-border">
            <div className="w-full flex items-center justify-between">
              <div className="flex items-center gap-2 flex-wrap">
                <ModeBadge mode={mode} />
                {quiz.total > 0 && (
                  <span className="text-[11px] font-mono text-accent-peach px-2 py-0.5 rounded-full bg-accent-peach/10 border border-accent-peach/30">
                    Q {Math.min(quiz.index, quiz.total)}/{quiz.total} · score {quiz.score}
                  </span>
                )}
                {engagement && engagement.score > 0 && (
                  <span
                    title={`Engagement: ${(engagement.score * 100).toFixed(0)}% · pace ${engagement.paceWpm.toFixed(0)} wpm`}
                    className={
                      "text-[11px] font-mono px-2 py-0.5 rounded-full border " +
                      (engagement.label === "engaged"
                        ? "text-accent-mint bg-accent-mint/10 border-accent-mint/30"
                        : engagement.label === "low"
                        ? "text-accent-coral bg-accent-coral/10 border-accent-coral/30"
                        : "text-zinc-400 bg-white/5 border-white/10")
                    }
                  >
                    {engagement.label}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs font-mono text-zinc-500">
                <button
                  onClick={() => setTurns([])}
                  title="Clear the on-screen transcript"
                  className="flex items-center gap-1 hover:text-zinc-200 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  clear transcript
                </button>
                <span className="opacity-60">·</span>
                {/* Status indicator (not a button) */}
                <span className="flex items-center gap-1.5" title={connected ? "WebSocket open" : "WebSocket closed — click the orb to connect"}>
                  <span className={
                    "w-1.5 h-1.5 rounded-full " +
                    (connected ? "bg-accent-mint animate-pulse" : "bg-zinc-500")
                  } />
                  {connected ? "live" : "offline"}
                </span>
              </div>
            </div>
            <VoiceOrb state={orb} onToggle={toggle} connected={connected} />

            {/* Mic level meter — proves the mic is actually capturing audio. */}
            {connected && (
              <div className="w-full max-w-md">
                <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-400 mb-1.5">
                  <span>mic level</span>
                  <span>{micLevel > 0.05 ? "active" : "quiet"}</span>
                </div>
                <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
                  <div
                    className="h-full transition-[width] duration-75 ease-out"
                    style={{
                      width: `${Math.min(100, micLevel * 100)}%`,
                      background:
                        micLevel > 0.5
                          ? "linear-gradient(90deg, #34d399, #ffb86b)"
                          : "linear-gradient(90deg, #38bdf8, #a78bfa)",
                    }}
                  />
                </div>
                <p className="mt-2 text-[10px] font-mono text-zinc-500 leading-snug text-center">
                  speak normally — bar should jump. flat? mic not capturing.
                  <br />
                  <strong className="text-amber-400">use headphones</strong> to avoid bot-echo feedback.
                </p>
              </div>
            )}
            {connError && (
              <div className="text-xs font-mono text-accent-coral">
                connection error: {connError}
              </div>
            )}

            <QuickCommands />
          </div>

          <div className="h-[420px]">
            <Transcript turns={turns} userInterim={userInterim} assistantInterim={assistantInterim} />
          </div>
        </div>

        <aside className="space-y-4">
          <ProgressPanel refreshKey={refreshKey} />
        </aside>
      </div>
      </section>

      <Features />
      <CurriculumShowcase />
      <StackSection />
      <Footer />
    </main>
  );
}

function id() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}
