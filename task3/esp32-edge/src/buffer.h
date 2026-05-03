// buffer.h — LittleFS-backed offline ring buffer (NDJSON, 64 KB cap)
//
// Responsibility: persist (topic, payload) pairs to flash when the broker
// is unreachable, and replay them oldest-first on reconnect. Survives
// power loss. Rotates by deletion when the cap is reached.

#pragma once

#include <Arduino.h>
#include <functional>

namespace buffer {

using PublishFn = std::function<bool(const String& topic, const String& payload)>;

// Mount LittleFS; format on first run if mount fails. Returns false only
// if formatting also fails (rare — flash hardware fault).
bool begin();

// Append one entry. Silently rotates if the file exceeds the cap.
void append(const String& topic, const String& payload);

// Replay every buffered entry through `publish`. Entries that fail to
// publish are kept in a temp file that replaces the buffer at the end of
// the drain. Successful entries are dropped. Idempotency is the caller's
// responsibility (we don't dedupe on the broker side).
void drain(PublishFn publish);

// Current on-disk size of the buffer file in bytes (0 if absent).
size_t size();

}  // namespace buffer
