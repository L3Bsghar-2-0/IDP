"""
DUM Relay — bridges the DUM streamer to the lumi-ui dashboard.

  POST /        <- streamer.py posts its JSON bundle here every ~2 s
  WS   /ws      <- lumi-ui opens a WebSocket and receives every bundle
  GET  /health  <- returns live / stale / down status

Run:
  python main.py

Env vars:
  RELAY_PORT          2400
  STALE_AFTER_SECS    10
  DOWN_AFTER_SECS     30
  CORS_ORIGINS        http://localhost:5173
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ── config ────────────────────────────────────────────────────────────────────

PORT         = int(os.environ.get("RELAY_PORT",        "3001"))
STALE_AFTER  = float(os.environ.get("STALE_AFTER_SECS", "10"))
DOWN_AFTER   = float(os.environ.get("DOWN_AFTER_SECS",  "30"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── payload model ─────────────────────────────────────────────────────────────

class DumBundle(BaseModel):
    source:     str            = "dum"
    fetched_at: str            = ""
    dum_url:    str            = ""
    records:    list[Any]      = Field(default_factory=list)
    summary:    dict[str, Any] = Field(default_factory=dict)
    forecast:   list[Any]      = Field(default_factory=list)

    model_config = {"extra": "allow"}

# ── state ─────────────────────────────────────────────────────────────────────

class _State:
    last_bundle:    DumBundle | None = None
    last_update_ts: float    | None = None
    clients:        list[WebSocket]  = []

    def relay_status(self) -> str:
        if self.last_update_ts is None:
            return "waiting"
        age = time.time() - self.last_update_ts
        if age > DOWN_AFTER:
            return "down"
        if age > STALE_AFTER:
            return "stale"
        return "live"

_state = _State()

# ── helpers ───────────────────────────────────────────────────────────────────

async def _broadcast(payload: dict) -> None:
    dead: list[WebSocket] = []
    for ws in list(_state.clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _state.clients.remove(ws)
        except ValueError:
            pass

def _envelope(bundle: DumBundle) -> dict:
    return {**bundle.model_dump(), "relay_status": _state.relay_status()}

# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="DUM Relay", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── routes ────────────────────────────────────────────────────────────────────

@app.post("/")
async def ingest(bundle: DumBundle) -> dict:
    """Receive a JSON bundle from streamer.py and push to all WS clients."""
    _state.last_bundle    = bundle
    _state.last_update_ts = time.time()
    await _broadcast(_envelope(bundle))
    logger.info(
        "relayed  records=%-4d  forecast=%-4d  clients=%d",
        len(bundle.records), len(bundle.forecast), len(_state.clients),
    )
    return {"ok": True, "clients_notified": len(_state.clients)}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """Dashboard subscribes here; receives every relayed bundle in real time."""
    await websocket.accept()
    _state.clients.append(websocket)
    logger.info("ws_connect   total=%d", len(_state.clients))

    # Send last known data immediately so the UI populates without waiting.
    if _state.last_bundle is not None:
        try:
            await websocket.send_json(_envelope(_state.last_bundle))
        except Exception:
            pass

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        try:
            _state.clients.remove(websocket)
        except ValueError:
            pass
        logger.info("ws_disconnect total=%d", len(_state.clients))


@app.get("/health")
async def health() -> dict:
    return {
        "relay_status":      _state.relay_status(),
        "clients_connected": len(_state.clients),
        "last_update_ts":    _state.last_update_ts,
        "stale_after_secs":  STALE_AFTER,
        "down_after_secs":   DOWN_AFTER,
    }


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("DUM Relay starting on port %d", PORT)
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, log_level="info")
