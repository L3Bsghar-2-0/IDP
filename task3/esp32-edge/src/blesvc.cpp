// blesvc.cpp — see blesvc.h

#include "blesvc.h"
#include <NimBLEDevice.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"
#include "netmgr.h"
#include "mqttmgr.h"
#include "sensor_dht22.h"
#include "sensor_mq2.h"

namespace blesvc {

// Service + characteristic UUIDs. Three characteristics, all under one
// service so a phone only has to discover one thing.
static constexpr const char* SVC_UUID  = "12345678-1234-1234-1234-123456789abc";
static constexpr const char* CHR_LIVE  = "12345678-1234-1234-1234-000000000001";
static constexpr const char* CHR_STAT  = "12345678-1234-1234-1234-000000000002";
static constexpr const char* CHR_PROV  = "12345678-1234-1234-1234-000000000003";

static String                  s_clientId;
static NimBLEServer*           s_server     = nullptr;
static NimBLECharacteristic*   s_charLive   = nullptr;
static NimBLECharacteristic*   s_charStat   = nullptr;
static NimBLECharacteristic*   s_charProv   = nullptr;

static uint32_t s_lastUpdateMs = 0;
static bool     s_advertising  = false;

// Provisioning callback. Accepts JSON {"ssid":"...","password":"..."}.
// Validation is intentionally minimal — Wi-Fi will tell us if the creds
// are wrong by failing to associate, and we already have backoff for that.
class ProvCallback : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* chr) override {
        const std::string val = chr->getValue();
        Serial.printf("[BLE] prov write (%u bytes)\n",
                      static_cast<unsigned>(val.size()));

        JsonDocument doc;
        const DeserializationError err = deserializeJson(doc, val);
        if (err) {
            Serial.printf("[BLE] prov parse error: %s\n", err.c_str());
            return;
        }
        const char* ssid = doc["ssid"];
        const char* pass = doc["password"];
        if (!ssid || strlen(ssid) == 0 || strlen(ssid) > 32) {
            Serial.println("[BLE] prov rejected: invalid ssid");
            return;
        }
        if (!pass || strlen(pass) > 63) {
            Serial.println("[BLE] prov rejected: invalid password");
            return;
        }
        netmgr::setCredentials(String(ssid), String(pass));
    }
};

class ServerCallback : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer*) override {
        Serial.println("[BLE] client connected");
    }
    void onDisconnect(NimBLEServer* s) override {
        Serial.println("[BLE] client disconnected");
        // NimBLE pauses advertising while a peer is connected; restart it
        // so the next phone can find us.
        s->startAdvertising();
        s_advertising = true;
    }
};

static String shortDeviceName(const String& clientId) {
    // BLE advertising names are length-limited; "esp32-aabbccddeeff" is
    // already over the safe 22-byte budget for some scanner UIs. Keep
    // the last 6 hex chars.
    if (clientId.length() < 6) return clientId;
    return String("IDP-") + clientId.substring(clientId.length() - 6);
}

void begin(const String& clientId) {
    s_clientId = clientId;

    NimBLEDevice::init(shortDeviceName(clientId).c_str());
    // Negotiate a higher MTU so the live-data JSON (~150 bytes) fits in
    // a single notify packet on phones that accept it.
    NimBLEDevice::setMTU(247);

    s_server = NimBLEDevice::createServer();
    if (!s_server) {
        Serial.println("[BLE] createServer failed");
        return;
    }
    s_server->setCallbacks(new ServerCallback());

    NimBLEService* svc = s_server->createService(SVC_UUID);
    if (!svc) {
        Serial.println("[BLE] createService failed");
        return;
    }

    s_charLive = svc->createCharacteristic(
        CHR_LIVE, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
    if (!s_charLive) {
        Serial.println("[BLE] createCharacteristic live failed");
        return;
    }
    s_charLive->setValue("{}");

    s_charStat = svc->createCharacteristic(
        CHR_STAT, NIMBLE_PROPERTY::READ);
    if (!s_charStat) {
        Serial.println("[BLE] createCharacteristic stat failed");
        return;
    }
    s_charStat->setValue("{}");

    s_charProv = svc->createCharacteristic(
        CHR_PROV, NIMBLE_PROPERTY::WRITE);
    if (!s_charProv) {
        Serial.println("[BLE] createCharacteristic prov failed");
        return;
    }
    s_charProv->setCallbacks(new ProvCallback());

    svc->start();

    NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
    if (!adv) {
        Serial.println("[BLE] getAdvertising failed");
        return;
    }
    adv->addServiceUUID(SVC_UUID);
    adv->setScanResponse(true);
    NimBLEDevice::startAdvertising();
    s_advertising = true;

    Serial.printf("[BLE] advertising as '%s'\n",
                  shortDeviceName(clientId).c_str());
}

static String buildLivePayload() {
    JsonDocument doc;
    doc["device_id"] = s_clientId;
    doc["ts"]        = (uint32_t)time(nullptr);

    float t, h;
    if (dht22::getLatest(t, h)) {
        JsonObject d = doc["dht22"].to<JsonObject>();
        d["temp_c"]  = t;
        d["hum"]     = h;
    }

    int   mn, mx;
    float mean, stddev;
    if (mq2::getLatestStats(mn, mx, mean, stddev)) {
        JsonObject g    = doc["gas_level"].to<JsonObject>();
        g["raw_min"]    = mn;
        g["raw_max"]    = mx;
        g["raw_mean"]   = mean;
        g["raw_stddev"] = stddev;
    }

    String s;
    serializeJson(doc, s);
    return s;
}

static String buildStatusPayload() {
    JsonDocument doc;
    doc["client_id"]  = s_clientId;
    doc["fw"]         = FW_VERSION;
    doc["wifi_state"] = netmgr::isConnected() ? "connected" : "disconnected";
    doc["mqtt_state"] = mqttmgr::isConnected() ? "connected" : "disconnected";
    doc["uptime_s"]   = (uint32_t)(millis() / 1000);
    doc["heap_free"]  = (uint32_t)ESP.getFreeHeap();
    doc["ip"]         = netmgr::isConnected() ? netmgr::ipAddress() : String("");

    String s;
    serializeJson(doc, s);
    return s;
}

void tick() {
    const uint32_t now = millis();

    if ((now - s_lastUpdateMs) >= 1000) {
        s_lastUpdateMs = now;

        if (s_charLive) {
            const String live = buildLivePayload();
            s_charLive->setValue(live.c_str());
            s_charLive->notify();
        }
        if (s_charStat) {
            const String stat = buildStatusPayload();
            s_charStat->setValue(stat.c_str());
        }
    }

    // Spec: advertise whenever Wi-Fi is disconnected so the user can
    // re-provision in the field. We keep advertising on continuously
    // (it's cheap and means a phone can also watch live data even when
    // Wi-Fi is fine) but explicitly re-arm if NimBLE has stopped it.
    if (!netmgr::isConnected() && !s_advertising) {
        NimBLEDevice::startAdvertising();
        s_advertising = true;
    }
}

}  // namespace blesvc
