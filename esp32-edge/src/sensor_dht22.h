// sensor_dht22.h — DHT22 temperature + humidity pipeline
//
// Responsibility: read the DHT22 every 2 s (its hardware-imposed minimum
// interval), validate against datasheet bounds and CRC failures, build
// the v1 JSON envelope, and hand it to mqttmgr::publish.

#pragma once

#include <Arduino.h>

namespace dht22 {

void     begin();
void     tick();

uint32_t errorCount();

// Latest accepted reading; returns false if no reading has succeeded yet.
// Used by blesvc to expose live data.
bool     getLatest(float& tempC, float& hum);

}  // namespace dht22
