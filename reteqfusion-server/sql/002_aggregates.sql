-- Continuous aggregates for downsampled queries
--
-- Continuous aggregates require a separate transaction in TimescaleDB.
-- They are created idempotently with IF NOT EXISTS.

CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time)         AS bucket,
    tenant,
    site,
    device_id,
    sensor_id,
    sensor_type,
    reading_key,
    AVG(value)                            AS avg_value,
    MIN(value)                            AS min_value,
    MAX(value)                            AS max_value,
    COUNT(*)                              AS sample_count
FROM telemetry
GROUP BY bucket, tenant, site, device_id, sensor_id, sensor_type, reading_key
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)           AS bucket,
    tenant,
    site,
    device_id,
    sensor_id,
    sensor_type,
    reading_key,
    AVG(value)                            AS avg_value,
    MIN(value)                            AS min_value,
    MAX(value)                            AS max_value,
    COUNT(*)                              AS sample_count
FROM telemetry
GROUP BY bucket, tenant, site, device_id, sensor_id, sensor_type, reading_key
WITH NO DATA;

-- Refresh policies
SELECT add_continuous_aggregate_policy('telemetry_1min',
    start_offset => INTERVAL '2 hours',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE);

SELECT add_continuous_aggregate_policy('telemetry_1hour',
    start_offset => INTERVAL '3 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE);
