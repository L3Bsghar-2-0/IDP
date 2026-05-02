// sensor_dht22.cpp — see sensor_dht22.h

#include "sensor_dht22.h"
#include <DHT.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <time.h>
#include "config.h"
#include "mqttmgr.h"

namespace dht22 {

static constexpr uint8_t  PIN          = DHT22_PIN;
static constexpr uint8_t  TYPE         = DHT22;
static constexpr uint32_t INTERVAL_MS  = 2000;
// DHT22 datasheet ranges: -40..80 °C, 0..100 % RH. We use the full
// datasheet range so legitimate extremes (e.g. cold-room deployments)
// are not rejected as "out of range". Tighten in config if your
// deployment guarantees a narrower envelope.
static constexpr float    TEMP_MIN     = -40.0f;
static constexpr float    TEMP_MAX     = 80.0f;
static constexpr float    HUM_MIN      = 0.0f;
static constexpr float    HUM_MAX      = 100.0f;

static DHT      s_dht(PIN, TYPE);
static uint32_t s_lastReadMs = 0;
static uint32_t s_seq        = 0;
static uint32_t s_errors     = 0;
static float    s_lastTemp   = NAN;
static float    s_lastHum    = NAN;

void begin() {
    s_dht.begin();
    Serial.printf("[DHT22] init on GPIO %u\n", PIN);
}

uint32_t errorCount() { return s_errors; }

bool getLatest(float& tempC, float& hum) {
    if (isnan(s_lastTemp)) return false;
    tempC = s_lastTemp;
    hum   = s_lastHum;
    return true;
}

// JSON envelope: matches schema v1 declared in <functional_requirements>.
static String buildPayload(float t, float h) {
    JsonDocument doc;
    doc["v"]            = "1";
    doc["device_id"]    = mqttmgr::clientId();
    doc["sensor_id"]    = "dht22-1";
    doc["sensor_type"]  = "dht22";
    doc["fw"]           = FW_VERSION;
    doc["ts"]           = (uint32_t)time(nullptr);
    doc["seq"]          = ++s_seq;
    doc["rssi"]         = WiFi.RSSI();
    doc["quality"]      = "good";

    JsonObject value = doc["value"].to<JsonObject>();
    value["temp_c"]  = t;
    value["hum"]     = h;

    String out;
    serializeJson(doc, out);
    return out;
}

void tick() {
    const uint32_t now = millis();
    if ((now - s_lastReadMs) < INTERVAL_MS) return;
    s_lastReadMs = now;

    const float t = s_dht.readTemperature();
    const float h = s_dht.readHumidity();

    // Three rejection paths, each counted in the log so chronic vs
    // intermittent issues are distinguishable.
    if (isnan(t) || isnan(h)) {
        s_errors++;
        Serial.printf("[DHT22] NaN read (errors=%u)\n", s_errors);
        return;
    }
    if (t < TEMP_MIN || t > TEMP_MAX) {
        s_errors++;
        Serial.printf("[DHT22] temp out of range %.1f°C (errors=%u)\n",
                      t, s_errors);
        return;
    }
    if (h < HUM_MIN || h > HUM_MAX) {
        s_errors++;
        Serial.printf("[DHT22] humidity out of range %.1f%% (errors=%u)\n",
                      h, s_errors);
        return;
    }

    s_lastTemp = t;
    s_lastHum  = h;

    const String payload = buildPayload(t, h);
    mqttmgr::publish(mqttmgr::topicDht22().c_str(), payload.c_str(),
                     /*qos=*/1, /*retain=*/false);
}

}  // namespace dht22
