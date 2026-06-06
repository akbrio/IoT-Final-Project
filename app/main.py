"""
FastAPI application.

Responsibilities:
- On startup: open the DB, start the MQTT subscriber, remember the asyncio loop.
- Each incoming reading is stored AND broadcast to every connected browser over
  a WebSocket (real-time, no polling).
- REST endpoints serve the sensor metadata and historical data for the charts.
- A background task prunes old rows on a schedule.

The tricky part is that MQTT messages arrive on a *thread*, but WebSocket sends
must happen on the asyncio *loop*. We bridge the two with
`asyncio.run_coroutine_threadsafe`, scheduling the broadcast on the saved loop.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .database import Database
from .mqtt_client import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")

STATIC_DIR = __file__.rsplit("/", 1)[0] + "/static"

db = Database(config.DATABASE_PATH)


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)
        log.info("WebSocket connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)
        log.info("WebSocket disconnected (%d total)", len(self.active))

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------------------
# MQTT -> store + broadcast bridge (called from the MQTT thread)
# ---------------------------------------------------------------------------
def handle_reading(sensor: str, value: float, ts_ms: int) -> None:
    db.insert(sensor, value, ts_ms)
    message = {"sensor": sensor, "value": value, "ts": ts_ms}
    if _loop is not None:
        # Schedule the async broadcast onto the web server's event loop.
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), _loop)


mqtt_service = MQTTService(on_reading=handle_reading)


# ---------------------------------------------------------------------------
# Background pruning task
# ---------------------------------------------------------------------------
async def _prune_loop():
    while True:
        await asyncio.sleep(3600)  # hourly
        try:
            removed = db.prune(config.DATA_RETENTION_MINUTES)
            if removed:
                log.info("Pruned %d old rows", removed)
        except Exception:
            log.exception("Prune failed")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_running_loop()
    db.init()
    mqtt_service.start()
    prune_task = asyncio.create_task(_prune_loop())
    log.info("Startup complete")
    try:
        yield
    finally:
        prune_task.cancel()
        mqtt_service.stop()
        log.info("Shutdown complete")


app = FastAPI(title="IoT Sensor Dashboard", lifespan=lifespan)


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
@app.get("/api/sensors")
def get_sensors():
    """Metadata the frontend uses to build the cards and charts."""
    return [
        {
            "key": key,
            "label": meta["label"],
            "unit": meta["unit"],
            "color": meta["color"],
            "topic": meta["topic"],
        }
        for key, meta in config.SENSORS.items()
    ]


@app.get("/api/history")
def get_history(
    sensor: str = Query(..., description="sensor key, e.g. voltage"),
    minutes: int = Query(config.DEFAULT_WINDOW_MINUTES, ge=1, le=20000),
):
    if sensor not in config.SENSORS:
        raise HTTPException(status_code=404, detail="unknown sensor")
    points = db.history(sensor, minutes, config.MAX_HISTORY_POINTS)
    return {
        "sensor": sensor,
        "unit": config.SENSORS[sensor]["unit"],
        "minutes": minutes,
        "points": points,
    }


@app.get("/api/latest")
def get_latest():
    """Most recent value for every sensor (used to fill the big number cards)."""
    out = {}
    for key in config.SENSORS:
        out[key] = db.latest(key)
    return out


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # We don't expect messages from the client; this keeps the socket
            # open and detects disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Static dashboard
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR + "/index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
