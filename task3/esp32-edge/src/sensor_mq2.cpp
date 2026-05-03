// sensor_mq2.cpp — see sensor_mq2.h

#include "sensor_mq2.h"
#include <ArduinoJson.h>
#include <WiFi.h>
#include <math.h>
#include <string.h>
#include <time.h>
#include "config.h"
#include "mqttmgr.h"

namespace mq2 {

static constexpr uint8_t  PIN                = MQ2_ADC_PIN;
// 10 Hz sampling — gas concentration drifts on the order of seconds, so
// 100 Hz would just oversample the same value and wear out flash via
// noisier aggregate stats. The 5 s aggregation window matches MQ2's
// step-response time per its datasheet.
static constexpr uint32_t SAMPLE_INTERVAL_MS = 100;
static constexpr uint32_t AGG_INTERVAL_MS    = 5000;
static constexpr int      ADC_MIN            = 0;
static constexpr int      ADC_MAX            = 4095;
static constexpr size_t   AGG_BUFFER_SIZE    = 50;       // 10 Hz × 5 s
static constexpr size_t   MEDIAN_WINDOW      = 5;

// Sliding-median filter state. We don't add to the aggregation buffer
// until the window is full — the first 4 samples after boot are warm-up.
static int    s_medWindow[MEDIAN_WINDOW] = {0};
static size_t s_medFilled                = 0;
static size_t s_medIdx                   = 0;

static int    s_aggBuf[AGG_BUFFER_SIZE];
static size_t s_aggCount = 0;

static uint32_t s_lastSampleMs = 0;
static uint32_t s_lastAggMs    = 0;
static uint32_t s_seq          = 0;
static uint32_t s_errors       = 0;

// Cached published stats for BLE consumers.
static bool  s_haveStats = false;
static int   s_lastMin   = 0, s_lastMax = 0;
static float s_lastMean  = 0.0f, s_lastStd = 0.0f;

void begin() {
    analogReadResolution(12);
    analogSetPinAttenuation(PIN, ADC_11db);
    Serial.printf("[MQ2] init on GPIO %u (12-bit ADC)\n", PIN);
    Serial.println("[MQ2] heater warming up — readings stabilize after ~3 min");
}

uint32_t errorCount() { return s_errors; }

bool getLatestStats(int& mn, int& mx, float& mean, float& stddev) {
    if (!s_haveStats) return false;
    mn     = s_lastMin;
    mx     = s_lastMax;
    mean   = s_lastMean;
    stddev = s_lastStd;
    return true;
}

// Insertion sort on 5 elements. Faster and smaller than std::nth_element
// for this size. Modifies a local copy.
static int median5(const int v[MEDIAN_WINDOW]) {
    int a[MEDIAN_WINDOW];
    memcpy(a, v, sizeof(a));
    for (size_t i = 1; i < MEDIAN_WINDOW; i++) {
        int  x = a[i];
        int  j = (int)i - 1;
        while (j >= 0 && a[j] > x) {
            a[j + 1] = a[j];
            j--;
        }
        a[j + 1] = x;
    }
    return a[MEDIAN_WINDOW / 2];
}

static void publishAggregate() {
    if (s_aggCount == 0) return;

    int     mn  = s_aggBuf[0];
    int     mx  = s_aggBuf[0];
    int64_t sum = 0;
    for (size_t i = 0; i < s_aggCount; i++) {
        const int v = s_aggBuf[i];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
        sum += v;
    }
    const float mean = (float)sum / (float)s_aggCount;

    float varSum = 0.0f;
    for (size_t i = 0; i < s_aggCount; i++) {
        const float d = (float)s_aggBuf[i] - mean;
        varSum += d * d;
    }
    const float stddev = sqrtf(varSum / (float)s_aggCount);

    s_lastMin   = mn;
    s_lastMax   = mx;
    s_lastMean  = mean;
    s_lastStd   = stddev;
    s_haveStats = true;

    JsonDocument doc;
    doc["v"]            = "1";
    doc["device_id"]    = mqttmgr::clientId();
    doc["sensor_id"]    = "mq2-1";
    doc["sensor_type"]  = "mq2";
    doc["fw"]           = FW_VERSION;
    doc["ts"]           = (uint32_t)time(nullptr);
    doc["seq"]          = ++s_seq;
    doc["rssi"]         = WiFi.RSSI();
    doc["quality"]      = "good";
    doc["unit"]         = "raw_adc";
    doc["gas_level"]    = mean;

    JsonObject stats = doc["stats"].to<JsonObject>();
    stats["raw_min"]    = mn;
    stats["raw_max"]    = mx;
    stats["raw_mean"]   = mean;
    stats["raw_stddev"] = stddev;
    stats["count"]      = (uint32_t)s_aggCount;

    String payload;
    serializeJson(doc, payload);
    mqttmgr::publish(mqttmgr::topicMq2().c_str(), payload.c_str(),
                     /*qos=*/1, /*retain=*/false);

    s_aggCount = 0;
}

void tick() {
    const uint32_t now = millis();

    if ((now - s_lastSampleMs) >= SAMPLE_INTERVAL_MS) {
        s_lastSampleMs = now;
        const int raw = analogRead(PIN);

        if (raw < ADC_MIN || raw > ADC_MAX) {
            s_errors++;
        } else {
            s_medWindow[s_medIdx] = raw;
            s_medIdx = (s_medIdx + 1) % MEDIAN_WINDOW;
            if (s_medFilled < MEDIAN_WINDOW) s_medFilled++;

            if (s_medFilled == MEDIAN_WINDOW && s_aggCount < AGG_BUFFER_SIZE) {
                s_aggBuf[s_aggCount++] = median5(s_medWindow);
            }
        }
    }

    if ((now - s_lastAggMs) >= AGG_INTERVAL_MS) {
        s_lastAggMs = now;
        publishAggregate();
    }
}

}  // namespace mq2
