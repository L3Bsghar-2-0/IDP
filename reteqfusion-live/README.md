# ReTeqFusion Live Subscriber

A minimal, dependency-light Python MQTT subscriber that connects to the
ReTeqFusion HiveMQ Cloud broker over TLS, listens to live ESP32 telemetry,
and pretty-prints every message in the terminal.

No database. No Docker. No Grafana. Just: connect → receive → decode → display.

## Setup

```bash
pip install -r requirements.txt
python subscriber.py
```

That's it. The subscriber will connect to HiveMQ Cloud, subscribe to all
ESP32 topics under `tenants/+/sites/+/devices/+/...`, and start rendering
incoming messages.

Stop the subscriber with `Ctrl+C`. A session summary will be printed.

## What you'll see

| Message type | Header | Style |
| --- | --- | --- |
| **DHT22 telemetry** | `🌡  DHT22 Telemetry` | cyan box, temp & humidity with quality flags |
| **MQ-2 telemetry** | `💨 MQ-2 Gas Sensor` | yellow box, ppm + hazard level + ADC bar graph |
| **MQ-2 alarm** (`smoke_detected=1`) | `🚨 MQ-2 GAS ALARM` | red blinking box + flashing banner line |
| **Device status** | `📡 Device Status` | green if online, red if offline |
| **Diagnostics** | `🔧 Diagnostics` | dim/gray, uptime + heap + RSSI |
| **Alerts** | `🚨 ALERT` | bold red, all fields dumped |
| **Unknown / malformed** | `⚠ UNKNOWN MESSAGE` | magenta, raw payload + parse error |

A live stats line is updated in place every 10 seconds, e.g.:

```
📊 Stats │ Msgs: 142 │ DHT22: 71 │ MQ2: 69 │ Alerts: 2 │ Errors: 0 │ Uptime: 00:03:22
```

## Project layout

```
reteqfusion-live/
├── subscriber.py     ← entry point: MQTT client + dispatch loop
├── parser.py         ← JSON parsing + pydantic validation
├── display.py        ← ANSI-coloured terminal rendering
├── stats.py          ← in-memory counters + summary
├── requirements.txt  ← paho-mqtt, pydantic
└── README.md
```

## Topics subscribed (QoS 1)

```
tenants/+/sites/+/devices/+/sensors/dht22/telemetry
tenants/+/sites/+/devices/+/sensors/mq2/telemetry
tenants/+/sites/+/devices/+/status
tenants/+/sites/+/devices/+/diagnostics
tenants/+/sites/+/devices/+/alerts/#
```

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `TLS FAILED` | Wrong port — must be **8883**, not 1883. TLS is mandatory on HiveMQ Cloud. |
| `AUTH FAILED` (rc=5 / 134 / 135) | Wrong username/password. The subscriber does **not** retry on auth failure — fix your credentials. |
| No messages at all | ESP32 may not be publishing. Verify the device is online and check the topic wildcards above. |
| Only one sensor type appears | The other sensor may not be wired/publishing yet. |
| `🔄 Disconnected` repeatedly | Network instability — paho-mqtt auto-reconnects with 2s → 30s backoff. |
| Garbled box characters | Your terminal needs UTF-8. On Windows: `chcp 65001` before running. |

## Manual test (publish a fake DHT22 reading)

If you have `mosquitto_pub` installed, you can simulate an ESP32 publish to
verify the subscriber works end-to-end. Use the dedicated ESP32 device
credentials (separate from the `python-server` subscriber credentials):

```bash
mosquitto_pub \
  -h e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud \
  -p 8883 --cafile /etc/ssl/certs/ca-certificates.crt \
  -u esp32-device -P Esp32-device \
  -t "tenants/demo/sites/lab/devices/test_device/sensors/dht22/telemetry" \
  -m '{"schema_version":"1.0","ts":"2025-01-01T12:00:00.000Z","device_id":"test_device","tenant":"demo","site":"lab","sensor_id":"dht22_01","sensor_type":"dht22","seq":1,"readings":{"temperature":{"value":24.5,"unit":"C","quality":"good"},"humidity":{"value":62.0,"unit":"%","quality":"good"}},"fw_version":"1.0.0"}'
```

You should see a cyan `🌡 DHT22 Telemetry` box appear in the subscriber
within a second. Try changing `smoke_detected` to `1` on an MQ-2 message
to trigger the blinking gas alarm output.
