# APR Optimization Gateway

Standalone Docker service for testing an APR-based MQTT optimization gateway.

## Flow

```text
MQTT input topic -> APR policy decision -> APR envelope encoding -> MQTT output topic
```

Default topics:

- Input: `iot/raw/#`
- Output: `iot/optimized/#`

## Run

```powershell
cd C:\access\iot\apr_gateway
docker compose up --build
```

## APIs

- `GET /health`
- `GET /api/metrics`
- `GET /api/policies/current`
- `POST /api/recommend`

Example recommendation request:

```json
{
  "topic": "iot/raw/temperature/temp_001",
  "payload_size": 2048,
  "latency_ms": 10,
  "queue_depth": 0,
  "schema_type": "defined_sensor",
  "sensitive": false
}
```

## Optional ML Model

Place these files in `models/` to enable the XGBoost APR model:

- `models/xgb_model.joblib`
- `models/xgb_model_meta.json`

If the model is missing or fails to load, the gateway uses a rule-based fallback.
