// config.h — credentials, broker, topic roots, broker CA cert
//
// Edit only the placeholder values below. Do not commit real credentials;
// for local overrides, create src/config.local.h (gitignored) and include
// it from this file.

#pragma once

// ── Wi-Fi defaults (overridden at runtime by NVS-stored credentials) ──
#define WIFI_SSID     "PLACEHOLDER_WIFI_SSID"
#define WIFI_PASSWORD "PLACEHOLDER_WIFI_PASSWORD"

// ── HiveMQ Cloud broker ──────────────────────────────────────────────
#define MQTT_HOST     "e9a3ce30ae3749ab880436548931b5d0.s1.eu.hivemq.cloud"
#define MQTT_PORT     8883                       // MQTT over TLS (TCP)
#define MQTT_USERNAME "esp32-device"
#define MQTT_PASSWORD "esp32-device"

// Note: port 8884 is the same broker's MQTT-over-WebSocket endpoint,
// reserved for browser clients. The ESP32 firmware uses 8883 (TCP/TLS)
// because PubSubClient does not speak the WebSocket framing.

// ── Topic hierarchy (must match broker ACL) ──────────────────────────
#define TENANT        "demo"
#define SITE          "lab"

// ── Optional client-id override (default: derived from MAC) ──────────
// #define CLIENT_ID_OVERRIDE "esp32-test-01"

// ── Firmware version (reported in payloads + diagnostics) ────────────
#define FW_VERSION    "1.0.0"

// ── OTA (Over-The-Air) update settings ───────────────────────────────
// Polling interval (in seconds) for checking updates. Set to 0 to disable polling.
#define OTA_POLLING_INTERVAL_SECONDS 3600    // 1 hour default

// Boot threshold for auto-rollback: if device fails to boot this many times
// in a row, it automatically reverts to the previous firmware partition.
#define OTA_ROLLBACK_BOOT_THRESHOLD  3

// HMAC-SHA256 secret for firmware signature verification.
// IMPORTANT: Change this to your own secret and pre-share with OTA backend.
// Keep this synchronized across all devices. 32 hex characters (16 bytes).
#define OTA_SIGNATURE_KEY "0123456789abcdef0123456789abcdef"

// Sensor pins (ESP32) ───────────────────────────────────────────────
#define DHT22_PIN     4
#define MQ2_ADC_PIN   34

// ── Broker root CA — Let's Encrypt ISRG Root X1 ──────────────────────
// HiveMQ Cloud's broker certificate chains to this root. Replace if your
// broker uses a different CA. Pinning the root (not an intermediate)
// keeps the device working across cert renewals.
static const char BROKER_CA_PEM[] PROGMEM = R"PEM(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
)PEM";
