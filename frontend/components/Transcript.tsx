"use client";
import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";

export type Turn = {
  id: string;
  role: "user" | "assistant";
  text: string;
  language?: string;
  at: number;
};

export default function Transcript({
  turns,
  userInterim = "",
  assistantInterim = "",
}: {
  turns: Turn[];
  userInterim?: string;
  assistantInterim?: string;
}) {
  const scroller = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns]);

  return (
    <div className="glass rounded-2xl p-1 shimmer-border overflow-hidden h-full flex flex-col">
      <div className="px-5 pt-4 pb-2 flex items-center justify-between border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-mint animate-pulse" />
          <h3 className="text-xs font-mono uppercase tracking-[0.3em] text-zinc-400">
            Live Transcript
          </h3>
        </div>
        <span className="text-[10px] font-mono text-zinc-500">{turns.length} turns</span>
      </div>
      <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <AnimatePresence initial={false}>
          {turns.length === 0 && !userInterim && !assistantInterim && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-zinc-500 text-sm font-mono italic"
            >
              transcript will appear as you speak…
            </motion.div>
          )}
          {turns.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={clsx(
                "max-w-[90%] rounded-xl px-3 py-2 leading-relaxed text-sm",
                t.role === "user"
                  ? "ml-auto bg-accent-violet/15 border border-accent-violet/25 text-zinc-100"
                  : "mr-auto bg-white/5 border border-white/10 text-zinc-200"
              )}
            >
              <div className="flex items-center gap-2 mb-1 text-[10px] font-mono uppercase tracking-widest text-zinc-400">
                <span>{t.role === "user" ? "you" : "Sofía"}</span>
                {t.language && <span className="px-1.5 rounded bg-white/5">{t.language}</span>}
              </div>
              <div>{t.text}</div>
            </motion.div>
          ))}
          {/* Live interim bubbles — render even before the final lands. */}
          {assistantInterim && (
            <motion.div
              key="assistant-interim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="max-w-[90%] mr-auto rounded-xl px-3 py-2 leading-relaxed text-sm bg-white/5 border border-dashed border-white/10 text-zinc-300 italic"
            >
              <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1">
                Sofía · streaming
              </div>
              <div>{assistantInterim}</div>
            </motion.div>
          )}
          {userInterim && (
            <motion.div
              key="user-interim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="max-w-[90%] ml-auto rounded-xl px-3 py-2 leading-relaxed text-sm bg-accent-violet/10 border border-dashed border-accent-violet/30 text-zinc-200 italic"
            >
              <div className="text-[10px] font-mono uppercase tracking-widest text-zinc-500 mb-1">
                you · live
              </div>
              <div>{userInterim}</div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
