-- ReTeqFusion IoT — initial schema
-- TimescaleDB extension and base tables

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- TELEMETRY (DHT22 + MQ-2 sensor readings, one row per reading_key per message)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry (
    time              TIMESTAMPTZ NOT NULL,
    tenant            TEXT        NOT NULL,
    site              TEXT        NOT NULL,
    device_id         TEXT        NOT NULL,
    sensor_id         TEXT        NOT NULL,
    sensor_type       TEXT        NOT NULL,    -- 'dht22' or 'mq2'
    reading_key       TEXT        NOT NULL,    -- e.g. 'temperature', 'gas_ppm'
    value             DOUBLE PRECISION,
    unit              TEXT,
    quality           TEXT,
    seq               BIGINT,
    fw_version        TEXT,
    -- DHT22 enriched
    heat_index        DOUBLE PRECISION,
    absolute_humidity DOUBLE PRECISION,
    dew_point         DOUBLE PRECISION,
    comfort_index     TEXT,
    -- MQ-2 enriched
    hazard_level      TEXT,
    -- raw envelope
    raw_json          JSONB
);

SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_telemetry_device
    ON telemetry (device_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_sensor
    ON telemetry (sensor_type, reading_key, time DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_sensor
    ON telemetry (device_id, sensor_id, reading_key, time DESC);

-- ----------------------------------------------------------------------------
-- DLQ (dead-letter queue for messages that failed to parse/validate)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dlq (
    id            SERIAL PRIMARY KEY,
    received_at   TIMESTAMPTZ DEFAULT NOW(),
    topic         TEXT,
    error_type    TEXT,
    error_message TEXT,
    raw_payload   TEXT
);

CREATE INDEX IF NOT EXISTS idx_dlq_received_at ON dlq (received_at DESC);

-- ----------------------------------------------------------------------------
-- DEVICE STATUS (current online/offline + metadata)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_status (
    device_id  TEXT PRIMARY KEY,
    last_seen  TIMESTAMPTZ,
    status     TEXT,
    ip         TEXT,
    rssi       INTEGER,
    fw_version TEXT
);

-- ----------------------------------------------------------------------------
-- ANOMALIES (detection events from processing pipeline)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomalies (
    time          TIMESTAMPTZ NOT NULL,
    device_id     TEXT        NOT NULL,
    sensor_id     TEXT        NOT NULL,
    sensor_type   TEXT        NOT NULL,
    anomaly_type  TEXT        NOT NULL,
    confidence    DOUBLE PRECISION,
    description   TEXT,
    reading_value DOUBLE PRECISION
);

SELECT create_hypertable('anomalies', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_anomalies_device
    ON anomalies (device_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_type
    ON anomalies (anomaly_type, time DESC);

-- ----------------------------------------------------------------------------
-- GAS ALERTS (MQ-2 SMOKE / HAZARD events)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gas_alerts (
    time      TIMESTAMPTZ NOT NULL,
    device_id TEXT        NOT NULL,
    sensor_id TEXT        NOT NULL,
    level     TEXT        NOT NULL,    -- 'SMOKE' or 'HAZARD'
    gas_ppm   DOUBLE PRECISION
);

SELECT create_hypertable('gas_alerts', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_gas_alerts_device
    ON gas_alerts (device_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_gas_alerts_level
    ON gas_alerts (level, time DESC);

-- ----------------------------------------------------------------------------
-- DIAGNOSTICS (uptime, heap, rssi, mqtt_reconnects)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagnostics (
    time            TIMESTAMPTZ NOT NULL,
    device_id       TEXT        NOT NULL,
    uptime_s        BIGINT,
    free_heap       BIGINT,
    wifi_rssi       INTEGER,
    mqtt_reconnects INTEGER,
    dlq_buffered    INTEGER
);

SELECT create_hypertable('diagnostics', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_diagnostics_device
    ON diagnostics (device_id, time DESC);
