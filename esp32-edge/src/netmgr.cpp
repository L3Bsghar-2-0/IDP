// netmgr.cpp — see netmgr.h

#include "netmgr.h"
#include <WiFi.h>
#include <Preferences.h>
#include <time.h>
#include "config.h"

namespace netmgr {

static constexpr uint32_t MIN_BACKOFF_MS     = 1000;
static constexpr uint32_t MAX_BACKOFF_MS     = 60000;
static constexpr uint32_t CONNECT_TIMEOUT_MS = 15000;

static String   s_ssid, s_pass;
static String   s_hostname;
static uint32_t s_backoffMs   = MIN_BACKOFF_MS;
static uint32_t s_lastAttempt = 0;
static bool     s_attempting  = false;
static bool     s_ntpSynced   = false;
static bool     s_connectedOnce = false;

// Pull credentials from NVS first; fall back to the compile-time defaults
// from config.h if the NVS slot is empty (i.e., never provisioned).
static void loadCredentials() {
    Preferences prefs;
    if (!prefs.begin("wifi", /*readOnly=*/true)) {
        s_ssid = WIFI_SSID;
        s_pass = WIFI_PASSWORD;
        Serial.println("[NET] NVS read failed — using compile-time creds");
        return;
    }
    String storedSsid = prefs.getString("ssid", "");
    String storedPass = prefs.getString("password", "");
    prefs.end();

    if (storedSsid.length() > 0) {
        s_ssid = storedSsid;
        s_pass = storedPass;
        Serial.printf("[NET] using NVS credentials (ssid=%s)\n", s_ssid.c_str());
    } else {
        s_ssid = WIFI_SSID;
        s_pass = WIFI_PASSWORD;
        Serial.printf("[NET] using compile-time credentials (ssid=%s)\n",
                      s_ssid.c_str());
    }
}

void begin(const char* hostname) {
    s_hostname = hostname;
    loadCredentials();
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(s_hostname.c_str());
    WiFi.setAutoReconnect(false);   // we handle backoff manually
    WiFi.persistent(false);         // don't write SSID to flash on every begin()
    WiFi.begin(s_ssid.c_str(), s_pass.c_str());
    s_lastAttempt = millis();
    s_attempting  = true;
    Serial.printf("[NET] connecting to '%s'...\n", s_ssid.c_str());
}

void setCredentials(const String& ssid, const String& password) {
    Preferences prefs;
    if (!prefs.begin("wifi", false)) {
        Serial.println("[NET] NVS write failed — credentials NOT persisted");
        return;
    }
    prefs.putString("ssid", ssid);
    prefs.putString("password", password);
    prefs.end();

    s_ssid = ssid;
    s_pass = password;

    Serial.printf("[NET] new credentials persisted (ssid=%s) — reconnecting\n",
                  ssid.c_str());
    WiFi.disconnect(true, false);
    WiFi.begin(s_ssid.c_str(), s_pass.c_str());
    s_lastAttempt = millis();
    s_backoffMs   = MIN_BACKOFF_MS;
    s_attempting  = true;
}

void tick() {
    if (WiFi.status() == WL_CONNECTED) {
        if (s_attempting || !s_connectedOnce) {
            s_attempting    = false;
            s_connectedOnce = true;
            s_backoffMs     = MIN_BACKOFF_MS;
            Serial.printf("[NET] connected: ip=%s rssi=%d\n",
                          WiFi.localIP().toString().c_str(), WiFi.RSSI());
        }
        return;
    }

    const uint32_t now = millis();

    // While an attempt is in flight, give it the full timeout before
    // giving up. WiFi.status() going from CONNECTED back to anything
    // else also enters this branch.
    if (s_attempting && (now - s_lastAttempt) < CONNECT_TIMEOUT_MS) return;

    if ((now - s_lastAttempt) >= s_backoffMs) {
        Serial.printf("[NET] reconnect attempt (backoff was %u ms)\n",
                      s_backoffMs);
        WiFi.disconnect(true, false);
        WiFi.begin(s_ssid.c_str(), s_pass.c_str());
        s_lastAttempt = now;
        s_attempting  = true;

        // Double with jitter; cap at 60 s. Jitter prevents thundering-herd
        // reconnects when many devices share an outage.
        uint32_t next = s_backoffMs * 2;
        if (next > MAX_BACKOFF_MS) next = MAX_BACKOFF_MS;
        s_backoffMs = next + (uint32_t)random(0, 500);
        if (s_backoffMs > MAX_BACKOFF_MS) s_backoffMs = MAX_BACKOFF_MS;
    }
}

bool isConnected() { return WiFi.status() == WL_CONNECTED; }

bool waitForNtp(uint32_t timeoutMs) {
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    const uint32_t start = millis();
    while ((millis() - start) < timeoutMs) {
        const time_t now = time(nullptr);
        // Any timestamp after Nov 2023 means NTP succeeded; before that we
        // are still on the boot epoch (~1970).
        if (now > 1700000000) {
            s_ntpSynced = true;
            struct tm tmv;
            gmtime_r(&now, &tmv);
            char buf[32];
            strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &tmv);
            Serial.printf("[NTP] synced: %s UTC\n", buf);
            return true;
        }
        delay(200);   // setup-only path; loop() never calls this
    }
    Serial.println("[NTP] sync timeout — TLS will fail until clock is set");
    return false;
}

bool   ntpSynced()  { return s_ntpSynced; }
int    rssi()       { return WiFi.RSSI(); }
String ipAddress()  { return WiFi.localIP().toString(); }

}  // namespace netmgr
