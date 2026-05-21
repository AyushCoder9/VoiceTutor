"use client";
import { motion } from "framer-motion";

const CMDS = [
  { label: "Teach me greetings",        topic: "teaching" },
  { label: "Quiz me on yesterday",      topic: "quiz" },
  { label: "Let's roleplay a café",     topic: "conversation" },
  { label: "I have a doubt",            topic: "doubt" },
];

export default function QuickCommands() {
  return (
    <div className="space-y-2">
      <h4 className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500">
        Try saying
      </h4>
      <div className="flex flex-wrap gap-2">
        {CMDS.map((c, i) => (
          <motion.div
            key={c.label}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            whileHover={{ y: -2 }}
            className="px-3 py-1.5 rounded-full glass text-xs font-mono text-zinc-300 cursor-default hover:text-white transition-colors"
          >
            "{c.label}"
          </motion.div>
        ))}
      </div>
    </div>
  );
}
