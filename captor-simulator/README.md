# Captor Simulator

Production-ready Industrial IoT sensor simulator for validating telemetry pipelines without physical hardware.

This project simulates realistic industrial sensors with:

- Time-based behavior (daily cycles, shift loads, pulses, events)
- Gaussian noise and physical range constraints
- Failure injection (stuck, dropout, spike, drift, disconnect, noise increase)
- Multi-device async runtime
- MQTT publishing with QoS 1, TLS, LWT, reconnect backoff, and offline SQLite buffering

## Project Layout

```
captor-simulator/
   simulator/
      base.py
      sensors.py
      device.py
      runner.py
   simulator.py
   config.yaml
   requirements.txt
   README.md
```

## Requirements

- Python 3.11+
- Windows, Linux, or macOS

## Setup

From the captor-simulator folder:

```powershell
python -m pip install -r requirements.txt
```

Optional (recommended): create and activate a virtual environment first.

## Quick Start

Run in stdout mode (best for first validation):

```powershell
python simulator.py --mode stdout --config config.yaml
```

You will see NDJSON telemetry records printed continuously.

## Runtime Modes

### 1) stdout mode

```powershell
python simulator.py --mode stdout --config config.yaml
```

Use when:

- Debugging data shape and value realism
- Testing parsers directly from process output

### 2) file mode

```powershell
python simulator.py --mode file --config config.yaml --output-file telemetry.ndjson
```

Behavior:

- Writes one NDJSON file per device (for example floor_01.ndjson)
- Good for replay-based pipeline tests and offline ingestion validation

### 3) mqtt mode

```powershell
python simulator.py --mode mqtt --config config.yaml
```

Set these environment variables first:

- MQTT_HOST
- MQTT_PORT
- MQTT_USER
- MQTT_PASS

Example (PowerShell):

```powershell
$env:MQTT_HOST="localhost"
$env:MQTT_PORT="8883"
$env:MQTT_USER="myuser"
$env:MQTT_PASS="mypassword"
python simulator.py --mode mqtt --config config.yaml
```

## Telemetry Contract

Each reading follows this strict schema:

```json
{
   "v": 1,
   "device_id": "floor_01",
   "sensor_id": "temp_01",
   "sensor_type": "temperature",
   "ts": 1777687000000,
   "seq": 42,
   "value": 24.73,
   "unit": "C",
   "quality": "good",
   "meta": {}
}
```

Notes:

- ts is epoch milliseconds
- seq increments per sensor stream
- quality is good, suspect, or bad
- value may be a number or an object (for multi-value sensors like vibration or energy)

## MQTT Topic Pattern

Telemetry topic:

```
tenants/{tenant}/sites/{site}/devices/{device_id}/sensors/{sensor_id}/telemetry
```

Device status topic (LWT retained):

```
tenants/{tenant}/sites/{site}/devices/{device_id}/status
```

Status values:

- online
- offline

## High-Frequency Aggregation

Sensors above 10 Hz are window-aggregated before publish.

Aggregate payload contains:

- min
- max
- mean
- std
- count

This keeps downstream systems stable under high sample-rate channels.

## Configuration Guide

Main file: config.yaml

Top-level sections:

- simulation
- mqtt
- devices

Key fields:

- simulation.speed_multiplier: accelerate time (for example 10.0)
- simulation.random_failures: enable stress mode failures
- simulation.aggregate_window_s: aggregation window for high-rate sensors
- devices[].sensors[].enabled: enable or disable sensors with no code changes
- devices[].sensors[].noise_factor: scale baseline noise
- devices[].failures[]: deterministic scheduled failures using offsets

Failure schedule semantics:

- start_offset_s is relative to simulator start
- duration_s is active duration
- intensity scales effect magnitude

## Integrating Into an Existing Pipeline

Use this process to wire the simulator safely into production-like flows.

### Step 1: Lock the schema at ingestion

Treat these fields as contract-required:

- v
- device_id
- sensor_id
- sensor_type
- ts
- seq
- value
- unit
- quality
- meta

### Step 2: Connect transport

Choose one input route:

- MQTT subscriber for streaming integration tests
- NDJSON file replay for deterministic, offline test runs
- stdout capture for local parser debugging

### Step 3: Handle quality-aware processing

Recommended policy:

- good: full trust and normal processing
- suspect: process but flag for QA/anomaly pipeline
- bad: drop from analytics or route to fault topic/table

### Step 4: Validate edge-case handling

Use deterministic failures to test:

- null/disconnect behavior
- stuck values and frozen trends
- spikes and clipping
- drift detection
- dropout recovery

### Step 5: Stress test throughput

Enable high-rate sensors and random failures together to validate:

- queue backpressure behavior
- parser resilience
- broker reconnect logic
- ordering and replay consistency

## MQTT Reliability Details

MQTT publishing includes:

- QoS 1 telemetry
- TLS support
- LWT retained offline status
- Exponential reconnect backoff plus jitter
- SQLite offline buffer per device
- Buffer cap of 10,000 messages with oldest-drop policy
- Drain oldest-first on reconnect

## Programmatic Embedding (Optional)

You can embed the simulator runtime into another Python service by importing modules in simulator/base.py, simulator/sensors.py, and simulator/device.py, then constructing VirtualDevice objects directly.

Common reasons to embed:

- Start and stop simulator from your test harness
- Use in-process queue publisher for integration tests
- Attach custom publisher adapters (Kafka/HTTP/etc.)

## Troubleshooting

### Import errors

- Ensure you are running from captor-simulator
- Reinstall dependencies with requirements.txt

### No MQTT output

- Confirm MQTT environment variables are set in the same shell session
- Verify broker TLS and credentials
- Check status topic for offline or reconnect loops

### Unexpected values

- Check sensor ranges and noise_factor in config.yaml
- Ensure failure schedules are not active at that timestamp
- Disable random_failures for deterministic debugging

## Recommended Hackathon Workflow

1. Start in stdout mode and validate schema quickly.
2. Move to file mode and test replay ingestion.
3. Move to mqtt mode once parser and transforms are stable.
4. Add scheduled failures to verify reliability paths.
5. Enable random_failures for final stress testing.
