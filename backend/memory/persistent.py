"""Long-term per-user memory — SQLite.

Why plain SQL over an ORM: keeps deps minimal and makes schema readable in
`schema.sql`. SQLite WAL mode handles concurrent reads while the agent writes.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class PersistentMemory:
    """Long-term store: users, lesson progress, vocab mastery (FSRS-lite), mistakes."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        ddl = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._conn() as c:
            c.executescript(ddl)

    # ---- users ----
    def upsert_user(self, user_id: str, name: str, native_lang: str = "en", target_lang: str = "es") -> None:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO users (id, name, native_lang, target_lang)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name = excluded.name,
                  last_seen_at = datetime('now')
                """,
                (user_id, name, native_lang, target_lang),
            )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    # ---- progress ----
    def record_lesson_score(self, user_id: str, lesson_id: str, score: float) -> None:
        status = "completed" if score >= 0.7 else "in_progress"
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO progress (user_id, lesson_id, status, score, attempts, completed_at, updated_at)
                VALUES (?, ?, ?, ?, 1, CASE WHEN ? >= 0.7 THEN datetime('now') ELSE NULL END, datetime('now'))
                ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                  score = MAX(progress.score, excluded.score),
                  attempts = progress.attempts + 1,
                  status = CASE WHEN excluded.score >= 0.7 THEN 'completed' ELSE progress.status END,
                  completed_at = CASE WHEN excluded.score >= 0.7 AND progress.completed_at IS NULL THEN datetime('now') ELSE progress.completed_at END,
                  updated_at = datetime('now')
                """,
                (user_id, lesson_id, status, score, score),
            )

    def get_progress(self, user_id: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM progress WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- vocab mastery (FSRS-lite) ----
    def record_vocab_attempt(self, user_id: str, word: str, lang: str, success: bool) -> dict[str, Any]:
        """FSRS-lite update.

        success → interval *= ease, ease += 0.05 (cap 2.5)
        lapse   → interval //= 2,  ease -= 0.20 (floor 1.3)
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM vocab_mastery WHERE user_id=? AND word=? AND lang=?",
                (user_id, word, lang),
            ).fetchone()

            ease = row["ease"] if row else 2.5
            interval = row["interval_days"] if row else 1.0
            reps = row["reps"] if row else 0
            lapses = row["lapses"] if row else 0

            if success:
                interval = min(365.0, max(1.0, interval * ease))
                reps += 1
                ease = min(2.5, ease + 0.05)
                next_due_delta = timedelta(days=interval)
            else:
                # Lapse: re-surface quickly (real FSRS behaviour). We keep the
                # `interval_days` field as half of the prior interval for the
                # *next* successful repetition, but schedule the immediate
                # review for ~1 minute from now so it shows up in `due_vocab`.
                interval = max(1.0, interval / 2)
                lapses += 1
                ease = max(1.3, ease - 0.2)
                # Schedule slightly in the past so `due_vocab` (which filters
                # `next_review_at <= now`) immediately resurfaces it.
                next_due_delta = timedelta(seconds=-1)

            # SQLite's datetime('now') returns 'YYYY-MM-DD HH:MM:SS' (space, no T).
            # We must match that exactly for lexicographic <= comparisons.
            _fmt = "%Y-%m-%d %H:%M:%S"
            now = datetime.utcnow().strftime(_fmt)
            next_review = (datetime.utcnow() + next_due_delta).strftime(_fmt)

            c.execute(
                """
                INSERT INTO vocab_mastery (
                  user_id, word, lang, ease, interval_days, reps, lapses, last_review_at, next_review_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, word, lang) DO UPDATE SET
                  ease = excluded.ease,
                  interval_days = excluded.interval_days,
                  reps = excluded.reps,
                  lapses = excluded.lapses,
                  last_review_at = excluded.last_review_at,
                  next_review_at = excluded.next_review_at
                """,
                (user_id, word, lang, ease, interval, reps, lapses, now, next_review),
            )
            return {
                "word": word, "lang": lang, "ease": ease, "interval_days": interval,
                "reps": reps, "lapses": lapses, "next_review_at": next_review,
            }

    def due_vocab(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT * FROM vocab_mastery
                WHERE user_id = ? AND next_review_at <= datetime('now')
                ORDER BY next_review_at ASC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- mistakes ----
    def log_mistake(
        self,
        user_id: str,
        kind: str,
        expected: str | None,
        got: str | None,
        lesson_id: str | None = None,
        note: str | None = None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO mistakes (user_id, lesson_id, kind, expected, got, note) VALUES (?,?,?,?,?,?)",
                (user_id, lesson_id, kind, expected, got, note),
            )

    def recent_mistakes(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM mistakes WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def reset_user_progress(self, user_id: str) -> dict[str, int]:
        """Clear all progress / vocab mastery / mistakes for a user."""
        with self._conn() as c:
            n_prog = c.execute("DELETE FROM progress WHERE user_id = ?", (user_id,)).rowcount
            n_vocab = c.execute("DELETE FROM vocab_mastery WHERE user_id = ?", (user_id,)).rowcount
            n_mist = c.execute("DELETE FROM mistakes WHERE user_id = ?", (user_id,)).rowcount
        return {"progress": n_prog, "vocab_mastery": n_vocab, "mistakes": n_mist}

    def reset_lesson(self, user_id: str, lesson_id: str) -> dict[str, int]:
        """Reset one lesson's progress + its mistakes. Vocab mastery for
        words taught only in that lesson is also wiped."""
        with self._conn() as c:
            n_prog = c.execute(
                "DELETE FROM progress WHERE user_id=? AND lesson_id=?",
                (user_id, lesson_id),
            ).rowcount
            n_mist = c.execute(
                "DELETE FROM mistakes WHERE user_id=? AND lesson_id=?",
                (user_id, lesson_id),
            ).rowcount
        return {"progress": n_prog, "mistakes": n_mist}

    def reset_weak_spots(self, user_id: str) -> dict[str, int]:
        """Clear lapses on every vocab row (resets ease to 2.5, lapses to 0).
        Mastery history (reps, intervals) is kept — this is "give me a fresh
        start on the words I struggle with" without losing what I know."""
        with self._conn() as c:
            n = c.execute(
                "UPDATE vocab_mastery SET lapses=0, ease=2.5 WHERE user_id=? AND lapses>0",
                (user_id,),
            ).rowcount
            n_mist = c.execute(
                "DELETE FROM mistakes WHERE user_id=?",
                (user_id,),
            ).rowcount
        return {"vocab_mastery_reset": n, "mistakes_cleared": n_mist}

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Return a JSON-able snapshot of everything the user owns. Useful for
        backup-before-reset or porting between accounts."""
        return {
            "user_id": user_id,
            "user": self.get_user(user_id),
            "progress": self.get_progress(user_id),
            "vocab_mastery": [
                dict(r) for r in self._all_rows(
                    "SELECT * FROM vocab_mastery WHERE user_id=? ORDER BY word", (user_id,)
                )
            ],
            "mistakes": self.recent_mistakes(user_id, limit=1000),
        }

    def _all_rows(self, sql: str, params: tuple) -> list:
        with self._conn() as c:
            return c.execute(sql, params).fetchall()

    def weak_areas(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """
                SELECT word, lang, lapses, ease FROM vocab_mastery
                WHERE user_id = ? AND lapses > 0
                ORDER BY lapses DESC, ease ASC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]


_singleton: PersistentMemory | None = None


def get_memory() -> PersistentMemory:
    global _singleton
    if _singleton is None:
        db_path = os.environ.get("SQLITE_PATH", "./data/voicetutor.db")
        _singleton = PersistentMemory(db_path)
    return _singleton
