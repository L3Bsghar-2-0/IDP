// buffer.cpp — see buffer.h

#include "buffer.h"
#include <LittleFS.h>
#include <ArduinoJson.h>

namespace buffer {

static constexpr const char* BUFFER_PATH = "/buffer.ndjson";
static constexpr const char* TEMP_PATH   = "/buffer.tmp";
static constexpr size_t      MAX_BYTES   = 64UL * 1024UL;

bool begin() {
    // First try mounting without format so we don't wipe a healthy FS.
    if (LittleFS.begin(false)) {
        Serial.printf("[BUF] LittleFS mounted, current buffer = %u bytes\n",
                      static_cast<unsigned>(size()));
        return true;
    }
    Serial.println("[BUF] mount failed — formatting...");
    if (!LittleFS.begin(true)) {
        Serial.println("[BUF] format failed; offline buffering disabled");
        return false;
    }
    Serial.println("[BUF] LittleFS formatted and mounted");
    return true;
}

size_t size() {
    if (!LittleFS.exists(BUFFER_PATH)) return 0;
    File f = LittleFS.open(BUFFER_PATH, "r");
    if (!f) return 0;
    const size_t sz = f.size();
    f.close();
    return sz;
}

void append(const String& topic, const String& payload) {
    // Enforce cap by deleting and starting over. Truncating from the start
    // would be more correct (oldest-first eviction), but LittleFS does not
    // support in-place truncation cheaply, and the tradeoff (occasional
    // loss of the oldest 64 KB during prolonged outages) is acceptable
    // for telemetry where freshness matters more than completeness.
    if (size() >= MAX_BYTES) {
        Serial.printf("[BUF] cap reached (%u B) — rotating\n",
                      static_cast<unsigned>(MAX_BYTES));
        LittleFS.remove(BUFFER_PATH);
    }

    File f = LittleFS.open(BUFFER_PATH, "a");
    if (!f) {
        Serial.println("[BUF] append: open failed");
        return;
    }

    // One JSON object per line; keys are short to save flash bytes.
    JsonDocument doc;
    doc["t"] = topic;
    doc["p"] = payload;
    String line;
    serializeJson(doc, line);

    f.println(line);
    f.close();
    Serial.printf("[BUF] appended (%u B total)\n",
                  static_cast<unsigned>(size()));
}

void drain(PublishFn publish) {
    if (!LittleFS.exists(BUFFER_PATH)) return;

    File in = LittleFS.open(BUFFER_PATH, "r");
    if (!in) return;

    if (LittleFS.exists(TEMP_PATH)) LittleFS.remove(TEMP_PATH);
    File out = LittleFS.open(TEMP_PATH, "w");
    if (!out) {
        in.close();
        Serial.println("[BUF] drain: cannot create temp file");
        return;
    }

    Serial.println("[BUF] draining...");
    size_t sent = 0, kept = 0, dropped = 0;

    while (in.available()) {
        String line = in.readStringUntil('\n');
        line.trim();
        if (line.length() == 0) continue;

        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, line);
        if (err) {
            // Malformed line — drop rather than risk an infinite re-queue.
            dropped++;
            continue;
        }

        String t = doc["t"].as<String>();
        String p = doc["p"].as<String>();

        if (publish(t, p)) {
            sent++;
        } else {
            kept++;
            out.println(line);
        }
    }

    in.close();
    out.close();

    LittleFS.remove(BUFFER_PATH);
    if (kept > 0) {
        LittleFS.rename(TEMP_PATH, BUFFER_PATH);
    } else {
        LittleFS.remove(TEMP_PATH);
    }

    Serial.printf("[BUF] drain complete — sent=%u kept=%u dropped=%u\n",
                  static_cast<unsigned>(sent),
                  static_cast<unsigned>(kept),
                  static_cast<unsigned>(dropped));
}

}  // namespace buffer
