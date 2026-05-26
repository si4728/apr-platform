-- Phase 3: Unknown Payload Schema Fingerprint Extension

ALTER TABLE unknown_payload_data ADD COLUMN schema_hash TEXT;
ALTER TABLE sensor_data ADD COLUMN schema_hash TEXT;

CREATE TABLE IF NOT EXISTS unknown_schema_profile (
    schema_hash TEXT PRIMARY KEY,
    payload_type TEXT,
    first_topic TEXT,
    last_topic TEXT,
    schema_keys TEXT,
    key_count INTEGER,
    sample_payload_text TEXT,
    message_count INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT
);

CREATE INDEX IF NOT EXISTS idx_unknown_payload_schema_hash
ON unknown_payload_data(schema_hash);

CREATE INDEX IF NOT EXISTS idx_schema_profile_last_seen
ON unknown_schema_profile(last_seen);
