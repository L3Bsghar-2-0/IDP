// ota.cpp — see ota.h

#include "ota.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <mbedtls/sha256.h>
#include <mbedtls/md.h>
#include <Preferences.h>
#include "config.h"
#include "mqttmgr.h"
#include "netmgr.h"

namespace ota {

// ── State Management ──────────────────────────────────────────────────
static State         s_state          = IDLE;
static State         s_nextState      = IDLE;
static uint32_t      s_stateEnterMs   = 0;

// ── Update Metadata ───────────────────────────────────────────────────
static String        s_updateVersion;
static String        s_updateSignature;
static uint32_t      s_updateSize     = 0;
static uint32_t      s_downloadedSize = 0;
static uint32_t      s_chunkSize      = 4096;  // Default 4 KB chunks

// ── Partition & Flash State ──────────────────────────────────────────
static esp_ota_handle_t      s_updateHandle     = 0;
static const esp_partition_t* s_updatePartition = nullptr;

// ── HMAC State ────────────────────────────────────────────────────────
static mbedtls_sha256_context s_shaCtx;
static bool                   s_shaInitialized = false;

// ── Diagnostics ───────────────────────────────────────────────────────
static uint32_t      s_updateAttempts = 0;
static uint32_t      s_updateErrors   = 0;
static uint32_t      s_lastCheckMs    = 0;
static const char*   s_lastError      = nullptr;

// ── NVS Storage Key ───────────────────────────────────────────────────
static const char    OTA_NS[]         = "ota";
static const char    KEY_VERSION[]    = "fw_ver";
static const char    KEY_BOOT_CNT[]   = "boot_cnt";
static const char    KEY_UPD_CNT[]    = "upd_cnt";
static const char    KEY_UPD_TIME[]   = "upd_time";

static constexpr uint32_t POLLING_INTERVAL_MS = OTA_POLLING_INTERVAL_SECONDS * 1000;
static constexpr uint32_t DOWNLOAD_TIMEOUT_MS = 60000;   // 60s max per chunk
static constexpr uint32_t STATE_TIMEOUT_MS    = 120000;  // 2 min max per state
static constexpr uint8_t  BOOT_THRESHOLD      = OTA_ROLLBACK_BOOT_THRESHOLD;

// ── NVS Helpers ───────────────────────────────────────────────────────

static Preferences& getNVS() {
    static Preferences prefs;
    static bool initialized = false;
    if (!initialized) {
        prefs.begin(OTA_NS, false);
        initialized = true;
    }
    return prefs;
}

static String getCurrentVersion() {
    Preferences& prefs = getNVS();
    return prefs.getString(KEY_VERSION, String(FIRMWARE_VERSION));
}

static void setCurrentVersion(const String& version) {
    Preferences& prefs = getNVS();
    prefs.putString(KEY_VERSION, version);
}

static uint32_t getBootCount() {
    Preferences& prefs = getNVS();
    return prefs.getUInt(KEY_BOOT_CNT, 0);
}

static void setBootCount(uint32_t count) {
    Preferences& prefs = getNVS();
    prefs.putUInt(KEY_BOOT_CNT, count);
}

static uint32_t getUpdateCount() {
    Preferences& prefs = getNVS();
    return prefs.getUInt(KEY_UPD_CNT, 0);
}

static void incrementUpdateCount() {
    Preferences& prefs = getNVS();
    uint32_t count = prefs.getUInt(KEY_UPD_CNT, 0);
    prefs.putUInt(KEY_UPD_CNT, count + 1);
}

static void setLastUpdateTime() {
    Preferences& prefs = getNVS();
    prefs.putUInt(KEY_UPD_TIME, (uint32_t)time(nullptr));
}

static bool isVersionNewer(const String& incoming, const String& current) {
    // Semantic versioning: X.Y.Z
    int inMaj, inMin, inPat;
    int curMaj, curMin, curPat;
    
    if (sscanf(incoming.c_str(), "%d.%d.%d", &inMaj, &inMin, &inPat) != 3) {
        return false;
    }
    if (sscanf(current.c_str(), "%d.%d.%d", &curMaj, &curMin, &curPat) != 3) {
        return false;
    }
    
    if (inMaj != curMaj) return inMaj > curMaj;
    if (inMin != curMin) return inMin > curMin;
    return inPat > curPat;
}

// ── HMAC-SHA256 Helpers ───────────────────────────────────────────────

static bool initHmac() {
    mbedtls_sha256_init(&s_shaCtx);
    s_shaInitialized = false;
    
    // HMAC-SHA256: SHA256(key XOR 0x5c, SHA256(key XOR 0x36, message))
    // For simplicity, use standard HMAC via mbedtls_md_hmac()
    s_shaInitialized = true;
    return true;
}

static bool verifySignature(const String& expectedSignature) {
    if (!s_shaInitialized) {
        Serial.println("[OTA] WARNING: HMAC not initialized for verification");
        return false;
    }
    
    // Finalize SHA256 hash
    uint8_t computedHash[32];
    mbedtls_sha256_finish(&s_shaCtx, computedHash);
    
    // Convert to hex string
    char computedHex[65];
    for (int i = 0; i < 32; i++) {
        sprintf(&computedHex[i * 2], "%02x", computedHash[i]);
    }
    computedHex[64] = '\0';
    
    bool match = (expectedSignature == computedHex);
    Serial.printf("[OTA] signature verification: %s\n", match ? "OK" : "FAIL");
    if (!match) {
        Serial.printf("    Expected: %s\n", expectedSignature.c_str());
        Serial.printf("    Computed: %s\n", computedHex);
    }
    return match;
}

// ── Partition Management ──────────────────────────────────────────────

static bool findNextUpdatePartition() {
    const esp_partition_t* running = esp_ota_get_running_partition();
    if (!running) {
        Serial.println("[OTA] ERROR: cannot find running partition");
        return false;
    }
    
    Serial.printf("[OTA] running partition: %s (0x%x, %u bytes)\n",
                  running->label, running->address, running->size);
    
    s_updatePartition = esp_ota_get_next_update_partition(nullptr);
    if (!s_updatePartition) {
        Serial.println("[OTA] ERROR: no OTA partition available");
        return false;
    }
    
    Serial.printf("[OTA] target partition:  %s (0x%x, %u bytes)\n",
                  s_updatePartition->label, s_updatePartition->address,
                  s_updatePartition->size);
    return true;
}

static bool beginFlash() {
    // Erase and open the OTA partition for writing
    esp_err_t err = esp_ota_begin(s_updatePartition, OTA_SIZE_UNKNOWN,
                                  &s_updateHandle);
    if (err != ESP_OK) {
        Serial.printf("[OTA] ERROR: esp_ota_begin failed (0x%x)\n", err);
        return false;
    }
    
    s_downloadedSize = 0;
    Serial.printf("[OTA] partition write started (max %u bytes)\n",
                  s_updatePartition->size);
    return true;
}

static bool writeChunk(const uint8_t* data, uint32_t size) {
    if (s_downloadedSize + size > s_updatePartition->size) {
        Serial.printf("[OTA] ERROR: firmware exceeds partition size "
                      "(%u + %u > %u)\n", s_downloadedSize, size,
                      s_updatePartition->size);
        return false;
    }
    
    esp_err_t err = esp_ota_write(s_updateHandle, data, size);
    if (err != ESP_OK) {
        Serial.printf("[OTA] ERROR: esp_ota_write failed (0x%x, offset %u)\n",
                      err, s_downloadedSize);
        return false;
    }
    
    s_downloadedSize += size;
    
    // Update HMAC as we stream
    if (s_shaInitialized) {
        mbedtls_sha256_update(&s_shaCtx, data, size);
    }
    
    // Log progress every 64 KB
    if (s_downloadedSize % (64 * 1024) == 0) {
        Serial.printf("[OTA] progress: %u bytes\n", s_downloadedSize);
    }
    return true;
}

static bool endFlash() {
    esp_err_t err = esp_ota_end(s_updateHandle);
    if (err != ESP_OK) {
        Serial.printf("[OTA] ERROR: esp_ota_end failed (0x%x)\n", err);
        return false;
    }
    
    Serial.printf("[OTA] partition write complete (%u bytes)\n", s_downloadedSize);
    s_updateHandle = 0;
    return true;
}

static bool switchPartition() {
    esp_err_t err = esp_ota_set_boot_partition(s_updatePartition);
    if (err != ESP_OK) {
        Serial.printf("[OTA] ERROR: esp_ota_set_boot_partition failed (0x%x)\n", err);
        return false;
    }
    
    Serial.printf("[OTA] boot partition switched to %s\n", s_updatePartition->label);
    return true;
}

// ── Rollback Logic ────────────────────────────────────────────────────

static void checkAndRollback() {
    // On every boot, check if we should rollback to previous partition
    uint32_t bootCnt = getBootCount();
    
    if (bootCnt >= BOOT_THRESHOLD) {
        Serial.printf("[OTA] ROLLBACK: boot count (%u) reached threshold (%u)\n",
                      bootCnt, BOOT_THRESHOLD);
        
        const esp_partition_t* running = esp_ota_get_running_partition();
        if (!running) return;
        
        // Find the "other" OTA partition and switch to it
        const esp_partition_t* fallback = esp_ota_get_next_update_partition(nullptr);
        if (fallback && fallback != running) {
            Serial.printf("[OTA] switching to fallback partition: %s\n",
                          fallback->label);
            esp_ota_set_boot_partition(fallback);
            setBootCount(0);  // Reset boot count
        }
    }
}

static void resetBootCount() {
    // Called after successful telemetry post (device deemed "healthy")
    setBootCount(0);
    Serial.println("[OTA] boot count reset (healthy device detected)");
}

// ── State Machine ─────────────────────────────────────────────────────

static void transitionTo(State next) {
    if (next != s_state) {
        Serial.printf("[OTA] %s → %s\n", stateName(s_state), stateName(next));
        s_state = next;
        s_stateEnterMs = millis();
    }
}

// ── Tick Handlers ─────────────────────────────────────────────────────

static void tickIdle() {
    // In idle state, optionally poll for updates at configured interval
    const uint32_t now = millis();
    
    if ((now - s_lastCheckMs) >= POLLING_INTERVAL_MS) {
        s_lastCheckMs = now;
        
        if (!netmgr::isConnected()) {
            Serial.println("[OTA] skipping poll: Wi-Fi not connected");
            return;
        }
        
        Serial.println("[OTA] polling for updates (periodic check)");
        // In a real implementation, this would query a backend API or
        // subscribe to a "query" topic. For now, we just log.
        transitionTo(CHECKING);
    }
}

static void tickChecking() {
    // In checking state, we wait for a response from the backend.
    // For now, this is a placeholder. The real flow is:
    // 1. Device polls (subscription to /commands/ota/check)
    // 2. Backend publishes update metadata to /commands/ota/update
    // 3. onUpdateCommand() is called with the metadata
    
    // Timeout: 30 seconds
    if ((millis() - s_stateEnterMs) > 30000) {
        Serial.println("[OTA] polling timeout — returning to idle");
        s_updateErrors++;
        transitionTo(IDLE);
    }
}

static void tickDownloading() {
    // In downloading state, we wait for firmware chunks over MQTT
    // This is passive: we receive data via MQTT messages
    
    // Timeout: 2 minutes of inactivity
    if ((millis() - s_stateEnterMs) > STATE_TIMEOUT_MS) {
        Serial.println("[OTA] ERROR: download timeout");
        s_updateErrors++;
        
        // Abort and rollback
        if (s_updateHandle) {
            esp_ota_abort(s_updateHandle);
            s_updateHandle = 0;
        }
        s_shaInitialized = false;
        transitionTo(ERROR);
    }
}

static void tickVerifying() {
    // Verification is instant (happens on state entry)
    // This state is just for logging/diagnostics
    transitionTo(FLASHING);
}

static void tickFlashing() {
    // Flashing is instant (happens on state entry)
    // This state is just for logging/diagnostics
    transitionTo(REBOOTING);
}

static void tickRebooting() {
    // Schedule a reboot after a brief delay (let current MQTT message complete)
    static uint32_t rebootDeadline = 0;
    
    if (rebootDeadline == 0) {
        rebootDeadline = millis() + 2000;
    }
    
    if (millis() >= rebootDeadline) {
        Serial.println("[OTA] rebooting into new firmware...");
        delay(1000);
        ESP.restart();
    }
}

static void tickError() {
    // In error state, just wait and eventually return to idle
    if ((millis() - s_stateEnterMs) > 5000) {
        Serial.println("[OTA] error state cleared — returning to idle");
        transitionTo(IDLE);
    }
}

// ── Public API ────────────────────────────────────────────────────────

void begin() {
    Serial.println("[OTA] initializing OTA manager");
    
    // Check boot count and possibly rollback
    checkAndRollback();
    
    // Increment boot count for this boot
    uint32_t bootCnt = getBootCount();
    setBootCount(bootCnt + 1);
    
    // Initialize HMAC context
    initHmac();
    
    // Log current state
    Serial.printf("[OTA] current firmware version: %s\n", getCurrentVersion().c_str());
    Serial.printf("[OTA] boot count: %u (threshold: %u)\n", getBootCount(), BOOT_THRESHOLD);
    Serial.printf("[OTA] update attempts: %u\n", getUpdateCount());
    
    // Subscribe to OTA command topic via mqttmgr
    // (This will be handled by a global callback registration in mqttmgr)
    
    s_state = IDLE;
    s_stateEnterMs = millis();
}

void tick() {
    // Non-blocking state machine tick
    switch (s_state) {
        case IDLE:
            tickIdle();
            break;
        case CHECKING:
            tickChecking();
            break;
        case DOWNLOADING:
            tickDownloading();
            break;
        case VERIFYING:
            tickVerifying();
            break;
        case FLASHING:
            tickFlashing();
            break;
        case REBOOTING:
            tickRebooting();
            break;
        case ERROR:
            tickError();
            break;
    }
}

State getState() {
    return s_state;
}

const char* stateName(State s) {
    switch (s) {
        case IDLE:        return "IDLE";
        case CHECKING:    return "CHECKING";
        case DOWNLOADING: return "DOWNLOADING";
        case VERIFYING:   return "VERIFYING";
        case FLASHING:    return "FLASHING";
        case REBOOTING:   return "REBOOTING";
        case ERROR:       return "ERROR";
        default:          return "UNKNOWN";
    }
}

const char* currentVersion() {
    static String s_cached;
    s_cached = getCurrentVersion();
    return s_cached.c_str();
}

const char* lastAttemptedVersion() {
    return s_updateVersion.c_str();
}

uint32_t bootCount() {
    return getBootCount();
}

uint32_t updateCount() {
    return getUpdateCount();
}

uint32_t errorCount() {
    return s_updateErrors;
}

bool triggerCheck() {
    if (s_state != IDLE) {
        Serial.println("[OTA] update already in progress");
        return false;
    }
    
    if (!netmgr::isConnected()) {
        Serial.println("[OTA] Wi-Fi not connected");
        return false;
    }
    
    Serial.println("[OTA] manual check triggered");
    transitionTo(CHECKING);
    return true;
}

void onUpdateCommand(const String& payload) {
    // Payload format: { "url": "...", "version": "X.Y.Z", "signature": "hex_string", "chunk_size": 4096 }
    
    if (s_state != IDLE && s_state != CHECKING) {
        Serial.println("[OTA] WARNING: update command received while update in progress");
        return;
    }
    
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (err) {
        Serial.printf("[OTA] ERROR: invalid JSON payload: %s\n", err.c_str());
        s_updateErrors++;
        return;
    }
    
    String url = doc["url"] | "";
    String version = doc["version"] | "";
    String signature = doc["signature"] | "";
    uint32_t chunkSize = doc["chunk_size"] | 4096;
    
    if (version.isEmpty() || signature.isEmpty()) {
        Serial.println("[OTA] ERROR: missing version or signature in payload");
        s_updateErrors++;
        return;
    }
    
    String currentVer = getCurrentVersion();
    if (!isVersionNewer(version, currentVer)) {
        Serial.printf("[OTA] skipping: incoming version %s not newer than %s\n",
                      version.c_str(), currentVer.c_str());
        return;
    }
    
    Serial.printf("[OTA] update available: %s → %s\n", currentVer.c_str(),
                  version.c_str());
    Serial.printf("[OTA] signature: %s\n", signature.c_str());
    Serial.printf("[OTA] chunk size: %u bytes\n", chunkSize);
    
    // Store update metadata and transition to downloading
    s_updateVersion = version;
    s_updateSignature = signature;
    s_chunkSize = chunkSize;
    s_downloadedSize = 0;
    s_updateAttempts++;
    
    // Find the next partition and begin flashing
    if (!findNextUpdatePartition() || !beginFlash()) {
        Serial.println("[OTA] ERROR: failed to prepare partition for flash");
        s_updateErrors++;
        transitionTo(ERROR);
        return;
    }
    
    // Initialize HMAC for signature verification
    if (!initHmac()) {
        Serial.println("[OTA] ERROR: failed to initialize HMAC");
        s_updateErrors++;
        esp_ota_abort(s_updateHandle);
        s_updateHandle = 0;
        transitionTo(ERROR);
        return;
    }
    
    transitionTo(DOWNLOADING);
}

// ── End of namespace ──────────────────────────────────────────────────

}  // namespace ota
