// netmgr.h — Wi-Fi station + NTP, with NVS-persisted credentials and
//            exponential-backoff reconnect.
//
// Responsibility: keep the device on Wi-Fi without ever calling delay()
// from the main loop, and provide a one-shot blocking NTP sync (used in
// setup() before TLS, since cert validation needs a real wall-clock).

#pragma once

#include <Arduino.h>

namespace netmgr {

void   begin(const char* hostname);
void   tick();

bool   isConnected();
bool   ntpSynced();
bool   waitForNtp(uint32_t timeoutMs);

int    rssi();
String ipAddress();

// Persist new credentials to NVS and trigger an immediate reconnect.
// Called from BLE provisioning.
void   setCredentials(const String& ssid, const String& password);

}  // namespace netmgr
