-- Data retention policies

-- Keep raw telemetry for 30 days
SELECT add_retention_policy('telemetry',
    INTERVAL '30 days',
    if_not_exists => TRUE);

-- Keep raw anomalies for 90 days
SELECT add_retention_policy('anomalies',
    INTERVAL '90 days',
    if_not_exists => TRUE);

-- Keep gas alerts for 180 days
SELECT add_retention_policy('gas_alerts',
    INTERVAL '180 days',
    if_not_exists => TRUE);

-- Keep diagnostics for 30 days
SELECT add_retention_policy('diagnostics',
    INTERVAL '30 days',
    if_not_exists => TRUE);

-- Keep 1-min aggregates for 1 year
SELECT add_retention_policy('telemetry_1min',
    INTERVAL '365 days',
    if_not_exists => TRUE);
