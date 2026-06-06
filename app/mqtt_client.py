"""
MQTT subscriber.

Connects to your Mosquitto broker, subscribes once to each distinct topic in
config.TOPIC_SENSORS, and for every message extracts each sensor's value from
the (possibly combined) JSON payload, then hands each reading to a callback.

Matches your Wemos firmware: one JSON message on topic "akbar" carrying all the
values. For each sensor on a topic we read its configured `field` from the JSON
(supports dotted paths like "accel.x"). If `field` is None we treat the whole
payload as a single number instead.

Design notes:
- connect_async + loop_start => the web server starts instantly even if the
  broker is briefly unreachable; paho retries on its own.
- Parsing is forgiving: missing/garbage fields are skipped, not fatal.
"""
import json
import logging
import time
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from . import config

log = logging.getLogger("mqtt")

# on_reading(sensor_key: str, value: float, ts_ms: int)
ReadingCallback = Callable[[str, float, int], None]


def _to_float(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _lookup(data: dict, path: str) -> Optional[float]:
    """Read a (possibly dotted) field path from a parsed JSON dict."""
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return _to_float(cur)


def extract_values(raw: bytes, sensor_keys: list[str]) -> list[tuple[str, float]]:
    """Return [(sensor_key, value), ...] extracted from one MQTT message."""
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return []

    # Parse JSON once (the common case for your firmware).
    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    out: list[tuple[str, float]] = []
    for key in sensor_keys:
        field = config.SENSORS[key]["field"]

        if field is None:
            # whole payload is a single number (e.g. "12.5")
            v = _to_float(text)
            if v is None and isinstance(data, (int, float)):
                v = float(data)
        elif isinstance(data, dict):
            v = _lookup(data, field)
        else:
            v = None

        if v is not None:
            out.append((key, v))

    if not out:
        log.warning("No usable values in payload: %r", text[:120])
    return out


class MQTTService:
    def __init__(self, on_reading: ReadingCallback):
        self._on_reading = on_reading
        self._client = mqtt.Client(
            client_id=config.MQTT_CLIENT_ID, clean_session=True
        )
        if config.MQTT_USERNAME:
            self._client.username_pw_set(
                config.MQTT_USERNAME, config.MQTT_PASSWORD
            )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)

    def start(self) -> None:
        log.info("Connecting to MQTT %s:%s", config.MQTT_BROKER, config.MQTT_PORT)
        self._client.connect_async(
            config.MQTT_BROKER, config.MQTT_PORT, config.MQTT_KEEPALIVE
        )
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("MQTT connected")
            for topic in config.TOPIC_SENSORS:
                client.subscribe(topic, qos=0)
                log.info("Subscribed to %s", topic)
        else:
            log.error("MQTT connect failed (rc=%s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            log.warning("MQTT disconnected unexpectedly (rc=%s); reconnecting", rc)

    def _on_message(self, client, userdata, msg):
        sensor_keys = config.TOPIC_SENSORS.get(msg.topic)
        if not sensor_keys:
            return
        ts_ms = int(time.time() * 1000)
        for key, value in extract_values(msg.payload, sensor_keys):
            try:
                self._on_reading(key, value, ts_ms)
            except Exception:
                log.exception("on_reading callback failed")
