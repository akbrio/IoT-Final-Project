"""
Central configuration.

Everything reads from environment variables so you never have to edit code to
change the broker or credentials. The SENSORS table below is the single source
of truth for which values the dashboard tracks and where they come from.

IMPORTANT — this matches your Wemos firmware exactly:
Your firmware publishes ONE combined JSON message to ONE topic ("akbar"):

    {"volatge":..., "cuurent":..., "power":..., "accel":{...}, "vibration":...}

So each sensor below points at the same topic and names the JSON `field` to
read from that message. The `field` values MUST match the JSON keys your
firmware publishes — if you rename a key in the firmware, rename it here too.

A `field` may use a dotted path for nested JSON, e.g. "accel.x".
If `field` is None, the whole payload is treated as a single number
(the simpler "one value per topic" style).
"""
import os


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# MQTT broker
# ---------------------------------------------------------------------------
MQTT_BROKER = _env("MQTT_BROKER", "16.16.253.191")
MQTT_PORT = int(_env("MQTT_PORT", "1883"))
MQTT_USERNAME = _env("MQTT_USERNAME", "akbar")
MQTT_PASSWORD = _env("MQTT_PASSWORD", "akbar2026")
MQTT_KEEPALIVE = int(_env("MQTT_KEEPALIVE", "60"))
MQTT_CLIENT_ID = _env("MQTT_CLIENT_ID", "iot-dashboard-backend")

# The single topic your Wemos publishes to.
MQTT_DATA_TOPIC = _env("MQTT_DATA_TOPIC", "akbar")

# ---------------------------------------------------------------------------
# Sensors -> key : { topic, field, label, unit, color }
#   topic : MQTT topic the value arrives on
#   field : JSON key within the message (dotted path allowed; None = raw number)
# ---------------------------------------------------------------------------
SENSORS = {
    "voltage": {
        "topic": MQTT_DATA_TOPIC, "field": "voltage",
        "label": "Voltage", "unit": "V", "color": "#ffb000",
    },
    "current": {
        "topic": MQTT_DATA_TOPIC, "field": "current",
        "label": "Current", "unit": "mA", "color": "#22d3ee",
    },
    "power": {
        "topic": MQTT_DATA_TOPIC, "field": "power",
        "label": "Power", "unit": "W", "color": "#4ade80",
    },
    "vibration": {
        "topic": MQTT_DATA_TOPIC, "field": "vibration",
        # Firmware sends sqrt(ax^2+ay^2+az^2) -> acceleration magnitude in m/s^2
        # (it includes gravity, so it idles near 9.8). See note in the chat.
        "label": "Vibration", "unit": "m/s²", "color": "#f472b6",
    },
    # --- Optional: uncomment to also chart the raw accelerometer axes ---
    # "accel_x": {"topic": MQTT_DATA_TOPIC, "field": "accel.x",
    #             "label": "Accel X", "unit": "m/s²", "color": "#a78bfa"},
    # "accel_y": {"topic": MQTT_DATA_TOPIC, "field": "accel.y",
    #             "label": "Accel Y", "unit": "m/s²", "color": "#60a5fa"},
    # "accel_z": {"topic": MQTT_DATA_TOPIC, "field": "accel.z",
    #             "label": "Accel Z", "unit": "m/s²", "color": "#34d399"},
}

# topic -> [sensor keys on that topic]  (so we subscribe once per distinct topic)
TOPIC_SENSORS: dict[str, list[str]] = {}
for _key, _meta in SENSORS.items():
    TOPIC_SENSORS.setdefault(_meta["topic"], []).append(_key)

# ---------------------------------------------------------------------------
# Database / retention
# ---------------------------------------------------------------------------
DATABASE_PATH = _env("DATABASE_PATH", "/data/sensors.db")
DATA_RETENTION_MINUTES = int(_env("DATA_RETENTION_MINUTES", "14400"))  # 10 days
DEFAULT_WINDOW_MINUTES = int(_env("DEFAULT_WINDOW_MINUTES", "5"))
MAX_HISTORY_POINTS = int(_env("MAX_HISTORY_POINTS", "2000"))
