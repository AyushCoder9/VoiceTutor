"use client";
import { motion } from "framer-motion";
import { BookOpen, Brain, MessageCircle, HelpCircle, Sparkles } from "lucide-react";

type Mode = "idle" | "teaching" | "quiz" | "conversation" | "doubt";

const META: Record<Mode, { label: string; color: string; Icon: React.ElementType }> = {
  idle:         { label: "Idle",         color: "#38bdf8", Icon: Sparkles },
  teaching:     { label: "Teaching",     color: "#a78bfa", Icon: BookOpen },
  quiz:         { label: "Quiz",         color: "#ffb86b", Icon: Brain },
  conversation: { label: "Conversation", color: "#34d399", Icon: MessageCircle },
  doubt:        { label: "Doubt",        color: "#ff6b6b", Icon: HelpCircle },
};

export default function ModeBadge({ mode }: { mode: Mode }) {
  const { label, color, Icon } = META[mode];
  return (
    <motion.div
      layout
      key={mode}
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-full px-4 py-1.5 flex items-center gap-2 shimmer-border"
      style={{ borderColor: `${color}55` }}
    >
      <Icon className="w-3.5 h-3.5" style={{ color }} strokeWidth={2.2} />
      <span className="text-xs font-mono uppercase tracking-[0.25em]" style={{ color }}>
        {label}
      </span>
    </motion.div>
  );
}
