# ESP32 Edge Firmware — IDP Project

Firmware for an ESP32-WROOM-32 dev board that samples a DHT22
temperature/humidity sensor and an MQ2 gas sensor, validates and aggregates
the readings, and publishes JSON telemetry over TLS-secured MQTT to a
HiveMQ Cloud broker. Features:

- LittleFS-backed NDJSON ring buffer for reliable offline storage and replay
- NimBLE GATT service for Wi‑Fi provisioning and live sensor/status reads
- TLS-protected MQTT telemetry and diagnostics, with retained LWT status
- OTA state machine for safe partitioned updates (HMAC verification planned)
- Periodic diagnostics for fleet health visibility

---

## Wiring

| Device            | ESP32 pin       | Notes                                                                  |
|-------------------|-----------------|------------------------------------------------------------------------|
| DHT22 VCC         | 3.3 V           |                                                                        |
| DHT22 GND         | GND             |                                                                        |
| DHT22 DATA        | GPIO 4          | 10 kΩ pull-up resistor between DATA and 3.3 V                          |
| MQ2 VCC           | 5 V / 3.3 V     | Per module spec; ensure AO level is ESP32-safe                         |
| MQ2 GND           | GND             |                                                                        |
| MQ2 AO            | GPIO 34         | Input-only, ADC1 channel 6 (12-bit ADC, raw 0..4095)                  |

---

## Build, flash, monitor

```
pio run                  # compile
pio run -t upload        # flash
pio device monitor       # 115200 baud
```

LittleFS is mounted from a partition created by the toolchain on first
boot — no separate `pio run -t uploadfs` step is required.

Note: PlatformIO in this repo pins `espressif32 @ ~6.7.0` (Arduino-ESP32
2.0.x). See `platformio.ini` for `monitor_speed`, `upload_speed`, and
`board_build.filesystem = littlefs` settings.

---

## Configuration

Edit only the placeholder lines in `src/config.h`:

```c
#define WIFI_SSID     "..."
#define WIFI_PASSWORD "..."
#define MQTT_USERNAME "..."   // HiveMQ Cloud device user
#define MQTT_PASSWORD "..."   // HiveMQ Cloud device password
```

The broker host (`e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud`),
port (`8883`, MQTT-over-TLS), tenant, site, and CA root certificate
(Let's Encrypt ISRG Root X1) are pre-set. The companion WebSocket port
`8884` is **not** used by this firmware — it's reserved for browser
clients (e.g. dashboards in the server layer).

If you'd rather not commit credentials, create `src/config.local.h`
(gitignored) with your overrides and `#include "config.local.h"` at the
top of `config.h`.

For convenience the repository contains `src/config.local.h.example`
which you can copy to `src/config.local.h` and edit locally. Do NOT
commit real credentials or private keys.

---

## Expected serial transcript on a healthy first boot

```
================================================
  ESP32 IDP Edge Firmware  v1.0.0
================================================

>>> CLIENT_ID = esp32-a4cf12345678 <<<
    (use this for HiveMQ ACL configuration)

[BUF] LittleFS mounted, current buffer = 0 bytes
[DHT22] init on GPIO 4
[MQ2] init on GPIO 34 (12-bit ADC)
[BLE] advertising as 'IDP-345678'
[NET] using compile-time credentials (ssid=MyWifi)
[NET] connecting to 'MyWifi'...
[NET] connected: ip=192.168.1.42 rssi=-54
[NTP] synced: 2026-05-02 14:23:11 UTC
[MQTT] init host=e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud:8883 client_id=esp32-a4cf12345678
[DIAG] last reset reason: poweron

[MAIN] setup complete — entering main loop

[MQTT] connecting...
[MQTT] connected
[MQTT] published 'online' status
[BUF] drain complete — sent=0 kept=0 dropped=0
```

After that, you should see one DHT22 publish every 2 s and one
MQ2 aggregate publish every 5 s. Diagnostics arrive every 5 minutes.

---

## Topic structure published by this device

```
tenants/demo/sites/lab/devices/{client_id}/sensors/dht22/telemetry
tenants/demo/sites/lab/devices/{client_id}/sensors/mq2/telemetry
tenants/demo/sites/lab/devices/{client_id}/status
tenants/demo/sites/lab/devices/{client_id}/diagnostics
```

`{client_id}` is the value printed at boot (derived from the ESP32's
factory MAC).

---

## HiveMQ ACL contract

In the HiveMQ Cloud console, create a credential and grant it **publish**
permission on:

```
tenants/demo/sites/lab/devices/+/#
```

Note the trailing `#` (multi-level wildcard). Using
`tenants/demo/sites/lab/devices/+/` (single-level wildcard, no `#`) is a
common and broken pattern — it matches *zero* topics because there's
nothing after the trailing slash.

Defense-in-depth: bind the ACL to require `client_id` to match the
device's own publish path. HiveMQ Cloud supports this via the `${client}`
substitution in the ACL — the credential can then only publish under its
own subtree even if compromised.

---

## BLE provisioning and live data

Service UUID: `12345678-1234-1234-1234-123456789abc`

| Characteristic UUID                            | Property      | Purpose                                                  |
|------------------------------------------------|---------------|----------------------------------------------------------|
| `12345678-1234-1234-1234-000000000001`         | read, notify  | Live sensor readings JSON, updated every 1 s             |
| `12345678-1234-1234-1234-000000000002`         | read          | Device status JSON (wifi/mqtt state, uptime, heap, ip)   |
| `12345678-1234-1234-1234-000000000003`         | write         | Wi-Fi provisioning: `{"ssid":"...","password":"..."}`    |

Use **nRF Connect** or **LightBlue** on a phone. Once you write to the
provisioning characteristic, the credentials are persisted to NVS via
`Preferences` and the device immediately attempts to reconnect with
them. On subsequent boots the NVS-stored credentials take precedence
over the compile-time defaults.

The device advertises continuously so the BLE channel is always
available, even when Wi-Fi is healthy.

BLE provisioning write payload example:

```
{"ssid":"MyWifi","password":"MyWifiPass"}
```

On successful write the device persists credentials to NVS and attempts
immediate reconnect. The device's serial log shows `[NET] connecting...`.

--

**Architecture (high level)**

- Sensors: `sensor_dht22` (DHT22 on GPIO4) and `sensor_mq2` (MQ2 analog
   via ADC GPIO34). Each module implements `begin()`/`tick()` and exposes
   latest values to the BLE service.
- Local buffer: `buffer` stores NDJSON telemetry entries in LittleFS when
   MQTT is unavailable; `drain()` replays entries on connect.
- Connectivity: `netmgr` manages Wi‑Fi, persists NVS credentials written
   from BLE provisioning, and performs NTP sync for TLS validation.
- MQTT layer: `mqttmgr` wraps `WiFiClientSecure` + `PubSubClient` and
   handles LWT, publish buffering, and drain-on-connect. (See Known Gaps
   below regarding command subscriptions.)
- OTA: `ota` contains a partitioned-update state machine and HMAC
   verification scaffolding; see OTA section for expected message schema.

Data flow summary:

- Sensors -> `mqttmgr::publish(topic,payload)` -> (connected) -> Broker
   OR -> (disconnected) -> `buffer::append()` (LittleFS)
- BLE phone -> provisioning write -> `netmgr::setCredentials()` -> NVS
   -> Wi‑Fi reconnect
- On MQTT connect -> `mqttmgr` publishes retained `status:online` and
   calls `buffer::drain()` to replay stored messages oldest-first.

--

**OTA (Over-The-Air) — expected behavior and payloads**

This firmware implements a safe partitioned OTA flow. The device
supports two update triggers:

1. Polling an HTTP endpoint (controlled by `OTA_POLLING_INTERVAL_SECONDS`).
2. Push command via MQTT (recommended for production).

Current code notes: the README documents the intended MQTT command topic
but the codebase currently lacks a subscription hookup to forward incoming
MQTT payloads into `ota::onUpdateCommand()`; this is a documented TODO.

Recommended OTA command topic (example):

```
tenants/demo/sites/lab/devices/{client_id}/commands/ota/update
```

Expected JSON payload schema (push):

```
{
   "url": "https://example.com/firmware/esp32-edge-1.2.0.bin",
   "version": "1.2.0",
   "signature": "<hex-encoded-hmac-sha256>",
   "chunk_size": 4096
}
```

- `url` (string): HTTPS URL where the firmware binary can be downloaded.
- `version` (string): Semantic version of the new firmware.
- `signature` (string): Hex-encoded HMAC-SHA256 computed over the binary
   using `OTA_SIGNATURE_KEY` (device-side) — **verification must be
   implemented server and client-side**.
- `chunk_size` (int, optional): preferred chunk size for streaming; the
   firmware streams to the alternate partition in blocks and verifies HMAC
   after complete download.

Behavior on receiving an OTA command:

- Validate JSON fields and `version` is newer than `FW_VERSION`.
- Download the file to the inactive partition, streaming to avoid OOM.
- Compute HMAC-SHA256 over the downloaded bytes and compare to
   `signature`. If verification passes, set new partition and reboot.
- If boot fails more than `OTA_ROLLBACK_BOOT_THRESHOLD` times, auto
   rollback occurs.

Known gap: `ota.cpp` contains HMAC scaffolding but the HMAC verification
appears incomplete — treat OTA as experimental until verification is
confirmed. See Developer Notes for the follow-up tasks.

--

**Security guidance**

- Never commit `src/config.local.h` or real `OTA_SIGNATURE_KEY` to Git.
- Prefer provisioning secrets via a secure provisioning server or
   manufacturing step; consider using an HSM or secure element for key
   storage on production devices.
- If you must embed keys in firmware for prototyping, rotate them before
   production and ensure broker ACLs limit publish scope to `tenants/...`.
- Ensure NTP sync completes before attempting TLS connections; otherwise
   certificate validation will fail.

--

**Diagnostics & Testing**

Example `mosquitto_pub` to publish an OTA push (replace placeholders):

```bash
mosquitto_pub -h <broker> -p 8883 --cafile /path/to/ca.pem \
   -u "MQTT_USERNAME" -P "MQTT_PASSWORD" \
   -t "tenants/demo/sites/lab/devices/esp32-<client_id>/commands/ota/update" \
   -m '{"url":"https://.../fw.bin","version":"1.2.0","signature":"..."}'
```

Simulate offline buffering by disabling Wi‑Fi on your router for 30s and
observing `[BUF] append` and subsequent `[BUF] drain` logs after network
restoration.

--

**Known gaps & TODOs**

- MQTT subscriptions for backend commands (OTA push) are not wired in
   `mqttmgr.cpp`; add `PubSubClient::setCallback()` and topic subscriptions
   during `mqttmgr::onConnect()` to route messages to `ota::onUpdateCommand()`.
- `ota.cpp` contains placeholder/partial HMAC verification functions
   (`initHmac()` / `verifySignature()`) — implement full `mbedtls_md_hmac`
   verification using `OTA_SIGNATURE_KEY`.
- Add `src/config.local.h.example` to speed onboarding (added in this
   commit).

--

The remainder of the README (Wiring table, Troubleshooting, Layout)
remains valid — see below for the original content.

---

## Troubleshooting MQTT connect failures

When the serial log shows `[MQTT] connect failed rc=N (...)`:

| rc  | Meaning                                  | Likely cause / fix                                                                                  |
|-----|------------------------------------------|-----------------------------------------------------------------------------------------------------|
| -4  | Connection timeout                       | Broker unreachable. Verify `MQTT_HOST` is correct and DNS resolves; check outbound 8883 firewall.   |
| -3  | Connection lost mid-handshake            | Network instability or broker dropped the socket. Will retry with backoff; usually self-healing.    |
| -2  | TLS handshake or socket connect failed   | Wrong CA cert, NTP not synced (cert date check fails), or wrong port. Confirm `[NTP] synced` log.   |
| -1  | Client disconnected cleanly              | Normal — typically follows a client-side `disconnect()` or a Wi-Fi drop.                            |
| 1   | Bad MQTT protocol version                | Broker requires v5; PubSubClient only speaks v3.1.1. Switch broker setting to allow v3.1.1.         |
| 2   | Client ID rejected                       | Client ID empty/too long, or another session is already connected with the same ID. Reboot/rotate.  |
| 3   | Server unavailable                       | Broker temporarily refusing new connections. Check HiveMQ Cloud status page.                        |
| 4   | Bad username or password                 | `MQTT_USERNAME` / `MQTT_PASSWORD` mismatch with the broker credential. Re-create the device user.   |
| 5   | Not authorized — check ACL               | Auth succeeded but ACL denies the publish. Verify the ACL pattern above (note the `#` wildcard).    |

---

## Resilience behavior to verify

1. **Buffering** — pull the Wi-Fi router for 30 s. Telemetry messages
   accumulate in `/buffer.ndjson`. When Wi-Fi returns, the serial log
   shows `[BUF] draining...` and the broker receives every queued
   message in order.
2. **LWT** — yank USB power for 5 s. Within ~60 s (one MQTT keep-alive
   interval), subscribers to the device's `status` topic receive the
   retained `{"status":"offline","ts":...}` message.
3. **Watchdog** — uncomment `delay(31000)` somewhere in `loop()` for a
   single test build. The device will reboot and the next
   `[DIAG] last reset reason:` log line will show `task_wdt`.

---

## Layout

```
esp32-edge/
├── platformio.ini
├── README.md
├── .gitignore
└── src/
    ├── main.cpp           setup() / loop() orchestration
    ├── config.h           credentials, broker, CA cert
    ├── sensor_dht22.{h,cpp}
    ├── sensor_mq2.{h,cpp}
    ├── netmgr.{h,cpp}     Wi-Fi + NTP + NVS provisioning
    ├── mqttmgr.{h,cpp}    TLS + MQTT + LWT + publish wrapper
    ├── buffer.{h,cpp}     LittleFS NDJSON ring buffer
    ├── blesvc.{h,cpp}     NimBLE GATT service
    └── diag.{h,cpp}       periodic diagnostics publish
```
