# ESP32 Edge Firmware — IDP Project

Firmware for an ESP32-WROOM-32 dev board that samples a DHT22
temperature/humidity sensor and an MQ2 gas sensor, validates and aggregates
the readings, and publishes JSON telemetry over TLS-secured MQTT to a
HiveMQ Cloud broker. Includes a LittleFS-backed offline ring buffer for
network outages, a NimBLE GATT service for Wi-Fi provisioning and live
monitoring from a phone, and a 5-minute diagnostics topic for fleet
health visibility.

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
