// diag.h — periodic diagnostics publish (every 5 minutes)
//
// Responsibility: pull error counters, heap stats, RSSI, uptime and the
// last reset reason into one envelope and ship it to the diagnostics
// topic. Captured once at boot so the reset reason reflects this boot,
// not the last diagnostic cycle.

#pragma once

namespace diag {

void begin();
void tick();

}  // namespace diag
