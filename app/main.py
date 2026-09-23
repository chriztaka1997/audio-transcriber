import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .database import Database
from .queue_manager import QueueManager
from .routes import router
from .ws import WebSocketManager

import os

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db = Database()
    await db.init()
    ws_manager = WebSocketManager()
    qm = QueueManager(db, ws_manager)
    app.state.db = db
    app.state.ws_manager = ws_manager
    app.state.queue_manager = qm
    await qm.resume_jobs()
    yield
    # Shutdown — nothing to clean up


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    ws_manager: WebSocketManager = app.state.ws_manager
    await ws_manager.connect(ws)

    # Send current state of all jobs on connect
    qm: QueueManager = app.state.queue_manager
    jobs = await qm.get_all_jobs()
    for job in jobs:
        try:
            await ws.send_text(json.dumps({
                "type": "job_update",
                "job": job.model_dump(),
            }, default=str))
        except Exception:
            break

    try:
        while True:
            # Keep connection alive, we don't expect client messages
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception:
        ws_manager.disconnect(ws)


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# Mount static files for CSS/JS (after explicit routes so /api and /ws take priority)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
