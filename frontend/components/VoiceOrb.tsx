"use client";
import { motion } from "framer-motion";
import { Mic, MicOff } from "lucide-react";

type Props = {
  state: "idle" | "listening" | "thinking" | "speaking" | "connecting";
  onToggle: () => void;
  connected: boolean;
};

const COPY: Record<Props["state"], string> = {
  idle: "Tap to start",
  listening: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking…",
  connecting: "Connecting…",
};

export default function VoiceOrb({ state, onToggle, connected }: Props) {
  const color =
    state === "listening" ? "#34d399"
    : state === "speaking" ? "#a78bfa"
    : state === "thinking" ? "#ffb86b"
    : state === "connecting" ? "#facc15"
    : "#38bdf8";

  return (
    <div className="relative flex flex-col items-center gap-6">
      <motion.button
        onClick={onToggle}
        whileTap={{ scale: 0.96 }}
        whileHover={{ scale: 1.02 }}
        className="relative w-[280px] h-[280px] rounded-full select-none"
        style={{
          background: `radial-gradient(circle at 30% 30%, ${color}55, transparent 60%), radial-gradient(circle at 70% 70%, #ff6b6b22, transparent 65%), radial-gradient(circle at 50% 50%, #06070d, #10131e)`,
          boxShadow:
            `inset 0 0 80px ${color}33, 0 30px 80px rgba(0,0,0,0.6), 0 0 60px ${color}33`,
        }}
        aria-label={connected ? "Stop voice session" : "Start voice session"}
      >
        {/* outer pulsing rings */}
        {(state === "listening" || state === "speaking" || state === "connecting") && (
          <>
            <span className="pulse-ring" />
            <motion.span
              className="absolute inset-0 rounded-full"
              animate={{ scale: [1, 1.06, 1], opacity: [0.6, 0.1, 0.6] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
              style={{ boxShadow: `0 0 0 14px ${color}22` }}
            />
          </>
        )}

        {/* swirling gradient interior */}
        <motion.div
          className="absolute inset-3 rounded-full"
          animate={{ rotate: state === "speaking" ? 360 : 0 }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
          style={{
            background: `conic-gradient(from 0deg, ${color}66, transparent 25%, ${color}33 50%, transparent 75%, ${color}66 100%)`,
            opacity: state === "idle" ? 0.4 : 0.9,
            filter: "blur(8px)",
          }}
        />
        <div className="absolute inset-6 rounded-full bg-ink-900/80 backdrop-blur-md border border-white/5 flex flex-col items-center justify-center">
          {connected ? (
            <Mic className="w-14 h-14" strokeWidth={1.2} style={{ color }} />
          ) : (
            <MicOff className="w-14 h-14" strokeWidth={1.2} style={{ color: "#777" }} />
          )}
          <span className="mt-2 text-xs font-mono text-zinc-400 uppercase tracking-[0.3em]">
            {connected ? state : "offline"}
          </span>
        </div>
      </motion.button>

      <motion.div
        key={state + String(connected)}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <div className="text-sm font-mono text-zinc-300/90 tracking-wide">
          {connected ? COPY[state] : "Click the orb to begin"}
        </div>
      </motion.div>
    </div>
  );
}
