"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";

type Section = { id: string; label: string };

const SECTIONS: Section[] = [
  { id: "demo", label: "Demo" },
  { id: "features", label: "Features" },
  { id: "curriculum", label: "Curriculum" },
  { id: "stack", label: "Stack" },
];

export default function Navbar() {
  const [active, setActive] = useState<string>("demo");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    onScroll();
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(e.target.id);
        }
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    SECTIONS.forEach((s) => {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, []);

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
      className={
        "fixed top-0 left-0 right-0 z-50 transition-all duration-500 " +
        (scrolled
          ? "backdrop-blur-xl bg-ink-950/60 border-b border-white/5"
          : "bg-transparent border-b border-transparent")
      }
    >
      <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
        <a href="#top" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent-violet via-accent-coral to-accent-peach grid place-items-center shadow-lg shadow-accent-violet/25 group-hover:shadow-accent-coral/40 transition-shadow duration-500">
            <svg viewBox="0 0 64 64" className="w-5 h-5" aria-hidden="true">
              <g fill="#ffffff">
                <rect x="13" y="26" width="5" height="12" rx="2.5" opacity="0.85" />
                <rect x="22" y="20" width="5" height="24" rx="2.5" opacity="0.95" />
                <rect x="30" y="14" width="5" height="36" rx="2.5" />
                <rect x="38" y="20" width="5" height="24" rx="2.5" opacity="0.95" />
                <rect x="46" y="26" width="5" height="12" rx="2.5" opacity="0.85" />
              </g>
            </svg>
          </div>
          <div className="hidden md:block leading-tight">
            <div className="font-display text-base">VoiceTutor</div>
            <div className="text-[9px] font-mono uppercase tracking-[0.3em] text-zinc-500 -mt-0.5">
              Profesora Sofía
            </div>
          </div>
        </a>

        <nav className="flex items-center gap-1 text-xs font-mono">
          {SECTIONS.map((s) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className={
                "px-3 py-1.5 rounded-full transition-colors duration-300 " +
                (active === s.id
                  ? "text-white bg-white/10"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-white/5")
              }
            >
              {s.label}
            </a>
          ))}
          <span className="hidden lg:flex items-center gap-1.5 ml-2 pl-3 border-l border-white/10 text-[10px] uppercase tracking-[0.25em] text-accent-mint">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-mint dot-live" />
            free tier
          </span>
        </nav>
      </div>
    </motion.header>
  );
}
