"""Sugam web server: the ADK agent API + the custom UI, in one process.

We do NOT reimplement the agent runtime. `get_fast_api_app` gives us ADK's own
FastAPI app — sessions, `/run_sse` streaming, artifact storage — already wired to
the `app/` agent. We take that app, add the few endpoints the UI needs that ADK
has no opinion about, and serve the built React bundle from the same origin.

One process, one port, no Node in production, and no CORS in prod because the UI
and the API are same-origin.

    Dev :  uv run python -m app.server        (API on :8000)
           npm run dev  (in frontend/)        (UI on :5173, proxies to :8000)
    Prod:  npm run build  (in frontend/)  ->  frontend/dist
           uv run python -m app.server         serves UI + API on :8000

`web=False` disables ADK's own dev UI, so "/" is free for ours.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from pydantic import BaseModel

import app.security_events as security_events
import app.tts as tts_engine

load_dotenv()

_APP_DIR = Path(__file__).parent.resolve()          # .../sugam-form-filler/app
_PROJECT_ROOT = _APP_DIR.parent
_FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"

# ADK resolves a directory containing agent.py as a *single agent* whose name is
# the directory name — so pointing at `app/` yields app_name == "app". The UI
# sends that same name in every /run_sse call; APP_NAME is the single source of
# truth for it (also surfaced via /api/config so the client never hardcodes it).
APP_NAME = _APP_DIR.name

# Vite's dev server is a different origin, so it needs CORS. In production the UI
# is served from this very app and no cross-origin request ever happens.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Persist sessions to the same SQLite file the ADK CLI already uses, so a
# conversation started in `adk web` is still there in our UI, and vice versa.
_SESSION_DB = _APP_DIR / ".adk" / "session.db"
_SESSION_DB.parent.mkdir(parents=True, exist_ok=True)

adk_app = get_fast_api_app(
    agents_dir=str(_APP_DIR),
    session_service_uri=f"sqlite:///{_SESSION_DB.as_posix()}",
    allow_origins=_DEV_ORIGINS,
    web=False,  # no ADK dev UI — "/" belongs to our SPA
)


@adk_app.get("/api/config")
async def ui_config() -> dict:
    """Everything the client needs to boot. Keeps app_name out of the frontend."""
    return {
        "appName": APP_NAME,
        "model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "piiRedaction": True,
    }


class TtsRequest(BaseModel):
    text: str


@adk_app.post("/api/tts")
async def tts(req: TtsRequest) -> Response:
    """Speak text the browser has no voice for. See app/tts.py for why this exists.

    The client calls this ONLY when `speechSynthesis` has no voice matching the
    user's language — English and Hindi users never reach it. Results are cached
    server-side, so a repeated Listen press costs nothing.
    """
    try:
        # Blocking network + audio work: keep it off the event loop.
        wav = await asyncio.to_thread(tts_engine.synthesize, req.text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Surface quota exhaustion as 429 so the client can say "try again in a
        # minute" instead of hanging or failing silently.
        message = str(exc)
        status = 429 if ("429" in message or "RESOURCE_EXHAUSTED" in message) else 502
        raise HTTPException(status_code=status, detail=message) from exc

    return Response(
        content=wav,
        media_type="audio/wav",
        # Same text always yields the same audio, so let the browser reuse it too.
        headers={"Cache-Control": "public, max-age=86400"},
    )


@adk_app.get("/api/security")
async def security_feed(cursor: int = 0) -> dict:
    """Live feed of security-checkpoint activity for the trust panel.

    Polled with a cursor rather than streamed: these events are low-volume and
    arrive *between* model calls, so a second SSE connection racing the agent
    stream would buy nothing but complexity.
    """
    return security_events.snapshot(cursor)


# --------------------------------------------------------------------------- #
# Static SPA. Registered LAST so every ADK + /api route above wins the match;
# this mount only ever sees paths nothing else claimed.
# --------------------------------------------------------------------------- #
if _FRONTEND_DIST.is_dir():
    _assets = _FRONTEND_DIST / "assets"
    if _assets.is_dir():
        adk_app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    @adk_app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """Serve the SPA, falling back to index.html for client-side routes.

        A bare StaticFiles(html=True) mount would 404 on a deep link like
        /form/123; the SPA owns its routing, so unknown paths return the shell.
        """
        candidate = (_FRONTEND_DIST / full_path).resolve()
        # Containment check: never serve a path that escapes dist/ via traversal.
        if (
            full_path
            and _FRONTEND_DIST in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")


app = adk_app  # uvicorn entrypoint: `uvicorn app.server:app`


if __name__ == "__main__":
    import uvicorn

    if not _FRONTEND_DIST.is_dir():
        print(
            "\n  frontend/dist not found — serving the API only.\n"
            "  Run the UI in dev mode:  cd frontend && npm run dev\n"
            "  Or build it for prod:    cd frontend && npm run build\n"
        )

    uvicorn.run(
        "app.server:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,  # ADK spawns the MCP server as a subprocess; reload double-spawns it
    )
