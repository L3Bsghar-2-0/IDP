// main.cpp — boot orchestration and the global tick loop.
//
// All real work lives in the per-module .cpp files. This file only:
//   1. derives the unique client ID,
//   2. brings up subsystems in the order their dependencies require
//      (sensors → BLE → Wi-Fi → NTP → MQTT → diagnostics),
//   3. runs each subsystem's tick() inside a non-blocking loop guarded
//      by the task watchdog.

#include <Arduino.h>
#include <WiFi.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "buffer.h"
#include "netmgr.h"
#include "mqttmgr.h"
#include "blesvc.h"
#include "diag.h"
#include "sensor_dht22.h"
#include "sensor_mq2.h"

static constexpr uint32_t WDT_TIMEOUT_S = 30;

// Build "esp32-XXXXXXXXXXXX" from the factory MAC, or honour the
// CLIENT_ID_OVERRIDE escape hatch from config.h.
static String deriveClientId() {
#ifdef CLIENT_ID_OVERRIDE
    return String(CLIENT_ID_OVERRIDE);
#else
    String mac = WiFi.macAddress();   // "AA:BB:CC:DD:EE:FF"
    mac.replace(":", "");
    mac.toLowerCase();
    return String("esp32-") + mac;
#endif
}

void setup() {
    Serial.begin(115200);
    delay(200);

    Serial.println();
    Serial.println("================================================");
    Serial.println("  ESP32 IDP Edge Firmware  v" FW_VERSION);
    Serial.println("================================================");

    // STA mode is required before WiFi.macAddress() returns a real value.
    WiFi.mode(WIFI_STA);

    const String clientId = deriveClientId();
    Serial.printf("\n>>> CLIENT_ID = %s <<<\n", clientId.c_str());
    Serial.println("    (use this for HiveMQ ACL configuration)\n");

    // Storage first — buffer needs LittleFS up before the first publish.
    if (!buffer::begin()) {
        Serial.println("[MAIN] WARNING: offline buffer unavailable");
    }

    // Sensor I/O pins.
    dht22::begin();
    mq2::begin();

    // BLE before Wi-Fi so that a phone can already see the device while
    // it's still trying to associate with an AP.
    blesvc::begin(clientId);

    // Bring Wi-Fi up. begin() is non-blocking; we poll for up to 20 s
    // before continuing so NTP and MQTT have something to talk over.
    netmgr::begin(clientId.c_str());
    const uint32_t wifiDeadline = millis() + 20000;
    while (!netmgr::isConnected() && millis() < wifiDeadline) {
        netmgr::tick();
        delay(100);
    }

    // NTP must succeed before TLS, otherwise the broker certificate's
    // "not before" date check will fail. If we don't have Wi-Fi yet,
    // sync deferred to the loop.
    if (netmgr::isConnected()) {
        netmgr::waitForNtp(15000);
    } else {
        Serial.println("[MAIN] no Wi-Fi yet — NTP and MQTT will start later");
    }

    // MQTT registers its topic strings; first connect attempt happens in
    // the loop's first tick().
    mqttmgr::begin(clientId);

    diag::begin();

    // Watchdog comes online last so a slow setup() can't trip it.
    esp_task_wdt_init(WDT_TIMEOUT_S, /*panic=*/true);
    esp_task_wdt_add(NULL);

    Serial.println("\n[MAIN] setup complete — entering main loop\n");
}

void loop() {
    // Every iteration must reach this line within WDT_TIMEOUT_S, otherwise
    // the device reboots and diag::begin() will report "task_wdt" on the
    // next boot.
    esp_task_wdt_reset();

    netmgr::tick();

    // If Wi-Fi only came up after setup(), sync NTP opportunistically.
    if (netmgr::isConnected() && !netmgr::ntpSynced()) {
        netmgr::waitForNtp(5000);
    }

    mqttmgr::tick();
    dht22::tick();
    mq2::tick();
    diag::tick();
    blesvc::tick();

    // yield() lets the FreeRTOS scheduler service Wi-Fi and BLE stacks
    // without imposing a fixed delay on the loop's response time.
    yield();
}
