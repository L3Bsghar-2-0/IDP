# 🚀 Full Execution Pipeline — STM32 → HiveMQ → Server

> ⚠️ **CRITICAL TERMINOLOGY MISMATCH** ⚠️
>
> The task brief asks for an **STM32** runbook, but the firmware that actually
> exists in this repository is for an **ESP32** (PlatformIO + Arduino-ESP32,
> see `esp32-edge/platformio.ini`). There is **no STM32 source**, **no
> CubeMX project**, **no `.ioc` file**, and **no STM32 HAL code anywhere in
> the tree**.
>
> This runbook documents the **real, working ESP32 → HiveMQ → FastAPI
> pipeline** as it exists today. If you genuinely need an STM32 build,
> a separate firmware port is required — see "Optional STM32 Port" notes
> at the end of each firmware section.

---

## 📋 PHASE 1 — Project Scan Summary

### 1. Firmware (`esp32-edge/`)

| Item | Value |
|---|---|
| MCU | **ESP32** (board `esp32dev`) — *not STM32* |
| Build system | PlatformIO, `platform = espressif32 @ ~6.7.0`, `framework = arduino` |
| MQTT library | **PubSubClient 2.8** (`knolleary/PubSubClient`) |
| TLS layer | `WiFiClientSecure` (mbedTLS via Arduino-ESP32) — root CA pinned in `config.h` (Let's Encrypt **ISRG Root X1**) |
| Transport | Wi‑Fi STA mode (no Ethernet, no GSM) |
| JSON | `bblanchon/ArduinoJson 7.x` |
| BLE provisioning | `NimBLE-Arduino 1.4.x` (`blesvc.cpp`) |
| Sensors | DHT22 on GPIO 4, MQ-2 on GPIO 34 (12-bit ADC) |
| Offline buffer | LittleFS (`buffer.cpp`) — replays after reconnect |
| Watchdog | `esp_task_wdt`, 30 s timeout |

**Topics published** (all built in `mqttmgr.cpp::buildTopics`):
```
tenants/<TENANT>/sites/<SITE>/devices/<clientId>/sensors/dht22/telemetry
tenants/<TENANT>/sites/<SITE>/devices/<clientId>/sensors/mq2/telemetry
tenants/<TENANT>/sites/<SITE>/devices/<clientId>/status            (LWT, retained)
tenants/<TENANT>/sites/<SITE>/devices/<clientId>/diagnostics
```
- `<TENANT>` = `demo`, `<SITE>` = `lab` (set in `config.h`)
- `<clientId>` is auto-derived from the MAC: `esp32-aabbccddeeff`
- All publishes are **QoS 1**, JSON payloads following schema v1.

**Broker target (firmware)** — from `config.h`:
| Field | Value |
|---|---|
| `MQTT_HOST` | `e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud` |
| `MQTT_PORT` | `8883` (TCP / TLS) |
| `MQTT_USERNAME` | `PLACEHOLDER_DEVICE_USERNAME` ⚠️ **must be set** |
| `MQTT_PASSWORD` | `PLACEHOLDER_DEVICE_PASSWORD` ⚠️ **must be set** |
| `WIFI_SSID/PASSWORD` | placeholders ⚠️ — overridable at runtime via NVS / BLE |
| TLS | yes (CA-only, no mTLS) |

### 2. HiveMQ Broker

| Item | Value |
|---|---|
| Type | **HiveMQ Cloud** (managed, no self-hosted broker config in repo) |
| Hostname | `e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud` |
| Ports in use | `8883` (MQTT-over-TLS, used by ESP32 + Python server). `8884` reserved for WebSocket per `config.h` comment |
| Auth | username + password (no client certs) |
| TLS | mandatory; broker cert chains to **ISRG Root X1** |
| Existing accounts | `python-server / Python-server5` (server subscriber, in `.env`) — device account placeholder |
| ACLs | not in repo (managed via HiveMQ Cloud dashboard) |

### 3. Backend Server (`reteqfusion-server/`)

| Item | Value |
|---|---|
| Language | **Python 3.12** (slim image) |
| Framework | **FastAPI 0.115** + Uvicorn |
| MQTT client | **paho-mqtt 2.1** (CallbackAPIVersion v2, MQTTv3.1.1, background thread, asyncio bridge via `asyncio.Queue`) |
| Topic subscriptions | the four telemetry / status / diagnostics wildcards above (QoS 1) |
| Validation | Pydantic v2 models (`telemetry.py`, `status.py`, `diagnostics.py`) |
| DB | **TimescaleDB on PostgreSQL 16** (`timescale/timescaledb:latest-pg16`), accessed via `asyncpg 0.29` |
| Migrations | `app/storage/migrations.py` runs `sql/001_init.sql` → `002_aggregates.sql` → `003_retention.sql` at startup |
| Tables | `telemetry` (hypertable), `dlq`, plus device + status tables |
| REST API | `/health`, `/api/v1/devices`, `/api/v1/sensors`, `/api/v1/events` on **port 8000** |
| Background tasks | MQTT consumer loop, `AlertingService` (publishes alarms back to MQTT) |
| LWT | `servers/<client_id>/status` retained `{"status":"offline",...}` |

### 4. Docker / Infrastructure (`reteqfusion-server/`)

`docker-compose.yml` already defines three services on the `reteq-net` bridge network:

| Service | Image | Ports | Volumes | Healthcheck |
|---|---|---|---|---|
| `app` (reteqfusion-app) | built from local `Dockerfile` | `8000:8000` | none | curl `/health` |
| `timescaledb` | `timescale/timescaledb:latest-pg16` | `5432:5432` | `timescaledb_data` | `pg_isready` |
| `grafana` | `grafana/grafana:latest` | `3000:3000` | `grafana_data`, `./grafana/provisioning`, `./grafana/grafana.ini` | none |

`Dockerfile` is a clean Python 3.12-slim image installing `requirements.txt` and running `uvicorn app.main:app`.

### 5. Dependencies & Config

**Firmware libs** (PlatformIO `lib_deps`):
```
bblanchon/ArduinoJson @ ^7.0.4
knolleary/PubSubClient @ ^2.8
adafruit/DHT sensor library @ ^1.4.6
adafruit/Adafruit Unified Sensor @ ^1.1.14
h2zero/NimBLE-Arduino @ ^1.4.1
```

**Server libs** (`reteqfusion-server/requirements.txt`):
```
paho-mqtt==2.1.0    fastapi==0.115.0    uvicorn[standard]==0.30.0
pydantic==2.7.0     pydantic-settings==2.3.0    asyncpg==0.29.0
numpy==1.26.4       python-dateutil==2.9.0       httpx==0.27.0
pytest==8.2.0       pytest-asyncio==0.23.7
```

**Required config files (must exist before `docker compose up`)**
| File | Status | Notes |
|---|---|---|
| `reteqfusion-server/.env` | ✅ present | broker creds + DB password — **rotate before any non-dev use** |
| `reteqfusion-server/.env.example` | ✅ present | template |
| `reteqfusion-server/grafana/grafana.ini` | ✅ present | provisioned dashboard path |
| `reteqfusion-server/grafana/provisioning/datasources/timescaledb.yaml` | ✅ present | |
| `reteqfusion-server/grafana/provisioning/dashboards/iot_overview.json` | ✅ present | |
| `reteqfusion-server/sql/00{1,2,3}_*.sql` | ✅ present | applied at startup |
| `esp32-edge/src/config.local.h` | ❌ missing (gitignored) | optional override; otherwise edit `config.h` directly |

**Hardcoded values that MUST be changed**
- ⚠️ `esp32-edge/src/config.h`: `WIFI_SSID`, `WIFI_PASSWORD`, `MQTT_USERNAME`, `MQTT_PASSWORD` are placeholders.
- ⚠️ `reteqfusion-server/.env`: real broker password is committed (`Python-server5`) — rotate.
- ⚠️ `POSTGRES_PASSWORD=reteq_secret_2025` and `GRAFANA_ADMIN_PASSWORD=reteq_grafana_2025` in `.env` — change for any deployed environment.

---

## ✅ Prerequisites

Install the following tools on your workstation:

| Tool | Why | Install |
|---|---|---|
| **Docker Desktop ≥ 4.30** (or Docker Engine + Compose v2) | run backend stack | <https://www.docker.com/products/docker-desktop/> |
| **Git** | clone repo | `winget install Git.Git` / `apt install git` |
| **Python 3.11+** | run captor-simulator and the live subscriber | python.org or `winget install Python.Python.3.13` |
| **PlatformIO Core** (or VS Code + PlatformIO extension) | build/flash ESP32 firmware | `pip install platformio` |
| **USB-to-UART driver** (CP210x or CH340) | flash + serial-monitor ESP32 | Silabs / WCH website |
| **mosquitto-clients** (`mosquitto_pub`, `mosquitto_sub`) | end-to-end test publishes | `winget install EclipseFoundation.Mosquitto` / `apt install mosquitto-clients` |
| **psql** (PostgreSQL client) — *optional* | inspect TimescaleDB rows | `apt install postgresql-client` |
| **openssl** — *only if generating your own certs* | TLS debugging | `apt install openssl` (already on macOS) |

Accounts / services:

| Service | Why | URL |
|---|---|---|
| **HiveMQ Cloud** account (Free tier OK) | the MQTT broker | <https://console.hivemq.cloud/> |

> ℹ️ STM32CubeIDE / OpenOCD / ST-Link tools are **NOT required** because no
> STM32 firmware exists in this repo. They would only be needed if you
> port the firmware (see "Optional STM32 Port" sections below).

---

## 📁 Step 1 — Repository & File Setup

### 1.1 Clone

```powershell
# PowerShell on Windows (this repo is at C:\IDP)
git clone <your-fork-url> C:\IDP
cd C:\IDP
git checkout esp32   # active branch where ESP32 firmware lives
```

### 1.2 Project layout (after clone)

```
IDP/
├── esp32-edge/             ← ESP32 firmware (PlatformIO)
│   ├── platformio.ini
│   └── src/                ← main.cpp, mqttmgr.cpp, sensor_*.cpp, config.h ...
├── reteqfusion-server/     ← FastAPI backend + Docker stack
│   ├── app/                ← Python source (mqtt, processing, storage, api ...)
│   ├── sql/                ← TimescaleDB migrations
│   ├── grafana/            ← provisioning + dashboards
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── .env                ← runtime secrets (gitignored)
│   └── .env.example
├── reteqfusion-live/       ← lightweight CLI subscriber for live debugging
└── captor-simulator/       ← Python sensor simulator (use instead of hardware)
```

### 1.3 Create `reteqfusion-server/.env`

If `.env` is missing, copy from the template:

```powershell
cd C:\IDP\reteqfusion-server
Copy-Item .env.example .env
```

Then edit `.env` with the **complete** template below — every variable below is consumed by `app/config.py` and/or `docker-compose.yml`:

```dotenv
# ── MQTT (HiveMQ Cloud) ────────────────────────────────────────────
MQTT_HOST=e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=python-server
MQTT_PASSWORD=Python-server5            # ← rotate for production
MQTT_CLIENT_ID=reteqfusion-server-01
MQTT_TLS=true
MQTT_KEEPALIVE=60

# ── TimescaleDB ────────────────────────────────────────────────────
POSTGRES_HOST=timescaledb               # service name on reteq-net
POSTGRES_PORT=5432
POSTGRES_DB=reteqfusion
POSTGRES_USER=reteq
POSTGRES_PASSWORD=reteq_secret_2025     # ← rotate for production
DATABASE_URL=postgresql://reteq:reteq_secret_2025@timescaledb:5432/reteqfusion

# ── Grafana ────────────────────────────────────────────────────────
GRAFANA_ADMIN_PASSWORD=reteq_grafana_2025

# ── App ────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
API_PORT=8000

# ── MQ-2 thresholds (ppm) ──────────────────────────────────────────
MQ2_SMOKE_ALARM_PPM=1000
MQ2_HAZARD_PPM=3000
```

> ⚠️ **WARNING — secret rotation**: `DATABASE_URL` embeds `POSTGRES_PASSWORD`.
> If you change one, change both. The string is parsed by asyncpg, not
> recombined from parts.

### 1.4 Create `esp32-edge/src/config.local.h` (optional override)

`config.h` includes `config.local.h` if you create one (the file is gitignored,
keeping real credentials out of version control):

```cpp
// esp32-edge/src/config.local.h — gitignored, edit at will
#pragma once

#undef  WIFI_SSID
#define WIFI_SSID     "MyHomeWifi"

#undef  WIFI_PASSWORD
#define WIFI_PASSWORD "supersecret"

#undef  MQTT_USERNAME
#define MQTT_USERNAME "esp32-device"

#undef  MQTT_PASSWORD
#define MQTT_PASSWORD "Esp32-device"

// Optionally pin a fixed client id (otherwise derived from MAC):
// #define CLIENT_ID_OVERRIDE "esp32-test-01"
```

> ⚠️ **WARNING**: `config.h` does **not** currently `#include "config.local.h"`.
> If you choose this path, add `#include "config.local.h"` at the bottom of
> `config.h` (guarded by `#if __has_include(...)`), or just edit `config.h`
> directly. The cleaner long-term solution is `#if __has_include("config.local.h")`.

---

## 🔐 Step 2 — TLS / Certificates Setup

This pipeline uses **broker-only TLS (no client certificates)**. Authentication is by username + password over an encrypted channel.

### 2.1 Server side (Python backend)

`app/mqtt/client.py` calls `ssl.create_default_context()`, which loads the
**system root CA bundle** (provided by the `ca-certificates` package
already installed in the `Dockerfile`):

```dockerfile
RUN apt-get install -y --no-install-recommends gcc libc6-dev ca-certificates
```

Nothing else to do server-side. HiveMQ Cloud's certificate chains to public
roots already trusted by the system bundle.

### 2.2 Firmware side (ESP32)

The ESP32 cannot rely on a system CA store, so the **ISRG Root X1** PEM is
hard-coded into `esp32-edge/src/config.h` (`BROKER_CA_PEM`) and loaded with:

```cpp
s_tls.setCACert(BROKER_CA_PEM);
```

If HiveMQ migrates to a different root, replace the PEM block in `config.h`. Fetch the current chain with:

```powershell
openssl s_client -showcerts -servername e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud `
  -connect e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud:8883 < $null
```

Copy the **last** `-----BEGIN CERTIFICATE-----` block (the root) into `BROKER_CA_PEM`.

### 2.3 Optional: time sync

TLS validation requires a correct clock. The ESP32 calls SNTP from `netmgr.cpp`
on boot (`pool.ntp.org`) — no manual setup needed. If your network blocks NTP,
override the server in `netmgr.cpp` or pre-set the RTC.

---

## 🐳 Step 3 — Docker Build & Compose

### 3.1 The `docker-compose.yml` already in the repo (verbatim, complete)

> File: `reteqfusion-server/docker-compose.yml`

```yaml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: reteqfusion-app
    depends_on:
      timescaledb:
        condition: service_healthy
      grafana:
        condition: service_started
    env_file:
      - .env
    ports:
      - "8000:8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 20s
    networks:
      - reteq-net

  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: reteqfusion-timescaledb
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - timescaledb_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 10
    networks:
      - reteq-net

  grafana:
    image: grafana/grafana:latest
    container_name: reteqfusion-grafana
    depends_on:
      timescaledb:
        condition: service_healthy
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/grafana.ini:/etc/grafana/grafana.ini
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD}
      GF_INSTALL_PLUGINS: grafana-clock-panel,grafana-simple-json-datasource
      GF_USERS_ALLOW_SIGN_UP: "false"
    restart: unless-stopped
    networks:
      - reteq-net

volumes:
  timescaledb_data:
  grafana_data:

networks:
  reteq-net:
    driver: bridge
```

### 3.2 The `Dockerfile` (verbatim, complete)

> File: `reteqfusion-server/Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app/ /app/app/
COPY sql/ /app/sql/
COPY tests/ /app/tests/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.3 Build & run

```powershell
cd C:\IDP\reteqfusion-server

# Build all images (the app image is built from local Dockerfile)
docker compose build

# Start the full stack in the background
docker compose up -d

# Tail logs to confirm startup
docker compose logs -f app
```

Healthchecks ensure the order is `timescaledb (healthy) → app (starting) → app (healthy)`. You should see, in order:

```
reteqfusion-timescaledb | database system is ready to accept connections
reteqfusion-grafana     | HTTP Server Listen ... address=[::]:3000
reteqfusion-app         | INFO  application_starting  version=1.0.0
reteqfusion-app         | INFO  mqtt_connected
reteqfusion-app         | INFO  application_ready
```

### 3.4 Network & volume map

| Object | Type | Used by | Notes |
|---|---|---|---|
| `reteq-net` | bridge network | all 3 services | inter-container DNS (e.g. `timescaledb:5432`) |
| `timescaledb_data` | named volume | `timescaledb` | survives container recreate; **delete to wipe** |
| `grafana_data` | named volume | `grafana` | dashboards & users |

### 3.5 Tear-down / reset

```powershell
docker compose down                   # stop, keep volumes
docker compose down --volumes         # stop AND wipe DB + Grafana data
```

---

## 📡 Step 4 — HiveMQ Broker Setup

This project uses **HiveMQ Cloud** (managed). There is no broker to install.

### 4.1 Cluster (already provisioned)

```
Hostname : e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud
TLS port : 8883   (TCP — used by ESP32 + Python backend)
WS  port : 8884   (WebSocket — reserved for browser dashboards)
```

> ⚠️ **WARNING**: this hostname and credentials are committed in the repo
> for development convenience. For any non-demo deployment: provision a new
> cluster, rotate credentials, and update both `.env` and `config.h`.

### 4.2 Create users in the HiveMQ Cloud dashboard

1. Sign in at <https://console.hivemq.cloud/>.
2. Open the cluster → **Access Management** → **Credentials**.
3. Create two users (one per consumer):

| Username | Password (rotate!) | Used by |
|---|---|---|
| `esp32-device` | `Esp32-device` (placeholder) | every ESP32 device |
| `python-server` | `Python-server5` (placeholder) | the FastAPI backend |

4. (Optional but recommended) **Set Topic Permissions** under Access
   Management → Roles. Suggested ACL:

| Role | Topic pattern | Action |
|---|---|---|
| `device` | `tenants/+/sites/+/devices/+/sensors/#` | publish |
| `device` | `tenants/+/sites/+/devices/+/status` | publish (retained) |
| `device` | `tenants/+/sites/+/devices/+/diagnostics` | publish |
| `device` | `tenants/+/sites/+/devices/+/cmd/#` | subscribe (future use) |
| `server` | `tenants/#` | subscribe |
| `server` | `tenants/+/sites/+/devices/+/alerts/#` | publish |
| `server` | `servers/+/status` | publish (retained, for own LWT) |

> ⚠️ **WARNING**: ACLs are **not** in this repo — they live in the cloud
> dashboard. Document any change in your team wiki; the repo cannot
> reproduce them.

### 4.3 Verify the broker is reachable from your laptop

Using `mosquitto_sub` (HiveMQ Cloud requires `--capath` or `--cafile` and TLS):

```powershell
# Linux/macOS path: /etc/ssl/certs/ca-certificates.crt
# Windows: install mosquitto and use the bundled "mosquitto.org.crt", or
# use --tls-version tlsv1.2 with no cafile if your build trusts system CAs.

mosquitto_sub -h e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud `
              -p 8883 -u python-server -P "Python-server5" `
              --capath /etc/ssl/certs/ -t 'tenants/#' -v
```

You should see a connection (no immediate disconnect). If retained `status`
messages exist, they'll print right away.

### 4.4 Self-hosted alternative (NOT what this project uses — for reference only)

If you ever switch to self-hosted **HiveMQ Community Edition**, the minimum
`docker-compose.yml` snippet would be:

```yaml
  hivemq:
    image: hivemq/hivemq-ce:2024.10
    container_name: hivemq-ce
    ports:
      - "1883:1883"      # plain MQTT
      - "8080:8080"      # control center
    volumes:
      - ./hivemq/conf:/opt/hivemq/conf
      - hivemq_data:/opt/hivemq/data
    networks:
      - reteq-net
```

…and you would need to:
- enable username/password auth via a `file-rbac` extension (CE doesn't have it natively — use HiveMQ EE or write a custom extension),
- bind a TLS port if not using a TLS terminator in front,
- update `MQTT_HOST=hivemq` and `MQTT_TLS=false` in `.env`.

---

## ⚙️ Step 5 — Backend Server Startup

Already covered by `docker compose up -d` (Step 3.3). What to check next:

### 5.1 Logs that confirm success

```powershell
docker compose logs --tail=200 app
```

Expected lines (in order):

```
INFO  application_starting   version=1.0.0
INFO  database connected     dsn=postgresql://reteq:***@timescaledb:5432/reteqfusion
INFO  migrations applied     files=001_init.sql,002_aggregates.sql,003_retention.sql
INFO  mqtt_connecting        host=...hivemq.cloud port=8883 tls=True
INFO  mqtt_connected         client_id=reteqfusion-server-01
INFO  mqtt_subscribed        topic=tenants/+/sites/+/devices/+/sensors/dht22/telemetry qos=1
INFO  mqtt_subscribed        topic=tenants/+/sites/+/devices/+/sensors/mq2/telemetry qos=1
INFO  mqtt_subscribed        topic=tenants/+/sites/+/devices/+/status qos=1
INFO  mqtt_subscribed        topic=tenants/+/sites/+/devices/+/diagnostics qos=1
INFO  application_ready
INFO  Uvicorn running on http://0.0.0.0:8000
```

### 5.2 Health probe (HTTP)

```powershell
curl http://localhost:8000/health
# → {"status":"ok","db":true,"mqtt":true}
```

### 5.3 Inspect the database

```powershell
docker exec -it reteqfusion-timescaledb `
  psql -U reteq -d reteqfusion -c "\dt"
docker exec -it reteqfusion-timescaledb `
  psql -U reteq -d reteqfusion -c "SELECT count(*) FROM telemetry;"
```

### 5.4 Open Grafana

Browse to <http://localhost:3000>, log in as `admin` / `${GRAFANA_ADMIN_PASSWORD}` (from `.env`), the default home dashboard `iot_overview` should already be provisioned.

---

## 🔌 Step 6 — Firmware Flash & Connect (ESP32)

> ⚠️ **WARNING — STM32 NOT SUPPORTED**: This repo contains no STM32 source.
> The instructions below are for the actual ESP32 firmware. See the bottom
> of this section for the rough STM32 port effort.

### 6.1 Edit credentials before building

Open `esp32-edge/src/config.h` (or create `config.local.h` and add
`#include "config.local.h"` at the bottom of `config.h`) and set:

```cpp
#define WIFI_SSID     "your-wifi-ssid"
#define WIFI_PASSWORD "your-wifi-password"
#define MQTT_USERNAME "esp32-device"          // matches HiveMQ Cloud user
#define MQTT_PASSWORD "Esp32-device"          // matches HiveMQ Cloud user
// MQTT_HOST / MQTT_PORT / TENANT / SITE are already set
```

### 6.2 Build & flash with PlatformIO

```powershell
cd C:\IDP\esp32-edge

# Build firmware
pio run

# Flash + open monitor (requires the ESP32 plugged in via USB)
pio run --target upload --target monitor
```

If `pio` is missing: `pip install platformio`.

### 6.3 Watch the serial output (115200 baud)

Expected boot sequence:

```
================================================
  ESP32 IDP Edge Firmware  v1.0.0
================================================

>>> CLIENT_ID = esp32-aabbccddeeff <<<
    (use this for HiveMQ ACL configuration)

[DHT22] init on GPIO 4
[MQ2]   init on GPIO 34 (12-bit ADC)
[MQ2]   heater warming up — readings stabilize after ~3 min
[NET]   Wi-Fi connecting to <SSID>...
[NET]   Wi-Fi connected, IP=192.168.x.y, RSSI=-58
[NET]   NTP sync ok, epoch=1714650000
[MQTT]  Attempting connection to ...hivemq.cloud:8883
[MQTT]  connected — state=0 (connected)
[MQTT]  PUB tenants/demo/sites/lab/devices/esp32-aabbccddeeff/status (retained)
[DHT22] PUB seq=1 temp=23.4 hum=58.1
[MQ2]   PUB seq=1 mean=890 ...
```

State-code reference (from `mqttmgr.cpp::decodeRc`):
| Code | Meaning |
|---|---|
| 0 | connected |
| -2 | TLS handshake failed |
| -4 | connection timeout |
| 4 | bad username / password |
| 5 | not authorized — check ACL |

### 6.4 Optional STM32 port (effort estimate, NOT runnable today)

If you must run on STM32 hardware, you would need to:

1. Pick a transport: **STM32 + W5500 Ethernet** (LwIP) or **STM32 + ESP-AT** Wi-Fi co-processor (UART AT commands).
2. Replace `WiFiClientSecure + PubSubClient` with **`paho-mqtt-embedded-c` + mbedTLS** (LwIP) or use Cube's NetXDuo MQTT client.
3. Re-implement `config.h`, `mqttmgr.cpp`, `netmgr.cpp`, `buffer.cpp`, BLE provisioning (or drop it), and the watchdog wrapper. The sensor logic in `sensor_dht22.cpp` / `sensor_mq2.cpp` is mostly portable but uses `ArduinoJson` — switch to a small C JSON lib (e.g. `tinycbor`/`jsmn`).
4. Build with STM32CubeIDE; flash with ST-Link (`STM32_Programmer_CLI -c port=SWD -d firmware.elf -rst`).
5. The broker, ACLs, payload schema, and topic hierarchy stay identical — the backend will not know the difference.

---

## 📊 Step 7 — End-to-End Verification

You have **three** ways to drive a "device" message — pick whichever you have available. The verification on the backend side is the same.

### 7.1 Source A — real ESP32

After flashing, simply observe the board publish on its 2 s / 5 s cadence (Step 6.3). You should see fresh rows in the DB within a few seconds.

### 7.2 Source B — captor-simulator (no hardware needed)

```powershell
cd C:\IDP\captor-simulator
python -m pip install -r requirements.txt

# point to broker (env vars override config.yaml's `mqtt: { host: null }`)
$env:MQTT_HOST="e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud"
$env:MQTT_PORT="8883"
$env:MQTT_USERNAME="esp32-device"
$env:MQTT_PASSWORD="Esp32-device"

python simulator.py --config config.yaml
```

### 7.3 Source C — single shot via `mosquitto_pub`

```powershell
mosquitto_pub `
  -h e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud -p 8883 `
  --capath /etc/ssl/certs/ `
  -u esp32-device -P "Esp32-device" `
  -t "tenants/demo/sites/lab/devices/test_device/sensors/dht22/telemetry" `
  -q 1 `
  -m '{"schema_version":"1.0","ts":"2026-05-02T10:00:00Z","device_id":"test_device","tenant":"demo","site":"lab","sensor_id":"dht22_01","sensor_type":"dht22","seq":1,"readings":{"temperature":{"value":24.5,"unit":"C","quality":"good"},"humidity":{"value":62.0,"unit":"%","quality":"good"}},"fw_version":"1.0.0"}'
```

### 7.4 Verification checklist (4 stages of the pipeline)

#### ① ESP32 / source published
- Serial log shows `[MQTT] PUB tenants/demo/sites/lab/devices/<id>/sensors/dht22/telemetry`
- For `mosquitto_pub`, exit code 0 and no stderr.

#### ② HiveMQ received and routed
- Open a parallel `mosquitto_sub`:
  ```powershell
  mosquitto_sub -h e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud `
    -p 8883 --capath /etc/ssl/certs/ -u python-server -P "Python-server5" `
    -t 'tenants/#' -v
  ```
  You should see your message echoed back.
- Or use **`reteqfusion-live/`** for a pretty-printed live view:
  ```powershell
  cd C:\IDP\reteqfusion-live
  pip install -r requirements.txt
  python subscriber.py
  ```

#### ③ Backend ingested it
```powershell
docker compose -f C:\IDP\reteqfusion-server\docker-compose.yml logs --tail=50 app | Select-String "telemetry|dispatch"
```
You should see entries like `INFO mqtt_message topic=... | INFO telemetry_persisted device_id=test_device sensor_type=dht22`.

Then query the hypertable:
```powershell
docker exec -it reteqfusion-timescaledb psql -U reteq -d reteqfusion -c `
  "SELECT time, device_id, sensor_type, reading_key, value FROM telemetry ORDER BY time DESC LIMIT 5;"
```

#### ④ Visible via API + Grafana
```powershell
curl http://localhost:8000/api/v1/devices
curl http://localhost:8000/api/v1/sensors?device_id=test_device&sensor_type=dht22&limit=5
```
Open <http://localhost:3000> → Dashboards → **IoT Overview** — temperature/humidity/ppm panels should plot the new points.

---

## 🐛 Step 8 — Troubleshooting Guide

### 🔌 ESP32 cannot connect to broker
| Symptom | Likely cause | Fix |
|---|---|---|
| `state=-2 (TLS handshake or socket connect failed)` | wrong root CA or wrong port (8884 instead of 8883) | confirm `MQTT_PORT 8883` and that `BROKER_CA_PEM` matches the broker's chain (Step 2.2) |
| `state=-4 (connection timeout)` | Wi-Fi up but no internet, or NTP failed → cert "not yet valid" | check NTP sync line in serial; ensure outbound TCP/8883 is open |
| `state=4 (bad username or password)` | typo in `MQTT_USERNAME/PASSWORD`, or used the server account on a device | use the device user; confirm in HiveMQ dashboard |
| `state=5 (not authorized)` | ACL denies publish | check Topic Permissions in HiveMQ Cloud — pattern must match the topic the firmware builds |
| Repeated reconnect every 2-60 s, exponential backoff log | broker dropped the session | inspect `pubFailCount()` via `diagnostics` topic; usually network instability |

### 🔐 TLS handshake failure (any client)
| Diagnostic | Action |
|---|---|
| `openssl s_client -connect host:8883 -showcerts` returns the chain | broker is up and serving TLS |
| Same command hangs / connection refused | wrong port or firewall — try 8883 explicitly |
| `verify error:num=20:unable to get local issuer certificate` | client doesn't trust the chain → install `ca-certificates` (Linux) or pass `--cafile mosquitto.org.crt` (Windows mosquitto) |
| ESP32 only: chain valid but TLS still fails | system clock not set → NTP issue |

### 🧱 Backend not receiving messages
| Check | Command | Expected |
|---|---|---|
| App connected to broker? | `curl localhost:8000/health` | `"mqtt":true` |
| Right wildcards subscribed? | `docker logs reteqfusion-app | grep mqtt_subscribed` | 4 entries |
| Messages reaching the broker at all? | `mosquitto_sub -t 'tenants/#' -v` (other shell) | sees the publish |
| Topic naming mismatch? | print `topic` field in `mqtt_message` log | must match `tenants/<t>/sites/<s>/devices/<d>/...` exactly (no leading slash) |
| Messages going to DLQ? | `docker exec -it reteqfusion-timescaledb psql -U reteq -d reteqfusion -c "SELECT topic,reason,error_msg FROM dlq ORDER BY received_at DESC LIMIT 10;"` | empty if all messages parse cleanly |
| Pydantic validation errors? | grep `dlq_validation` in app logs | shows missing required fields |

### 🐳 Docker networking issues
| Symptom | Diagnosis | Fix |
|---|---|---|
| `app` container exits with `connection refused timescaledb:5432` | started before DB was healthy | `depends_on: condition: service_healthy` is set — verify the timescaledb healthcheck is passing: `docker compose ps` |
| `timescaledb` healthy but `app` says `password authentication failed` | `.env` and DB-init mismatch (volume from prior run with different password) | `docker compose down --volumes` then `up -d` (DESTRUCTIVE: wipes data) |
| Cannot reach `http://localhost:8000` from host | port not exposed or app crashed | `docker compose ps` (state should be `running (healthy)`); `docker compose logs app` |
| Grafana `Failed to connect to data source` | Grafana provisioning still references `localhost` instead of `timescaledb` | open `reteqfusion-server/grafana/provisioning/datasources/timescaledb.yaml` and ensure `url: timescaledb:5432` |
| Containers can't reach the internet (broker unreachable from `app`) | corporate firewall / VPN / Docker DNS broken | `docker compose exec app python -c "import socket; print(socket.gethostbyname('e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud'))"` |

### 🗄 TimescaleDB / migration issues
| Symptom | Fix |
|---|---|
| `extension "timescaledb" is not available` | image must be `timescale/timescaledb:*-pg16` (not vanilla `postgres`) — already correct in repo |
| `relation "telemetry" does not exist` after fresh boot | migrations didn't run → check `app` logs for `migrations applied`; if missing, the container failed before that point |
| `duplicate key` on retry | same `seq` for same device — re-publish with monotonic `seq` or accept the dedupe |

### 🔁 Quick reset cookbook

```powershell
# Restart only the app (keeps DB)
docker compose restart app

# Rebuild app after editing Python source
docker compose build app && docker compose up -d app

# Full nuke (DB + Grafana wiped — no recovery)
docker compose down --volumes
docker compose up -d --build
```

---

## 🌐 Data-flow summary

**ESP32 (Wi-Fi STA + WiFiClientSecure + PubSubClient @ QoS 1) → HiveMQ Cloud (`e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud:8883`, MQTT v3.1.1 over TLS) → FastAPI backend (`reteqfusion-app`, paho-mqtt subscriber → `asyncio.Queue` → Pydantic validation → asyncpg) → TimescaleDB hypertable `telemetry` + REST API on `:8000` + Grafana dashboards on `:3000`.**

> ⚠️ Where this brief said "STM32" the actual MCU is **ESP32**. Everything
> downstream of the MCU is identical regardless of which microcontroller
> publishes — porting to STM32 is firmware-only work.
