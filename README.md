# GENSET Telemetry — IoT Sensor Dashboard

Real-time web dashboard for generator sensor data. It subscribes to your MQTT
broker, stores readings in SQLite, and streams them live to a browser dashboard
over WebSockets.

```
Wemos D1 mini ──► MQTT broker ──► [ this app ] ──► SQLite (history)
 (INA219, MPU6050)                      │
                                        └────► WebSocket ──► Dashboard (charts)
```

You already have the hardware → MQTT half working. **This repo is the
subscribe + store + visualise half.**

## What's inside

```
iot-dashboard/
├── README.md
├── Dockerfile                  # builds the app image
├── docker-compose.yml          # runs the app (port 8000)
├── docker-compose.caddy.yml    # OPTIONAL: adds HTTPS via Caddy on your domain
├── requirements.txt
├── .env.example                # copy to .env (broker, credentials, topics)
├── caddy/
│   └── Caddyfile               # reverse-proxy + auto-HTTPS config
└── app/
    ├── main.py                 # FastAPI app, REST API, WebSocket, MQTT→WS bridge
    ├── config.py               # ALL settings + the sensor/topic table
    ├── mqtt_client.py          # subscribes to the broker, parses payloads
    ├── database.py             # SQLite time-series storage
    ├── models.py               # API response models
    └── static/                 # the dashboard (HTML/CSS/JS, Chart.js)
        ├── index.html
        ├── style.css
        └── app.js
```

## Quick start (Docker — recommended)

On your Ubuntu server:

```bash
git clone <your-repo-url> iot-dashboard   # or copy the folder over
cd iot-dashboard

cp .env.example .env          # defaults already match your broker
docker compose up -d --build
```

Open **http://YOUR_SERVER_IP:8000** — the dashboard appears, and as your Wemos
publishes to `akbar/voltage`, `akbar/current`, `akbar/power`, `akbar/vibration`,
the charts fill in live.

```bash
docker compose logs -f        # watch MQTT connect + subscribe messages
docker compose down           # stop
```

## Add HTTPS on akbar.serveblog.net (optional)

Make sure your domain's **A record points to this server's public IP**, then:

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

Caddy automatically obtains a free Let's Encrypt certificate. Your dashboard is
then at **https://akbar.serveblog.net** (WebSockets are proxied automatically).

## Run without Docker (for quick local testing)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env.example | xargs)   # load settings
export DATABASE_PATH=./data/sensors.db
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Configuration

Everything is in **`.env`** (or environment variables). No code editing needed
to change the broker, credentials, retention, or topics. See `.env.example`.

### Payload format — matches the Wemos firmware
The firmware publishes ONE combined JSON message to ONE topic (`akbar`):

    {"volatge":12.3,"cuurent":250.5,"power":3.1,"accel":{"x":..,"y":..,"z":..},"vibration":9.8}

`app/config.py` maps each sensor to the JSON `field` it reads from that message
(including the firmware's `volatge` / `cuurent` spellings). To add the raw accel
axes as their own charts, uncomment the `accel_x/y/z` entries in `config.py`.
If you fix the firmware key spellings, update the matching `field` values too.

### Adding a 5th sensor later
Add one entry to the `SENSORS` dict in `app/config.py` (key, topic, label, unit,
color). The API, WebSocket, and dashboard all rebuild themselves from it — no
other changes required.

## API reference

| Method | Path                                   | Purpose                          |
|--------|----------------------------------------|----------------------------------|
| GET    | `/`                                    | The dashboard                    |
| GET    | `/api/sensors`                         | Sensor metadata (labels/units)   |
| GET    | `/api/history?sensor=voltage&minutes=5`| Historical points for one sensor |
| GET    | `/api/latest`                          | Newest value per sensor          |
| WS     | `/ws`                                  | Live readings stream             |
| GET    | `/healthz`                             | Health check                     |
| GET    | `/docs`                                | Auto-generated API docs          |

## Notes
- History persists across restarts (stored in a Docker volume `sensor-data`).
- Old rows are pruned automatically (default retention: 10 days, configurable).
- The dashboard has a window selector: 5m / 30m / 1h / 12h / 1d / 10d.
