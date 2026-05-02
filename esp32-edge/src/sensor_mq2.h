// sensor_mq2.h — MQ2 gas sensor (analog output) pipeline
//
// Responsibility: sample the MQ2's AO pin, reject ADC glitches with a
// median-of-5 filter, accumulate filtered values into a 5-second window,
// then publish min/max/mean/std as raw ADC counts.
//
// Note on ppm conversion: turning ADC counts into a parts-per-million
// reading requires per-unit R0 calibration (sensor resistance in clean
// air) plus a gas-specific curve that differs for LPG vs methane vs
// smoke. We publish raw ADC values and leave the curve fitting to the
// server, which can also re-calibrate without a firmware reflash.

#pragma once

#include <Arduino.h>

namespace mq2 {

void     begin();
void     tick();

uint32_t errorCount();

// Latest published-window stats; returns false until the first window
// has completed.
bool     getLatestStats(int& mn, int& mx, float& mean, float& stddev);

}  // namespace mq2
