"use client";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { fetchCurriculum, type Curriculum, type Lesson } from "@/lib/api";

export default function CurriculumShowcase() {
  const [data, setData] = useState<Curriculum | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCurriculum()
      .then((c) => {
        if (!cancelled) setData(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      id="curriculum"
      className="relative max-w-7xl mx-auto px-6 py-24 md:py-32"
    >
      <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr] gap-10 items-end mb-14">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6 }}
        >
          <div className="text-[10px] font-mono uppercase tracking-[0.4em] text-accent-coral mb-3">
            §03 · curriculum
          </div>
          <h2 className="font-display text-4xl md:text-5xl leading-tight tracking-tight">
            Six hand-authored lessons.<br />
            <span className="text-gradient">A1 to A2.</span>
          </h2>
        </motion.div>
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-zinc-400 leading-relaxed"
        >
          Hand-authored over LLM-generated so a reviewer can spot-check grammar.
          Adding a seventh lesson is a JSON edit — no rebuild.
        </motion.p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {(data?.lessons ?? PLACEHOLDER_LESSONS).map((lesson, i) => (
          <LessonCard key={lesson.id} lesson={lesson} index={i} />
        ))}
      </div>
    </section>
  );
}

function LessonCard({ lesson, index }: { lesson: Lesson; index: number }) {
  const num = String(index + 1).padStart(2, "0");
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{ duration: 0.5, delay: (index % 6) * 0.06, ease: [0.16, 1, 0.3, 1] }}
      className="group card-tilt glass rounded-2xl border border-white/10 overflow-hidden relative"
    >
      <div className="p-6 pb-5">
        <div className="flex items-center justify-between mb-6">
          <span className="font-display text-3xl text-zinc-700 group-hover:text-zinc-500 transition-colors">
            {num}
          </span>
          <span className="text-[10px] font-mono uppercase tracking-[0.25em] px-2 py-0.5 rounded-full border border-accent-violet/40 text-accent-violet bg-accent-violet/10">
            {lesson.level}
          </span>
        </div>
        <h3 className="font-display text-xl text-zinc-100 leading-tight mb-2">
          {lesson.title}
        </h3>
        <p className="text-[13px] text-zinc-400 leading-relaxed line-clamp-2">
          {lesson.objective}
        </p>
      </div>
      <div className="px-6 py-3 border-t border-white/5 flex items-center justify-between text-[11px] font-mono text-zinc-500">
        <span>
          <span className="text-zinc-300">{lesson.vocab_count}</span> vocab · {lesson.estimated_minutes} min
        </span>
        <ArrowUpRight className="w-3.5 h-3.5 text-zinc-600 group-hover:text-accent-coral group-hover:rotate-12 transition-all" />
      </div>
    </motion.div>
  );
}

const PLACEHOLDER_LESSONS: Lesson[] = [
  { id: "greetings-001", title: "Greetings & Introductions", level: "A1", estimated_minutes: 5, objective: "Greet, introduce, ask how someone is.", vocab_count: 10 },
  { id: "numbers-001", title: "Numbers 1 to 20", level: "A1", estimated_minutes: 6, objective: "Count and use numbers in phrases.", vocab_count: 20 },
  { id: "ordering-food-001", title: "Ordering Food", level: "A2", estimated_minutes: 7, objective: "Order politely, ask for the bill.", vocab_count: 12 },
  { id: "family-001", title: "Family Members", level: "A1", estimated_minutes: 6, objective: "Talk about parents, siblings, relatives.", vocab_count: 11 },
  { id: "days-time-001", title: "Days of the Week & Time", level: "A2", estimated_minutes: 7, objective: "Name days, tell time at the hour.", vocab_count: 12 },
  { id: "directions-001", title: "Asking for Directions", level: "A2", estimated_minutes: 8, objective: "Ask where places are, understand directions.", vocab_count: 12 },
];
