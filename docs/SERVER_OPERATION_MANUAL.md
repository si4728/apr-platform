# Server-Side Operation Manual

## Purpose

This manual describes how to operate the platform server in a real deployment environment. It focuses on runtime operation, not paper experiments.

The server-side platform is responsible for:

- running the Flask dashboard and REST APIs,
- connecting to MQTT broker,
- subscribing to telemetry topics,
- receiving and decoding APR envelopes,
- storing telemetry and runtime logs in SQLite,
- executing APR recommendation and policy push,
- monitoring queue, latency, schema, and broker state.

## Main Server File

```text
server.py
```

Run this file on the server host.

```powershell
cd C:\access\iot
python server.py
```

Default dashboard URL:

```text
http://localhost:5000
```

For other machines on the same network:

```text
http://<server-ip>:5000
```

## Required Server Files and Folders

| Path | Purpose |
|---|---|
| `server.py` | Main Flask/MQTT server |
| `config.json` | MQTT, sensor, APR, DB writer configuration |
| `iot_data.db` | SQLite runtime database |
| `policy/` | APR policy and codec logic |
| `database/db_manager.py` | Async DB writer |
| `monitor/queue_monitor.py` | Queue and topic-rate monitoring |
| `templates/` | Dashboard HTML |
| `static/` | Dashboard CSS/JS |
| `apr/xgb_model.joblib` | Optional trained APR model |
| `apr/xgb_model_meta.json` | Optional APR model metadata |

## Server Startup Sequence

When `server.py` starts, it performs the following sequence:

1. Load `config.json`.
2. Initialize SQLite database schema.
3. Enable SQLite WAL mode.
4. Start async DB writer.
5. Connect to MQTT broker.
6. Subscribe to:

```text
iot/sensor/#
```

7. Start Flask server on:

```text
0.0.0.0:5000
```

8. Serve dashboards and REST APIs.

## Server Shutdown

Use `Ctrl+C` in the server terminal.

On shutdown, the server attempts to:

- stop MQTT loop,
- disconnect MQTT client,
- flush and stop async DB writer.

Avoid killing the process abruptly during heavy ingestion because queued DB writes may be lost.

## Configuration File

Main configuration:

```text
config.json
```

Important sections:

```json
{
  "mqtt": {},
  "sensors": [],
  "platform": {}
}
```

## MQTT Configuration

Example:

```json
"mqtt": {
  "broker": "218.146.225.166",
  "port": 1883,
  "topic_prefix": "iot/sensor"
}
```

The server subscribes to:

```text
iot/sensor/#
```

The server ignores policy command topics when receiving telemetry:

```text
iot/sensor/policy/
```

## Distributed Broker Configuration

Multiple brokers can be configured:

```json
"brokers": [
  {
    "name": "primary",
    "host": "218.146.225.166",
    "port": 1883,
    "priority": 1,
    "enabled": true
  },
  {
    "name": "backup",
    "host": "192.168.0.20",
    "port": 1883,
    "priority": 2,
    "enabled": true
  }
]
```

The server attempts brokers in priority order.

## Platform Runtime Configuration

Important settings:

```json
"platform": {
  "enable_experiment_log": true,
  "enable_apr": true,
  "auto_apr": true,
  "apr_min_samples": 5,
  "apr_evaluation_interval_seconds": 30,
  "apr_skip_unchanged_policy": true,
  "apr_rollback_enabled": true,
  "apr_rollback_latency_increase_pct": 10,
  "publisher_queue_size": 1000,
  "publisher_retry_count": 1,
  "db_writer": {
    "batch_size": 100,
    "flush_interval": 0.1,
    "max_queue_size": 20000
  }
}
```

## APR Runtime Operation

APR consists of:

- metric collection,
- recommendation,
- policy push,
- feedback collection,
- rollback decision.

APR recommendation code:

```text
policy/apr_policy.py
```

Policy push topic:

```text
iot/sensor/policy/<sensor_id>
```

Example pushed policy:

```json
{
  "qos": 1,
  "compression": "zlib",
  "encryption": "AES-GCM",
  "integrity": "sha256"
}
```

## APR APIs

### Recommend Policy

```http
POST /api/apr/recommend
```

Example request:

```json
{
  "payload_size": 512,
  "network_latency_ms": 20,
  "queue_depth": 10,
  "topic": "iot/sensor/temperature/temp_001",
  "schema_type": "standard"
}
```

### Start Collection

```http
POST /api/apr/collection/start
```

### Evaluate Collection

```http
POST /api/apr/collection/evaluate
```

### Publish With Policy

```http
POST /api/apr/publish-with-policy
```

## APR Rollback

Rollback is controlled by:

```json
"apr_rollback_enabled": true,
"apr_rollback_latency_increase_pct": 10
```

If latency after policy deployment is worse than before by the configured percentage, the server pushes the previous policy back to the device.

Rollback events are stored in:

```text
apr_policy_log
```

## Codec and Encryption

APR envelope encode/decode logic:

```text
policy/codec.py
```

Supported values:

| Field | Values |
|---|---|
| compression | `none`, `zlib`, `gzip` |
| encryption | `none`, `AES-GCM` |
| integrity | `none`, `sha256` |

The AES key can be configured with:

```powershell
$env:APR_AES_KEY_HEX="00112233445566778899aabbccddeeff"
python server.py
```

The same key must be configured on edge devices.

## Database Operation

Database file:

```text
iot_data.db
```

The server uses SQLite WAL mode:

```text
PRAGMA journal_mode=WAL
PRAGMA synchronous=NORMAL
```

Main tables:

| Table | Purpose |
|---|---|
| `sensor_data` | Valid defined sensor telemetry |
| `mqtt_experiment_log` | Runtime communication and policy log |
| `unknown_payload_data` | Invalid, unknown, or decode-failed payloads |
| `unknown_schema_profile` | Schema evolution and clustering metadata |
| `apr_policy_log` | APR policy decision, feedback, rollback history |
| `voice_stream_results` | Voice stream runtime result summaries |

## Async DB Writer

The server does not write all incoming MQTT messages directly in the callback. It enqueues writes to:

```text
database/db_manager.py
```

Important metrics:

- `queue_depth`
- `queued`
- `committed`
- `failed`
- `dropped`
- `last_error`

Check:

```text
http://localhost:5000/api/db/status
```

## Dashboard URLs

| URL | Purpose |
|---|---|
| `/` | Main telemetry dashboard |
| `/all_dashboard` | Multi-sensor dashboard |
| `/sensor_config` | Sensor configuration |
| `/queue_dashboard` | Queue and backlog monitoring |
| `/latency_dashboard` | Latency statistics and trend |
| `/experiment_dashboard` | Scenario runner |
| `/schema_dashboard` | Unknown schema and schema evolution |
| `/apr_dashboard` | APR recommendation and policy operation |
| `/voice_dashboard` | Voice streaming metrics |
| `/device_edge_doc` | Raspberry Pi edge device documentation |
| `/server_operation_manual` | This server operation manual |

## Health Check APIs

| API | Purpose |
|---|---|
| `/api/broker/status` | MQTT broker configuration and active broker |
| `/api/db/status` | SQLite and DB writer status |
| `/api/queue-stats` | Queue monitor state |
| `/api/topic-rate` | Topic publish/receive rate |
| `/api/backlog-estimation` | Estimated queue backlog |
| `/api/apr/collection/status` | APR collection and policy state |
| `/api/latency-stats` | Latency statistics |
| `/api/experiment-log` | Runtime communication logs |

## Normal Operation Checklist

Before start:

- Confirm MQTT broker address in `config.json`.
- Confirm port `1883` is reachable.
- Confirm `APR_AES_KEY_HEX` if AES-GCM is used.
- Confirm disk space for `iot_data.db`.
- Confirm sensor IDs and topics.

After start:

- Open `/api/broker/status`.
- Open `/api/db/status`.
- Check dashboard loads at `/`.
- Start edge device publisher.
- Confirm data appears in `/all_dashboard`.
- Confirm DB writer `dropped` remains `0`.
- Confirm unknown payload count is not increasing unexpectedly.

During operation:

- Watch queue depth.
- Watch p95 latency.
- Watch APR rollback events.
- Watch decryption failures.
- Watch database size.

## Troubleshooting

### Server does not start

Check:

- Python environment,
- missing packages,
- port `5000` already in use,
- malformed `config.json`.

### MQTT connection fails

Check:

- broker IP,
- broker port,
- firewall,
- broker authentication,
- broker service status.

### Data does not appear

Check:

- edge device is publishing,
- topic starts with `iot/sensor/`,
- server subscribed to `iot/sensor/#`,
- payload has required fields,
- DB writer has no errors.

### Payload goes to unknown table

Check required telemetry fields:

- `sensor_id`
- `sensor_type`
- `value`
- `unit`
- `timestamp` or `publish_timestamp`

Check schema mismatch in:

```text
unknown_payload_data
unknown_schema_profile
```

### APR policy is not applied

Check:

- `enable_apr` is true,
- `auto_apr` is true if automatic evaluation is expected,
- device subscribed to `iot/sensor/policy/<sensor_id>`,
- server pushes to the same sensor ID,
- device logs show `[policy] updated`.

### AES-GCM decode fails

Check:

- server and device have the same `APR_AES_KEY_HEX`,
- device has `cryptography` installed,
- policy value is exactly `AES-GCM`,
- message was not modified in transit.

### DB queue grows continuously

Check:

- disk I/O,
- `db_writer.batch_size`,
- `db_writer.flush_interval`,
- `db_writer.max_queue_size`,
- database lock errors,
- high MQTT message rate.

## Backup and Maintenance

Recommended:

- back up `iot_data.db` regularly,
- rotate large `.log` files,
- archive old experiment/runtime data,
- monitor disk usage,
- keep `config.json` under version control or external backup.

For SQLite WAL mode, include related WAL/SHM files if present:

```text
iot_data.db
iot_data.db-wal
iot_data.db-shm
```

## Production Hardening

Recommended before production deployment:

- enable MQTT authentication,
- enable MQTT TLS,
- set `APR_AES_KEY_HEX` explicitly,
- avoid default AES key,
- run server under a process manager,
- configure log rotation,
- add external health checks,
- restrict dashboard/API access,
- back up database automatically.

## Recommended Server Launch Example

PowerShell:

```powershell
cd C:\access\iot
$env:APR_AES_KEY_HEX="00112233445566778899aabbccddeeff"
python server.py
```

Then open:

```text
http://localhost:5000
```
