-- VoiceTutor SQLite schema
-- Single-file persistent memory for per-user progress.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  native_lang   TEXT NOT NULL DEFAULT 'en',
  target_lang   TEXT NOT NULL DEFAULT 'es',
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS progress (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       TEXT NOT NULL,
  lesson_id     TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'in_progress',
  score         REAL NOT NULL DEFAULT 0.0,
  attempts      INTEGER NOT NULL DEFAULT 0,
  completed_at  TEXT,
  updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id),
  UNIQUE (user_id, lesson_id)
);

-- FSRS-lite spaced repetition table.
CREATE TABLE IF NOT EXISTS vocab_mastery (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         TEXT NOT NULL,
  word            TEXT NOT NULL,
  lang            TEXT NOT NULL,
  ease            REAL NOT NULL DEFAULT 2.5,
  interval_days   REAL NOT NULL DEFAULT 1.0,
  reps            INTEGER NOT NULL DEFAULT 0,
  lapses          INTEGER NOT NULL DEFAULT 0,
  last_review_at  TEXT,
  next_review_at  TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id),
  UNIQUE (user_id, word, lang)
);

CREATE INDEX IF NOT EXISTS idx_vocab_due ON vocab_mastery(user_id, next_review_at);

CREATE TABLE IF NOT EXISTS mistakes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     TEXT NOT NULL,
  lesson_id   TEXT,
  kind        TEXT NOT NULL,
  expected    TEXT,
  got         TEXT,
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_mistakes_user ON mistakes(user_id, created_at DESC);
