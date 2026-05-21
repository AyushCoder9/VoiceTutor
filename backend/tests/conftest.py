"""pytest setup — make repo root importable as `backend.*`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# `backend/` is one level up; add the project root so `import backend.…` works.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Use a throwaway DB per test session.
os.environ.setdefault("SQLITE_PATH", str(ROOT / "backend" / "tests" / ".tmp-test.db"))
