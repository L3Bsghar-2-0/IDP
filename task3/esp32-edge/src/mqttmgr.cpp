// mqttmgr.cpp — see mqttmgr.h

#include "mqttmgr.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"
#include "buffer.h"
#include "netmgr.h"

namespace mqttmgr {

static constexpr uint32_t MIN_BACKOFF_MS = 2000;
static constexpr uint32_t MAX_BACKOFF_MS = 60000;

static WiFiClientSecure s_tls;
static PubSubClient     s_client(s_tls);

static String   s_clientId;
static String   s_topicDht22;
static String   s_topicMq2;
static String   s_topicStatus;
static String   s_topicDiagnostics;

static uint32_t s_backoffMs    = MIN_BACKOFF_MS;
static uint32_t s_lastAttempt  = 0;
static uint32_t s_pubFailures  = 0;

// Decode PubSubClient::state() into something a human can read in logs.
// The numeric codes are stable across PubSubClient versions.
static const char* decodeRc(int rc) {
    switch (rc) {
        case -4: return "connection timeout";
        case -3: return "connection lost mid-handshake";
        case -2: return "TLS handshake or socket connect failed";
        case -1: return "client disconnected cleanly";
        case  0: return "connected";
        case  1: return "bad MQTT protocol version";
        case  2: return "client ID rejected";
        case  3: return "server unavailable";
        case  4: return "bad username or password";
        case  5: return "not authorized — check ACL";
        default: return "unknown";
    }
}

const String& clientId()        { return s_clientId; }
const String& topicDht22()      { return s_topicDht22; }
const String& topicMq2()        { return s_topicMq2; }
const String& topicStatus()     { return s_topicStatus; }
const String& topicDiagnostics(){ return s_topicDiagnostics; }
uint32_t      pubFailCount()    { return s_pubFailures; }

static void buildTopics() {
    String base;
    base.reserve(96);
    base  = "tenants/";
    base += TENANT;
    base += "/sites/";
    base += SITE;
    base += "/devices/";
    base += s_clientId;

    s_topicDht22        = base + "/sensors/dht22/telemetry";
    s_topicMq2          = base + "/sensors/mq2/telemetry";
    s_topicStatus       = base + "/status";
    s_topicDiagnostics  = base + "/diagnostics";
}

static String buildLwtPayload() {
    JsonDocument doc;
    doc["status"] = "offline";
    doc["ts"]     = (uint32_t)time(nullptr);
    String s;
    serializeJson(doc, s);
    return s;
}

static String buildOnlinePayload() {
    JsonDocument doc;
    doc["status"] = "online";
    doc["fw"]     = FW_VERSION;
    doc["ts"]     = (uint32_t)time(nullptr);
    String s;
    serializeJson(doc, s);
    return s;
}

void begin(const String& clientId) {
    s_clientId = clientId;
    buildTopics();

    s_tls.setCACert(BROKER_CA_PEM);
    s_client.setServer(MQTT_HOST, MQTT_PORT);
    s_client.setKeepAlive(60);
    s_client.setBufferSize(1024);
    s_client.setSocketTimeout(10);

    Serial.printf("[MQTT] init host=%s:%u client_id=%s\n",
                  MQTT_HOST, (unsigned)MQTT_PORT, s_clientId.c_str());
}

static bool tryConnect() {
    // LWT must be passed at connect time — PubSubClient has no setWill()
    // accessor. Retain it so subscribers always see the device's last
    // known status even if they connect after the device is offline.
    const String lwt = buildLwtPayload();

    Serial.println("[MQTT] connecting...");
    const bool ok = s_client.connect(
        s_clientId.c_str(),
        MQTT_USERNAME, MQTT_PASSWORD,
        s_topicStatus.c_str(),  // willTopic
        1,                      // willQos
        true,                   // willRetain
        lwt.c_str(),            // willMessage
        true                    // cleanSession
    );

    if (!ok) {
        const int rc = s_client.state();
        Serial.printf("[MQTT] connect failed rc=%d (%s)\n", rc, decodeRc(rc));
        return false;
    }
    Serial.println("[MQTT] connected");

    // Replace the retained LWT with an "online" message immediately so
    // subscribers know we're alive before any telemetry arrives.
    const String online = buildOnlinePayload();
    s_client.publish(s_topicStatus.c_str(), online.c_str(), /*retain=*/true);
    Serial.println("[MQTT] published 'online' status");

    // Drain any messages that piled up while offline. The drain function
    // sends them through PubSubClient directly (not back through our own
    // publish() wrapper) so a transient failure during drain re-buffers
    // the unsent tail without re-buffering the already-sent prefix.
    buffer::drain([](const String& topic, const String& payload) -> bool {
        return s_client.publish(topic.c_str(),
                                reinterpret_cast<const uint8_t*>(payload.c_str()),
                                payload.length(),
                                /*retain=*/false);
    });
    return true;
}

void tick() {
    // Don't even attempt to talk to the broker until Wi-Fi is up.
    if (!netmgr::isConnected()) return;

    if (s_client.connected()) {
        s_client.loop();
        return;
    }

    const uint32_t now = millis();
    if ((now - s_lastAttempt) < s_backoffMs) return;
    s_lastAttempt = now;

    if (tryConnect()) {
        s_backoffMs = MIN_BACKOFF_MS;
    } else {
        uint32_t next = s_backoffMs * 2;
        if (next > MAX_BACKOFF_MS) next = MAX_BACKOFF_MS;
        s_backoffMs = next;
    }
}

bool isConnected() { return s_client.connected(); }

bool publish(const char* topic, const char* payload, int qos, bool retain) {
    // PubSubClient v2.8 silently treats QoS as 0 in publish(); the
    // willQos argument to connect() is the only place QoS is honored.
    // We document the intended QoS via the parameter even though the
    // wire QoS is 0 here. This is a known limitation of the library.
    (void)qos;

    if (!s_client.connected()) {
        s_pubFailures++;
        Serial.println("[MQTT] not connected → buffering");
        buffer::append(topic, payload);
        return false;
    }
    const bool ok = s_client.publish(
        topic,
        reinterpret_cast<const uint8_t*>(payload),
        strlen(payload),
        retain);
    if (!ok) {
        s_pubFailures++;
        Serial.printf("[MQTT] publish failed (state=%d) → buffering\n",
                      s_client.state());
        buffer::append(topic, payload);
    }
    return ok;
}

}  // namespace mqttmgr
