"""
SQLite storage for time-series sensor readings.

Why it's written this way:
- The MQTT client runs in its own thread; the web server reads on the asyncio
  loop. SQLite connections cannot be shared across threads, so each call opens
  its own short-lived connection. For this write volume that is perfectly fine.
- WAL mode lets reads and writes happen concurrently without locking errors.
- Timestamps are stored as epoch milliseconds (INTEGER) which sorts/filters
  fast and is exactly what the charting library wants on the frontend.
"""
import os
import sqlite3
import threading
import time

# Serialise writes from the MQTT thread to avoid rare "database is locked"
# hiccups under bursty publishing.
_write_lock = threading.Lock()


class Database:
    def __init__(self, path: str):
        self.path = path

    # -- connection helper --------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # -- schema -------------------------------------------------------------
    def init(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id     INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor TEXT    NOT NULL,
                    value  REAL    NOT NULL,
                    ts     INTEGER NOT NULL          -- epoch milliseconds, UTC
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sensor_ts ON readings (sensor, ts)"
            )
            conn.commit()
        finally:
            conn.close()

    # -- writes -------------------------------------------------------------
    def insert(self, sensor: str, value: float, ts_ms: int) -> None:
        with _write_lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO readings (sensor, value, ts) VALUES (?, ?, ?)",
                    (sensor, value, ts_ms),
                )
                conn.commit()
            finally:
                conn.close()

    def prune(self, retention_minutes: int) -> int:
        """Delete rows older than the retention window. Returns rows removed."""
        cutoff = int(time.time() * 1000) - retention_minutes * 60 * 1000
        with _write_lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    # -- reads --------------------------------------------------------------
    def history(self, sensor: str, minutes: int, max_points: int) -> list[dict]:
        """Return readings for `sensor` over the last `minutes`, ascending.

        If the window contains more rows than `max_points`, evenly down-sample
        so the browser receives a manageable number of points.
        """
        cutoff = int(time.time() * 1000) - minutes * 60 * 1000
        conn = self._connect()
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM readings WHERE sensor = ? AND ts >= ?",
                (sensor, cutoff),
            ).fetchone()[0]

            if count == 0:
                return []

            # ceil division guarantees the result never exceeds max_points
            step = max(1, -(-count // max_points))
            if step == 1:
                rows = conn.execute(
                    "SELECT ts, value FROM readings "
                    "WHERE sensor = ? AND ts >= ? ORDER BY ts ASC",
                    (sensor, cutoff),
                ).fetchall()
            else:
                # Keep every `step`-th row using the row number within the window.
                rows = conn.execute(
                    """
                    SELECT ts, value FROM (
                        SELECT ts, value,
                               ROW_NUMBER() OVER (ORDER BY ts ASC) AS rn
                        FROM readings
                        WHERE sensor = ? AND ts >= ?
                    )
                    WHERE rn % ? = 0
                    ORDER BY ts ASC
                    """,
                    (sensor, cutoff, step),
                ).fetchall()

            return [{"sensor": sensor, "ts": int(ts), "value": float(v)}
                    for ts, v in rows]
        finally:
            conn.close()

    def latest(self, sensor: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT ts, value FROM readings WHERE sensor = ? "
                "ORDER BY ts DESC LIMIT 1",
                (sensor,),
            ).fetchone()
            if row is None:
                return None
            return {"sensor": sensor, "ts": int(row[0]), "value": float(row[1])}
        finally:
            conn.close()
