// blesvc.h — NimBLE GATT service for live data, status, and Wi-Fi
//            provisioning.
//
// Responsibility: keep BLE advertising up so a phone can always reach the
// device, push live sensor data over notify every 1 s, expose runtime
// status on read, and accept new Wi-Fi credentials over a write
// characteristic. Persists provisioning to NVS via netmgr.

#pragma once

#include <Arduino.h>

namespace blesvc {

void begin(const String& clientId);
void tick();

}  // namespace blesvc
