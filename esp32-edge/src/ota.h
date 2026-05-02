// ota.h — Over-The-Air firmware update with signature verification
//
// Responsibility: manage the OTA state machine (IDLE → CHECKING → DOWNLOADING →
// VERIFYING → FLASHING → REBOOTING), handle both push (MQTT command) and polling
// (periodic check) mechanisms, verify firmware signatures, and implement boot-count
// based auto-rollback on failed updates.
//
// Features:
//   • Dual-partition OTA (native ESP-IDF) with boot partition switching
//   • HMAC-SHA256 signature verification (configurable key in config.h)
//   • Push mechanism: subscribe to {client_id}/commands/ota/update MQTT topic
//   • Polling mechanism: optional periodic check for updates (configurable interval)
//   • Auto-rollback: tracks failed boot count per partition, reverts after N failures
//   • Non-blocking state machine (never stalls main loop or watchdog)
//   • Offline resilience: graceful abort on network loss mid-download

#pragma once

#include <Arduino.h>

namespace ota {

// State machine states for OTA operations
enum State {
    IDLE,        // Waiting for update request
    CHECKING,    // Checking for available updates (polling mode)
    DOWNLOADING, // Fetching firmware from MQTT topic
    VERIFYING,   // Validating HMAC-SHA256 signature
    FLASHING,    // Writing to alternate partition
    REBOOTING,   // Scheduling reboot into new firmware
    ERROR        // Update failed; error logged
};

void        begin();
void        tick();

// Query current OTA state (for diagnostics/UI)
State       getState();
const char* stateName(State s);

// Query version info (for diagnostics)
const char* currentVersion();
const char* lastAttemptedVersion();
uint32_t    bootCount();
uint32_t    updateCount();
uint32_t    errorCount();

// Trigger a poll for available updates (optional; polling also happens at
// configured interval automatically). Returns true if check was initiated.
bool        triggerCheck();

// MQTT message handler (called from mqttmgr when update command arrives)
// Payload format: { "url": "mqtt://...", "version": "X.Y.Z", "signature": "hex_string", "chunk_size": 4096 }
// Called from mqttmgr callback — should not block.
void        onUpdateCommand(const String& payload);

}  // namespace ota
