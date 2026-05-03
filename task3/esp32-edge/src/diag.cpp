// diag.cpp — see diag.h

#include "diag.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_system.h>
#include <WiFi.h>
#include <time.h>
#include "config.h"
#include "mqttmgr.h"
#include "ota.h"
#include "sensor_dht22.h"
#include "sensor_mq2.h"

namespace diag {

static constexpr uint32_t INTERVAL_MS = 5UL * 60UL * 1000UL;

static uint32_t            s_lastMs = 0;
static esp_reset_reason_t  s_resetReason = ESP_RST_UNKNOWN;

static const char* resetName(esp_reset_reason_t r) {
    switch (r) {
        case ESP_RST_POWERON:   return "poweron";
        case ESP_RST_EXT:       return "external";
        case ESP_RST_SW:        return "software";
        case ESP_RST_PANIC:     return "panic";
        case ESP_RST_INT_WDT:   return "int_wdt";
        case ESP_RST_TASK_WDT:  return "task_wdt";
        case ESP_RST_WDT:       return "other_wdt";
        case ESP_RST_DEEPSLEEP: return "deepsleep";
        case ESP_RST_BROWNOUT:  return "brownout";
        case ESP_RST_SDIO:      return "sdio";
        default:                return "unknown";
    }
}

void begin() {
    // Captured once — esp_reset_reason() returns the same value for the
    // whole boot, but caching avoids the call on every diagnostics cycle.
    s_resetReason = esp_reset_reason();
    Serial.printf("[DIAG] last reset reason: %s\n", resetName(s_resetReason));
}

static void publishDiagnostics() {
    JsonDocument doc;
    doc["v"]          = "1";
    doc["device_id"]  = mqttmgr::clientId();
    doc["fw"]         = FW_VERSION;
    doc["ts"]         = (uint32_t)time(nullptr);
    doc["uptime_s"]   = (uint32_t)(millis() / 1000);
    doc["heap_free"]  = (uint32_t)ESP.getFreeHeap();
    doc["heap_min"]   = (uint32_t)ESP.getMinFreeHeap();
    doc["rssi"]       = WiFi.RSSI();
    doc["reset"]      = resetName(s_resetReason);

    JsonObject errs = doc["errors"].to<JsonObject>();
    errs["dht22"]    = dht22::errorCount();
    errs["mq2"]      = mq2::errorCount();
    errs["mqtt_pub"] = mqttmgr::pubFailCount();
    errs["ota"]      = ota::errorCount();

    // OTA diagnostics
    JsonObject ota_obj = doc["ota"].to<JsonObject>();
    ota_obj["state"]      = ota::stateName(ota::getState());
    ota_obj["version"]    = ota::currentVersion();
    ota_obj["boot_count"] = ota::bootCount();
    ota_obj["updates"]    = ota::updateCount();

    String payload;
    serializeJson(doc, payload);
    mqttmgr::publish(mqttmgr::topicDiagnostics().c_str(), payload.c_str(),
                     /*qos=*/1, /*retain=*/false);
}

void tick() {
    const uint32_t now = millis();
    if ((now - s_lastMs) >= INTERVAL_MS) {
        s_lastMs = now;
        publishDiagnostics();
    }
}

}  // namespace diag
