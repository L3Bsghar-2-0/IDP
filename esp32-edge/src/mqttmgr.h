// mqttmgr.h — MQTT-over-TLS connection, publish wrapper, LWT, topic
//             accessors. Drains the offline buffer on each fresh connect.
//
// Responsibility: own the WiFiClientSecure + PubSubClient pair, expose a
// single publish() entry point that transparently buffers on failure, and
// handle reconnect with bounded backoff. Topics are computed once in
// begin() and exposed via const-ref accessors so no string concatenation
// happens on the hot path.

#pragma once

#include <Arduino.h>

namespace mqttmgr {

void          begin(const String& clientId);
void          tick();

bool          isConnected();

// Returns true on success, false if buffered (or dropped if buffering
// also failed). QoS is honored as far as PubSubClient supports it
// (QoS 1 max — no QoS 2 in this library).
bool          publish(const char* topic, const char* payload,
                      int qos, bool retain);

const String& clientId();

// Pre-built topic strings (avoid per-publish String concatenation).
const String& topicDht22();
const String& topicMq2();
const String& topicStatus();
const String& topicDiagnostics();

uint32_t      pubFailCount();

}  // namespace mqttmgr
