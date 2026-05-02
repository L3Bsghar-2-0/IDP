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

## OTA (Over-The-Air) Update Simulation

The simulator supports simulating firmware update workflows for testing OTA pipelines.

### Enabling OTA Simulation

In config.yaml, set the ota section:

```yaml
ota:
  enabled: true
  update_interval_s: 3600
  failure_rate: 0.05
  available_versions:
    - "1.0.0"
    - "1.0.1"
    - "1.1.0"
    - "2.0.0"
```

Fields:

- enabled: Enable/disable OTA simulation (default: false)
- update_interval_s: Polling interval for checking updates in seconds (default: 3600 = 1 hour)
- failure_rate: Probability (0-1) that an update will fail (default: 0.05 = 5%)
- available_versions: List of firmware versions that can be deployed

### OTA State Machine

Each simulated device runs a state machine through the following states:

1. **IDLE** — Device is stable, waiting for update commands or polling for updates
2. **CHECKING** — Device is polling backend for available updates
3. **DOWNLOADING** — Device is fetching firmware image (simulated 2-5 seconds)
4. **VERIFYING** — Device is validating signature (simulated ~0.1 seconds)
5. **FLASHING** — Device is writing firmware to flash partition (simulated 3-8 seconds)
6. **REBOOTING** — Device is rebooting into new firmware (simulated 1-2 seconds)
7. **ERROR** — Update failed; device will return to IDLE after delay

### OTA Topics

When OTA is enabled, simulated devices publish to:

**OTA Status Topic:**
```
tenants/{tenant}/sites/{site}/devices/{device_id}/ota/status
```

**Example Payloads:**

Update started:
```json
{
  "ts": 1777687000,
  "event": "update_started",
  "device_id": "esp32-aabbccddee00",
  "target_version": "1.0.1",
  "state": "DOWNLOADING"
}
```

Update complete:
```json
{
  "ts": 1777687025,
  "event": "update_complete",
  "device_id": "esp32-aabbccddee00",
  "current_version": "1.0.1",
  "boot_count": 0
}
```

Update failed:
```json
{
  "ts": 1777687010,
  "event": "update_failed",
  "device_id": "esp32-aabbccddee00",
  "target_version": "1.0.1",
  "reason": "signature_verification_failed",
  "error_count": 1
}
```

### Triggering OTA Updates (Programmatic)

To trigger an update to a specific device, use the OTASimulator directly in Python:

```python
from simulator.otasim import OTASimulator

ota_sim = OTASimulator(enabled=True, failure_rate=0.05)
ota_sim.initialize_device("esp32-aabbccddee00", initial_version="1.0.0")

# Trigger update to version 1.0.1
success = ota_sim.trigger_update("esp32-aabbccddee00", "1.0.1")

# Check OTA state
state = ota_sim.get_state("esp32-aabbccddee00")
print(f"Device version: {state['current_version']}")
print(f"OTA state: {state['state']}")
print(f"Updates completed: {state['update_count']}")
```

### Testing OTA Workflows

**Scenario 1: Successful update deployment**

1. Enable OTA in config.yaml with failure_rate=0 (no failures)
2. Run simulator
3. Observe update events in MQTT or stdout
4. Verify device transitions through state machine
5. Check final state is IDLE with new version

**Scenario 2: Failure injection**

1. Enable OTA with failure_rate=0.5 (50% failure chance)
2. Run simulator multiple times
3. Observe some devices succeed, others fail with error_count incrementing
4. Verify rollback/recovery behavior

**Scenario 3: Multi-device deployment**

1. Configure multiple devices in config.yaml
2. Enable OTA on all devices
3. Run simulator
4. Observe staggered update checks across fleet
5. Monitor diagnostics topic for OTA state per device

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
