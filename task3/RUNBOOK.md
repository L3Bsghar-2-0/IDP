# Re·Tech Fusion — Production Runbook

> Complete step-by-step guide for training the TinyML model, generating jury evidence,
> and deploying to the ESP32 hardware.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Desktop | ≥ 24.0 | `docker compose` (V2 plugin) |
| PlatformIO CLI or IDE | ≥ 6.x | For firmware flashing |
| ESP32 Dev Module | Any variant | With DHT22 + MQ-2 connected |
| USB-Serial cable | — | For flashing + serial monitoring |
| Sensor CSV | — | `sensor_data.csv` in `data/` |

---

## Phase 1 — ML Pipeline (Docker)

### 1.1 Prepare Input Data

```bash
# Place your unified sensor CSV into the data/ mount point.
# The CSV must have columns: timestamp, sensor_type, value
# (or already be pivoted with one column per sensor).
cp /path/to/unified_sensor_data.csv  data/sensor_data.csv
```

### 1.2 Build the Base Image

```bash
docker compose build base
```

This creates `idp-base:latest` with TensorFlow 2.15, numpy, pandas, scikit-learn.
It only needs to be rebuilt when dependencies change.

### 1.3 Run the Full Pipeline

```bash
docker compose up --build
```

This executes three stages sequentially:

| Stage | Service | Inputs | Outputs |
|-------|---------|--------|---------|
| 1. Train | `trainer` | `data/sensor_data.csv` | `models/model.h5`, `models/scaler.pkl`, `models/held_out_test.csv` |
| 2. Convert | `converter` | `models/model.h5`, `models/held_out_test.csv` | `models/model_int8.tflite`, `models/model_fp32.tflite`, `esp32-edge/src/model_data.h` |
| 3. Simulate | `simulator` | `models/model_int8.tflite`, `models/held_out_test.csv` | `results/simulation_results.json`, `results/latency_report.json` |

### 1.4 Validate Outputs

```bash
# Check the model size budget (<200 KB)
ls -la models/model_int8.tflite

# Verify jury evidence
cat results/simulation_results.json | python -m json.tool | head -30

# Confirm latency pass
cat results/latency_report.json
# Expected: "latency_pass": true
```

### 1.5 Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ERROR: Data file not found` | CSV not in `data/` | `cp sensor_data.csv data/` |
| `trainer` exits with code 1 | Data format mismatch | Ensure CSV has `timestamp`, `sensor_type`, `value` columns |
| `converter` exits with code 1 | Missing `model.h5` | Re-run `docker compose up` from scratch |
| Large model (>200KB) | Too many parameters | Reduce MLP width in `train_model.py` |

---

## Phase 2 — ESP32 Firmware Deployment

### 2.1 Verify model_data.h

After `docker compose up`, the converter writes `model_data.h` directly into `esp32-edge/src/`.
Verify it exists:

```bash
head -5 esp32-edge/src/model_data.h
# Expected: const unsigned char model_data[] PROGMEM = { 0x20, 0x00, ...
```

### 2.2 Configure Wi-Fi + MQTT Credentials

Create a local credential override (git-ignored):

```bash
cp esp32-edge/src/config.h esp32-edge/src/config.local.h
```

Edit `config.local.h` with your actual credentials:
```cpp
#undef  WIFI_SSID
#define WIFI_SSID     "your-network"
#undef  WIFI_PASS
#define WIFI_PASS     "your-password"
#undef  MQTT_USER
#define MQTT_USER     "your-mqtt-user"
#undef  MQTT_PASS
#define MQTT_PASS     "your-mqtt-pass"
```

Then add `#include "config.local.h"` at the top of `config.h`.

### 2.3 Compile + Flash

**PlatformIO CLI:**
```bash
cd esp32-edge
pio run --target upload
```

**Arduino IDE:**
1. Board: "ESP32 Dev Module"
2. Partition: "Default 4MB with spiffs"
3. Flash: "Upload"

### 2.4 Serial Monitor

```bash
# PlatformIO
pio device monitor --baud 115200

# Arduino IDE → Tools → Serial Monitor → 115200 baud
```

**Expected boot sequence:**
```
[BOOT]  Re·Tech Fusion v1.0.0 — starting...
[NET]   Connecting to WiFi...
[NET]   Connected. IP: 192.168.x.x
[NTP]   Synced. UTC: 2026-05-03T02:00:00Z
[MQTT]  Connected to mqtt.hivemq.cloud:8883
[ANOM]  Model loaded. Input shape: [1, 10, 3]. Arena: 4096 bytes
[DHT22] First read OK: 24.5°C, 55.2%
[MQ-2]  Warming up (60s)...
[DIAG]  Last reset reason: poweron
[BOOT]  All subsystems initialized.
```

**Live inference log:**
```
[ANOM] win=25  mae=0.012  thr=0.045  anomaly=NO   latency=18ms
[ANOM] win=26  mae=0.089  thr=0.047  anomaly=YES  latency=19ms  ← spike detected
```

### 2.5 Latency Validation (on device)

To collect real hardware latency evidence, use serial mode:

```bash
python simulate.py \
    --mode serial \
    --port COM3 \
    --baud 115200 \
    --output_dir results/
```

This captures 50 consecutive inference cycles from the live firmware and writes `latency_report.json`.

---

## Phase 3 — Jury Evidence Checklist

| Artifact | Location | Verified |
|----------|----------|----------|
| `simulation_results.json` | `results/` | Contains model metadata + anomaly events |
| `latency_report.json` | `results/` | Shows `latency_pass: true`, `mean_inference_ms < 200` |
| `training_report.txt` | `models/` | Per-sensor MAE breakdown |
| `quantization_report.txt` | `models/` | Size + accuracy degradation check |
| `model_data.h` | `esp32-edge/src/` | C byte array for firmware inclusion |
| `README_part3.md` | root | Submission template (fill in measured values) |

---

## Phase 4 — Updating README_part3.md

After pipeline completes, populate the placeholders in `README_part3.md`:

```bash
# From simulation_results.json:
#   model.total_params       → [PARAM_COUNT]
#   model.size_fp32_bytes    → [SIZE_FP32_KB]  (÷ 1024)
#   model.size_int8_bytes    → [SIZE_INT8_KB]  (÷ 1024)
#   per_sensor_mae[]         → [MAE_SENSOR_1], [MAE_SENSOR_2], [MAE_SENSOR_3]

# From latency_report.json:
#   mean_inference_ms        → [MEAN_LATENCY_MS]
#   p50/p95/max              → remaining placeholders
#   latency_pass             → [PASS/FAIL]
```

---

## Appendix A — Running Without Docker

If Docker is unavailable, run the pipeline natively:

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install tensorflow==2.15.1 numpy==1.26.4 pandas==2.2.1 scikit-learn==1.4.2

# Stage 1: Train
python train_model.py \
    --data_path unified_sensor_data.csv \
    --window_size 10 \
    --output_dir models/

# Stage 2: Convert
python convert_model.py \
    --model models/model.h5 \
    --data_path models/held_out_test.csv \
    --scaler_path models/scaler.pkl \
    --output_dir models/ \
    --header_dir esp32-edge/src/

# Stage 3: Simulate
python simulate.py \
    --mode emulate \
    --model models/model_int8.tflite \
    --data models/held_out_test.csv \
    --scaler_path models/scaler.pkl \
    --output_dir results/
```

---

## Appendix B — Known Limitations

1. **Offline buffer cap:** LittleFS buffer is 64 KB. Prolonged network outages (>~400 messages) will cause FIFO rotation of oldest telemetry.
2. **TLS CA rotation:** The `BROKER_CA_PEM` in `config.h` is hardcoded to the ISRG Root X1 certificate. If HiveMQ rotates its CA, the firmware must be reflashed.
3. **MQ-2 warm-up:** The MQ-2 gas sensor requires a 60-second warm-up period after power-on before readings are reliable.
4. **Model retraining:** If sensor characteristics change (new sensor types, different sampling rates), the full pipeline must be re-executed to regenerate `model_data.h`.
