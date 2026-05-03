# Changelog

2026-05-02 - Documentation update

- Expanded README with architecture diagram, OTA payload schema,
  diagnostics examples, and security guidance.
- Added `src/config.local.h.example` for safe local configuration.
- Documented known gaps: MQTT command subscription wiring and incomplete
  HMAC verification in `ota.cpp` (next steps: implement subscriptions and
  finish HMAC verification).
