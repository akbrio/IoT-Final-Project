"""
Central configuration.

Everything reads from environment variables so you never have to edit code to
change the broker or credentials. The SENSORS table below is the single source
of truth for which values the dashboard tracks and where they come from.

TOPIC LAYOUT — one topic per sensor, each carrying a single plain number:
    gen/voltage     ->  "12.345"
    gen/current     ->  "250.500"
    gen/power       ->  "3.092"
    gen/vibration   ->  "9.811"

The "gen" prefix is set by MQTT_TOPIC_PREFIX (default "gen"). Change it in one
place and the dashboard re-subscribes accordingly — just keep the firmware's
topics matching.

`field = None` means "the whole payload IS the number" (as above). If you ever
switch a topic back to JSON, set `field` to the key to read (dotted paths OK).
"""
import os


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


# ---------------------------------------------------------------------------
# MQTT broker
# ---------------------------------------------------------------------------
MQTT_BROKER = _env("MQTT_BROKER", "16.16.143.50")
MQTT_PORT = int(_env("MQTT_PORT", "1883"))
MQTT_USERNAME = _env("MQTT_USERNAME", "akbar")
MQTT_PASSWORD = _env("MQTT_PASSWORD", "akbar2026")
MQTT_KEEPALIVE = int(_env("MQTT_KEEPALIVE", "60"))
MQTT_CLIENT_ID = _env("MQTT_CLIENT_ID", "iot-dashboard-backend")

# Topic prefix. With "gen", topics are gen/voltage, gen/current, etc.
MQTT_TOPIC_PREFIX = _env("MQTT_TOPIC_PREFIX", "gen")

# ---------------------------------------------------------------------------
# Sensors -> key : { topic, field, label, unit, color }
#   topic : MQTT topic this value arrives on
#   field : JSON key to read (dotted path allowed); None = whole payload is the number
# ---------------------------------------------------------------------------
SENSORS = {
    "voltage": {
        "topic": f"{MQTT_TOPIC_PREFIX}/voltage", "field": None,
        "label": "Voltage", "unit": "V", "color": "#ffb000",
    },
    "current": {
        "topic": f"{MQTT_TOPIC_PREFIX}/current", "field": None,
        "label": "Current", "unit": "mA", "color": "#22d3ee",
    },
    "power": {
        "topic": f"{MQTT_TOPIC_PREFIX}/power", "field": None,
        "label": "Power", "unit": "W", "color": "#4ade80",
    },
    "vibration": {
        "topic": f"{MQTT_TOPIC_PREFIX}/vibration", "field": None,
        # Firmware sends sqrt(ax^2+ay^2+az^2) -> acceleration magnitude in m/s^2
        # (includes gravity, so it idles near 9.8 at rest).
        "label": "Vibration", "unit": "m/s²", "color": "#f472b6",
    },
}

# topic -> [sensor keys on that topic]  (we subscribe once per distinct topic)
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
