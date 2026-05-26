-- phase2_schema.sql
-- MQTT Industrial IoT Platform - Phase 2 Experiment Log Schema

CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT,
    sensor_type TEXT,
    value REAL,
    unit TEXT,
    timestamp TEXT,
    topic TEXT,
    mode TEXT,
    experiment_id TEXT,
    seq INTEGER,
    publish_timestamp TEXT,
    received_timestamp TEXT,
    measured_latency REAL,
    payload_size INTEGER,
    qos INTEGER,
    compression TEXT,
    encryption TEXT,
    integrity TEXT
);

CREATE TABLE IF NOT EXISTS unknown_payload_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload_text TEXT NOT NULL,
    payload_size INTEGER NOT NULL,
    payload_type TEXT NOT NULL,
    error_message TEXT,
    received_at TEXT NOT NULL,
    experiment_id TEXT,
    seq INTEGER,
    publish_timestamp TEXT,
    received_timestamp TEXT,
    measured_latency REAL,
    qos INTEGER,
    compression TEXT,
    encryption TEXT,
    integrity TEXT
);

CREATE TABLE IF NOT EXISTS mqtt_experiment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT,
    topic TEXT,
    sensor_id TEXT,
    sensor_type TEXT,
    seq INTEGER,
    publish_timestamp TEXT,
    received_timestamp TEXT,
    measured_latency REAL,
    payload_size INTEGER,
    qos INTEGER,
    compression TEXT,
    encryption TEXT,
    integrity TEXT,
    apr_policy TEXT,
    predicted_latency REAL,
    is_unknown_schema INTEGER,
    payload_type TEXT,
    payload_text TEXT,
    platform_mode TEXT,
    policy_key TEXT,
    latency_ms REAL,
    schema_hash TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sensor_data_topic ON sensor_data(topic);
CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_id ON sensor_data(sensor_id);
CREATE INDEX IF NOT EXISTS idx_sensor_data_received ON sensor_data(received_timestamp);
CREATE INDEX IF NOT EXISTS idx_unknown_payload_topic ON unknown_payload_data(topic);
CREATE INDEX IF NOT EXISTS idx_unknown_payload_received_at ON unknown_payload_data(received_at);
CREATE INDEX IF NOT EXISTS idx_exp_log_experiment_id ON mqtt_experiment_log(experiment_id);
CREATE INDEX IF NOT EXISTS idx_exp_log_topic ON mqtt_experiment_log(topic);
CREATE INDEX IF NOT EXISTS idx_exp_log_received ON mqtt_experiment_log(received_timestamp);
CREATE INDEX IF NOT EXISTS idx_exp_log_policy_key ON mqtt_experiment_log(policy_key);
CREATE INDEX IF NOT EXISTS idx_exp_log_payload_type ON mqtt_experiment_log(payload_type);
