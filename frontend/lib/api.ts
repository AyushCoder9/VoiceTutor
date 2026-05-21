const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Lesson = {
  id: string;
  title: string;
  level: string;
  estimated_minutes: number;
  objective: string;
  vocab_count: number;
};

export type Curriculum = {
  language: string;
  native_language: string;
  lessons: Lesson[];
};

export type Progress = {
  user_id: string;
  user: { name: string; native_lang: string; target_lang: string } | null;
  progress: Array<{ lesson_id: string; status: string; score: number; attempts: number }>;
  weak_areas: Array<{ word: string; lang: string; lapses: number; ease: number }>;
  due_vocab: Array<{ word: string; lang: string; next_review_at: string }>;
  recent_mistakes: Array<{ kind: string; expected: string; got: string; created_at: string }>;
};

export type Metrics = {
  stt_ms: { n: number; p50: number; p95: number; max: number; mean: number };
  llm_ttft_ms: { n: number; p50: number; p95: number; max: number; mean: number };
  tts_first_ms: { n: number; p50: number; p95: number; max: number; mean: number };
  total_ms: { n: number; p50: number; p95: number; max: number; mean: number };
};

export async function fetchCurriculum(): Promise<Curriculum> {
  const r = await fetch(`${API}/curriculum`, { cache: "no-store" });
  return r.json();
}

export async function fetchProgress(): Promise<Progress> {
  const r = await fetch(`${API}/progress`, { cache: "no-store" });
  return r.json();
}

export async function fetchMetrics(): Promise<Metrics> {
  const r = await fetch(`${API}/metrics`, { cache: "no-store" });
  return r.json();
}

export async function resetProgress(): Promise<{ user_id: string; deleted: Record<string, number> }> {
  const r = await fetch(`${API}/reset_progress`, { method: "POST" });
  return r.json();
}

export async function resetWeakSpots(): Promise<{ user_id: string; updated: Record<string, number> }> {
  const r = await fetch(`${API}/reset_weak_spots`, { method: "POST" });
  return r.json();
}

export async function resetLesson(lessonId: string): Promise<{ deleted: Record<string, number> }> {
  const r = await fetch(`${API}/reset_lesson?lesson_id=${encodeURIComponent(lessonId)}`, { method: "POST" });
  return r.json();
}

export async function exportProgress(): Promise<unknown> {
  const r = await fetch(`${API}/export_progress`);
  return r.json();
}
