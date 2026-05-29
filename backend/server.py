"""FastAPI server entrypoint.

Exposes:
  GET  /                 — health probe
  GET  /metrics          — rolling latency stats (P50/P95/max/mean)
  GET  /progress         — per-user progress, weak areas, due vocab
  GET  /curriculum       — lesson list
  WS   /ws               — voice channel: PCM audio in/out, JSON events
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .bot import LanguageTutorBot
from .curriculum.loader import CURRICULUM
from .memory.persistent import get_memory
from .observability.logger import init_logger, log
from .observability.metrics import METRICS
from .transports.websocket import build_transport

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
init_logger(LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log().info("voicetutor server starting")
    # Eagerly init the DB so the first WS connect doesn't pay schema init cost.
    get_memory()
    yield
    log().info("voicetutor server stopped")


app = FastAPI(title="VoiceTutor", version="0.1.0", lifespan=lifespan)

# Parse ALLOWED_ORIGINS from environment, default to "*" if not set
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
origins = [origin.strip() for origin in allowed_origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "voicetutor",
        "status": "ok",
        "target_lang": CURRICULUM.language,
        "lessons": [{"id": l.id, "title": l.title, "level": l.level} for l in CURRICULUM.all()],
    }


@app.get("/metrics")
async def metrics() -> dict[str, Any]:
    return METRICS.snapshot()


@app.get("/progress")
async def progress(user_id: str | None = None) -> dict[str, Any]:
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    mem = get_memory()
    return {
        "user_id": uid,
        "user": mem.get_user(uid),
        "progress": mem.get_progress(uid),
        "weak_areas": mem.weak_areas(uid),
        "due_vocab": mem.due_vocab(uid),
        "recent_mistakes": mem.recent_mistakes(uid),
    }


@app.get("/curriculum")
async def curriculum() -> dict[str, Any]:
    return {
        "language": CURRICULUM.language,
        "native_language": CURRICULUM.native_language,
        "lessons": [
            {
                "id": l.id,
                "title": l.title,
                "level": l.level,
                "estimated_minutes": l.estimated_minutes,
                "objective": l.objective,
                "vocab_count": len(l.vocabulary),
            }
            for l in CURRICULUM.all()
        ],
    }


@app.post("/reset_progress")
async def reset_progress(user_id: str | None = None) -> dict[str, Any]:
    """Full wipe — progress + vocab mastery + mistakes."""
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    res = get_memory().reset_user_progress(uid)
    return {"user_id": uid, "scope": "all", "deleted": res}


@app.post("/reset_lesson")
async def reset_lesson(lesson_id: str, user_id: str | None = None) -> dict[str, Any]:
    """Reset a specific lesson — progress + its mistakes only."""
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    res = get_memory().reset_lesson(uid, lesson_id)
    return {"user_id": uid, "lesson_id": lesson_id, "scope": "lesson", "deleted": res}


@app.post("/reset_weak_spots")
async def reset_weak_spots(user_id: str | None = None) -> dict[str, Any]:
    """Clear lapses + recent mistakes. Keeps mastery / reps / intervals.

    Useful for 'give me a fresh start on the words I struggle with' without
    losing what the learner has already learned correctly.
    """
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    res = get_memory().reset_weak_spots(uid)
    return {"user_id": uid, "scope": "weak_spots", "updated": res}


@app.get("/export_progress")
async def export_progress(user_id: str | None = None) -> dict[str, Any]:
    """Download the user's data — backup-before-reset use case."""
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    return get_memory().export_user_data(uid)


@app.get("/session_recovery")
async def session_recovery(user_id: str | None = None) -> dict[str, Any]:
    """Returns enough state for the client to know where the learner left off.

    Used at reconnect: the UI can show "Last time you were on Greetings —
    want to continue?" without needing the bot to recompute from raw history.
    """
    uid = user_id or os.environ.get("DEFAULT_USER_ID", "demo-user-001")
    mem = get_memory()
    prog = mem.get_progress(uid)
    in_progress = next((p for p in prog if p["status"] == "in_progress"), None)
    weak = mem.weak_areas(uid, limit=3)
    due = mem.due_vocab(uid, limit=5)
    return {
        "user_id": uid,
        "has_recent_session": bool(in_progress or weak or due),
        "in_progress_lesson": in_progress,
        "weak_words": [w["word"] for w in weak],
        "words_due": [d["word"] for d in due],
        "suggested_next": (
            f"Resume {in_progress['lesson_id']}" if in_progress
            else f"Review {due[0]['word']}" if due
            else "Start a new lesson"
        ),
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    """Detailed health probe — checks each external dependency is reachable.
    Used by ops / dashboards. Lightweight."""
    import time
    mem = get_memory()
    checks: dict[str, dict[str, Any]] = {}
    # DB ping
    t = time.time()
    try:
        mem.get_user(os.environ.get("DEFAULT_USER_ID", "demo-user-001"))
        checks["sqlite"] = {"ok": True, "latency_ms": int((time.time() - t) * 1000)}
    except Exception as e:
        checks["sqlite"] = {"ok": False, "error": str(e)}
    # Env-key presence (not values)
    for key in ("GROQ_API_KEY", "ASSEMBLYAI_API_KEY", "ELEVENLABS_API_KEY"):
        checks[key.lower()] = {"present": bool(os.environ.get(key))}
    return {"status": "ok" if all(c.get("ok", c.get("present", True)) for c in checks.values()) else "degraded",
            "checks": checks}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    log().info("WebSocket accepted")
    transport = build_transport(websocket)
    bot = LanguageTutorBot()
    try:
        await bot.run(transport)
    except WebSocketDisconnect:
        log().info("WebSocket disconnected")
    except Exception as e:
        log().exception(f"WS session crashed: {e}")
        try:
            import json
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Backend pipeline crash: {type(e).__name__} - {str(e)}"
            }))
        except Exception:
            pass
    finally:
        log().info("WS session ended")



from fastapi.responses import PlainTextResponse

@app.get("/logs")
async def get_logs():
    """Debug endpoint to fetch the latest backend logs."""
    try:
        with open("backend_debug.log", "r") as f:
            return PlainTextResponse(f.read()[-50000:])  # last 50KB
    except Exception as e:
        return PlainTextResponse(f"Error reading logs: {e}")

if __name__ == "__main__":
    import uvicorn


    uvicorn.run(
        "backend.server:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=LOG_LEVEL.lower(),
        reload=False,
    )
