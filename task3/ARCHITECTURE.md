# Re·Tech Fusion — System Architecture

## Overview

Re·Tech Fusion is an end-to-end industrial IoT platform for **energy monitoring, anomaly detection, and predictive intelligence**. The system combines **on-device TinyML inference** on ESP32 microcontrollers with a cloud-connected data pipeline for centralized dashboarding.

---

## High-Level Data Flow

```
                                    ┌──────────────────────────────────┐
                                    │        Lumi Dashboard            │
                                    │   (lumi-dashboard.html or        │
                                    │    lumi-ui React SPA)            │
                                    └────────────▲─────────────────────┘
                                                 │ WebSocket / REST
                                    ┌────────────┴─────────────────────┐
                                    │      reteqfusion-server          │
                                    │   (FastAPI + TimescaleDB)        │
                                    └────────────▲─────────────────────┘
                                                 │ MQTT (TLS 1.2+)
                                    ┌────────────┴─────────────────────┐
                                    │     HiveMQ Cloud Broker          │
                                    │   mqtt.hivemq.cloud:8883         │
                                    └────────────▲─────────────────────┘
                                                 │ MQTT publish
                   ┌─────────────────────────────┴──────────────────────────────┐
                   │                        ESP32 Edge Node                     │
                   │                                                            │
                   │   ┌──────────┐   ┌──────────────┐   ┌──────────────────┐  │
                   │   │  DHT22   │──▶│  Sliding-     │──▶│  TFLite Micro   │  │
                   │   │  MQ-2    │   │  Window       │   │  INT8 MLP       │  │
                   │   │  Sensors │   │  Buffer (10)  │   │  Inference      │  │
                   │   └──────────┘   └──────────────┘   └───────┬──────────┘  │
                   │                                              │             │
                   │                                    ┌─────────▼──────────┐  │
                   │                                    │  Anomaly Detector  │  │
                   │                                    │  Rolling Z-Score   │  │
                   │                                    │  2.5σ threshold    │  │
                   │                                    └────────────────────┘  │
                   └────────────────────────────────────────────────────────────┘
```

---

## Component Inventory

### 1. ML Training Pipeline (Python / Docker)

| File | Role |
|------|------|
| `train_model.py` | Loads unified sensor CSV → chronological train/val/test split (70/15/15) → MinMaxScaler (fit on train) → builds sliding-window MLP → saves `model.h5`, `scaler.pkl`, `held_out_test.csv` |
| `convert_model.py` | Loads `model.h5` → full-INT8 post-training quantization with representative dataset → size/accuracy validation → generates `model_int8.tflite` + `model_data.h` C byte array |
| `simulate.py` | Loads INT8 TFLite model → runs PC-side emulation on held-out test → rolling z-score anomaly detection (2.5σ) → produces `simulation_results.json` + `latency_report.json` |

**Docker orchestration:** `docker-compose.yml` chains these as `trainer → converter → simulator` using `depends_on: condition: service_completed_successfully`.

### 2. ESP32 Edge Firmware (`esp32-edge/`)

| File | Role |
|------|------|
| `main.cpp` | Boot orchestration: `netmgr → mqttmgr → ota → sensors → buffer → anomaly → diag` |
| `config.h` | All compile-time constants: pins, MQTT host, thresholds, firmware version, TLS CA cert |
| `netmgr.cpp/h` | Wi-Fi STA mode, exponential-backoff reconnect, NTP time sync |
| `mqttmgr.cpp/h` | TLS MQTT client, topic namespacing, LWT, QoS-aware publish, retry |
| `sensor_dht22.cpp/h` | DHT22 (temperature, humidity) — 2-second read interval |
| `sensor_mq2.cpp/h` | MQ-2 (smoke/gas) — 5-second aggregation window with min/max/mean stats |
| `anomaly.cpp/h` | **On-device TFLite Micro inference** — sliding window buffer, INT8 model, rolling z-score |
| `buffer.cpp/h` | Offline message queue (LittleFS, 64 KB FIFO, auto-drain on reconnect) |
| `ota.cpp/h` | HTTP-based OTA firmware updates with version tracking |
| `ble_prov.cpp/h` | BLE-based Wi-Fi credential provisioning |
| `diag.cpp/h` | Periodic diagnostics heartbeat (heap, RSSI, uptime, error counts) |

### 3. Backend Server (`reteqfusion-server/`)

| Component | Role |
|-----------|------|
| `app/main.py` | FastAPI application entry point |
| `app/config.py` | pydantic-settings config loader (`.env` driven) |
| `app/mqtt_listener.py` | MQTT subscriber that ingests sensor telemetry |
| `Dockerfile` | Production image (python:3.12-slim + uvicorn) |

### 4. Dashboard

| Component | Role |
|-----------|------|
| `lumi-dashboard.html` | Standalone static HTML dashboard with Chart.js — designed for jury demos |
| `lumi-ui/` | React + Vite SPA (development version) |

---

## Key Design Constants

| Parameter | Value | Source |
|-----------|-------|--------|
| Window Size | 10 timesteps | `config.h:WINDOW_SIZE`, `train_model.py --window_size` |
| Anomaly Z-Score Multiplier | 2.5σ | `anomaly.cpp:ZSCORE_MULTIPLIER`, `simulate.py` |
| Anomaly Rolling Buffer | 20 samples | `anomaly.cpp:ROLLING_BUF_SIZE`, `simulate.py` |
| Quantization | Full INT8 (input/output) | `convert_model.py`, `anomaly.cpp` |
| Model Size Budget | < 200 KB | `convert_model.py` validation |
| Latency Budget | < 200 ms | `simulate.py` validation |
| MQTT QoS for Telemetry | 1 | `mqttmgr.cpp` |
| DHT22 Read Interval | 2 s | `sensor_dht22.cpp` |
| MQ-2 Aggregation Window | 5 s | `sensor_mq2.cpp` |
| Diagnostics Interval | 5 min | `diag.cpp` |
| Offline Buffer Size | 64 KB | `buffer.cpp` |
| TLS | TLS 1.2+ (ISRG Root X1 CA) | `config.h:BROKER_CA_PEM` |
| Random Seeds | 42 (numpy, tensorflow) | `train_model.py`, `convert_model.py` |

---

## Anomaly Detection: Python ↔ Firmware Parity

Both the Python simulation (`simulate.py`) and the firmware (`anomaly.cpp`) implement the **identical** detection algorithm:

1. **Predict** the next timestep using the INT8 MLP.
2. **Calculate** absolute prediction error per sensor.
3. **Append** error to a rolling buffer of last 20 errors.
4. **Compute** `threshold = mean(buffer) + 2.5 × std(buffer)`.
5. **Flag anomaly** if `error > threshold`.

This ensures the jury can validate that PC-side simulation results are reproducible on the real hardware.

---

## Directory Tree

```
IDP/
├── docker-compose.yml         # Pipeline orchestration
├── Dockerfile.base            # Shared Python/TF base image
├── Dockerfile.trainer         # Stage 1: training
├── Dockerfile.converter       # Stage 2: quantization
├── Dockerfile.simulator       # Stage 3: emulation
├── .env                       # Pipeline config
├── .env.example               # Template for secrets
├── .gitignore                 # VCS exclusions
├── .dockerignore              # Build context exclusions
│
├── train_model.py             # [Python] Model training
├── convert_model.py           # [Python] INT8 quantization
├── simulate.py                # [Python] PC-side emulation
│
├── data/                      # Input sensor CSV mount point
├── models/                    # Generated model artifacts
├── results/                   # Jury evidence (JSON)
│
├── esp32-edge/                # PlatformIO firmware project
│   ├── platformio.ini
│   └── src/
│       ├── main.cpp
│       ├── config.h
│       ├── anomaly.cpp/h
│       ├── sensor_dht22.cpp/h
│       ├── sensor_mq2.cpp/h
│       ├── mqttmgr.cpp/h
│       ├── netmgr.cpp/h
│       ├── buffer.cpp/h
│       ├── ota.cpp/h
│       ├── ble_prov.cpp/h
│       ├── diag.cpp/h
│       └── model_data.h       # Auto-generated by converter
│
├── reteqfusion-server/        # FastAPI backend
│   ├── Dockerfile
│   ├── app/
│   └── sql/
│
├── lumi-dashboard.html        # Static dashboard (jury demo)
├── lumi-ui/                   # React dashboard (dev)
│
├── ARCHITECTURE.md            # This file
├── RUNBOOK.md                 # Step-by-step operations guide
└── README_part3.md            # Hackathon submission template
```
