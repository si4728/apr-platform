# Raspberry Pi Edge Device Documentation

## Purpose

`raspi_iot_publisher.py` is the minimal edge-device program for operating the platform with a real external device such as a Raspberry Pi.

The platform server remains on the host running `server.py`. The Raspberry Pi only needs to:

- read sensor values,
- publish telemetry to MQTT,
- subscribe to APR policy commands,
- apply the pushed communication policy on subsequent messages.

## Files

```text
device/raspi_iot_publisher.py
device/client.config
device/raspi-requirements.txt
device/run_raspi_client.sh
device/apr-raspi-client.service
```

Copy these files to the Raspberry Pi.

The client reads `client.config` by default, so normal operation does not require long command-line arguments.

## Runtime Role

The device publishes telemetry to a data topic:

```text
iot/sensor/<sensor_id>
```

or a user-specified topic such as:

```text
iot/sensor/temperature/temp_001
```

The device also subscribes to a policy-control topic:

```text
iot/sensor/policy/<sensor_id>
```

When the server pushes an APR policy to the policy topic, the device stores the policy in memory and applies it from the next publish cycle.

## Dependencies

Install dependencies on Raspberry Pi:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r raspi-requirements.txt
```

`paho-mqtt` is required.

`cryptography` is required when the server may push:

```json
{"encryption": "AES-GCM"}
```

## Configuration

Edit:

```text
client.config
```

Example:

```ini
[mqtt]
broker = 218.146.225.166
port = 1883
username =
password =
tls = false

[device]
sensor_id = temp_001
sensor_type = temperature
unit = C
client_id = raspi-temp-001

[topics]
telemetry = iot/sensor/temperature/temp_001
policy = iot/sensor/policy/temp_001

[runtime]
interval = 1.0
experiment_id = RASPI_RUNTIME

[security]
apr_aes_key_hex = 01010101010101010101010101010101
```

If `telemetry` is omitted, the default telemetry topic is:

```text
iot/sensor/<sensor_id>
```

If `policy` is omitted, the default policy topic is:

```text
iot/sensor/policy/<sensor_id>
```

## Basic Execution

```bash
python raspi_iot_publisher.py
```

or:

```bash
./run_raspi_client.sh
```

Optional config path override:

```bash
python raspi_iot_publisher.py --config /path/to/client.config
```

## Config Options

| Section | Key | Required | Description |
|---|---|---:|---|
| `mqtt` | `broker` | Yes | MQTT broker IP or hostname |
| `mqtt` | `port` | No | MQTT broker port, default `1883` |
| `mqtt` | `username` | No | MQTT username |
| `mqtt` | `password` | No | MQTT password |
| `mqtt` | `tls` | No | Enable MQTT TLS |
| `device` | `sensor_id` | Yes | Unique sensor/device ID |
| `device` | `sensor_type` | No | Sensor type, default `temperature` |
| `device` | `unit` | No | Sensor unit |
| `device` | `client_id` | No | MQTT client ID |
| `topics` | `telemetry` | No | Telemetry publish topic |
| `topics` | `policy` | No | APR policy command topic |
| `runtime` | `interval` | No | Publish interval in seconds |
| `runtime` | `experiment_id` | No | Runtime/session ID |
| `security` | `apr_aes_key_hex` | No | Shared AES-GCM key |

## Telemetry Payload

For plain JSON publishing, the device sends:

```json
{
  "experiment_id": "EDGE_RUNTIME",
  "platform_mode": "edge_device",
  "seq": 1,
  "sensor_id": "temp_001",
  "sensor_type": "temperature",
  "value": 24.531,
  "unit": "C",
  "topic": "iot/sensor/temperature/temp_001",
  "timestamp": "2026-05-20T04:00:00.000000+00:00",
  "publish_timestamp": "2026-05-20T04:00:00.000000+00:00",
  "policy": {
    "qos": 0,
    "compression": "none",
    "encryption": "none",
    "integrity": "none"
  }
}
```

The server uses these fields to classify the message as defined sensor telemetry:

- `sensor_id`
- `sensor_type`
- `value`
- `unit`
- `timestamp` or `publish_timestamp`

Do not remove those fields.

## APR Policy Command

The server sends APR policy commands through:

```text
iot/sensor/policy/<sensor_id>
```

Example policy command:

```json
{
  "qos": 1,
  "compression": "zlib",
  "encryption": "AES-GCM",
  "integrity": "sha256"
}
```

The device log will show:

```text
[policy] updated: {'qos': 1, 'compression': 'zlib', 'encryption': 'AES-GCM', 'integrity': 'sha256'}
```

After this point, outgoing telemetry is encoded as an APR envelope.

## APR Envelope Payload

When compression, encryption, or integrity is enabled, the payload becomes:

```json
{
  "metadata": {
    "publish_timestamp": "2026-05-20T04:00:00.000000+00:00",
    "experiment_id": "EDGE_RUNTIME",
    "seq": 1,
    "qos": 1,
    "compression": "zlib",
    "encryption": "AES-GCM",
    "integrity": "sha256",
    "hash": "..."
  },
  "data": "Base64(...)"
}
```

The server decodes this envelope through `policy/codec.py`.

## Supported Policy Values

| Field | Supported Values |
|---|---|
| `qos` | `0`, `1`, `2` |
| `compression` | `none`, `zlib`, `gzip` |
| `encryption` | `none`, `AES-GCM` |
| `integrity` | `none`, `sha256` |

## Control Commands

The device also understands control commands.

Start metric collection mode:

```json
{
  "command": "collect"
}
```

Reset to default policy:

```json
{
  "command": "reset_policy"
}
```

or:

```json
{
  "command": "default_policy"
}
```

## AES-GCM Key

The device and server must share the same AES key.

Current compatibility default:

```text
01010101010101010101010101010101
```

For real operation, set an explicit key on both sides.

On Raspberry Pi:

```bash
export APR_AES_KEY_HEX=00112233445566778899aabbccddeeff
python raspi_iot_publisher.py --broker 218.146.225.166 --sensor-id temp_001
```

On Windows server PowerShell:

```powershell
$env:APR_AES_KEY_HEX="00112233445566778899aabbccddeeff"
python server.py
```

The key must be 16 bytes, 24 bytes, or 32 bytes when decoded from hex.

## Real Sensor Integration

Edit this function:

```python
def read_sensor_value(sensor_type):
```

Replace the simulated values with actual sensor code.

Example DHT-style structure:

```python
def read_sensor_value(sensor_type):
    temperature = read_temperature_from_sensor()
    return round(temperature, 3), "C"
```

Possible integration methods:

- GPIO
- I2C
- SPI
- UART
- USB serial
- Modbus
- industrial sensor gateway output

Only the returned value and unit need to match the payload structure.

## Server-Side Operating Sequence

Start the platform server:

```powershell
cd C:\access\iot
python server.py
```

Open:

```text
http://<server-ip>:5000
http://<server-ip>:5000/queue_dashboard
http://<server-ip>:5000/latency_dashboard
http://<server-ip>:5000/apr_dashboard
```

## Device-Side Operating Sequence

Start the Pi publisher:

```bash
python raspi_iot_publisher.py
```

Expected logs:

```text
[mqtt] connected rc=0
[mqtt] subscribed policy topic: iot/sensor/policy/temp_001
[edge] publishing topic: iot/sensor/temperature/temp_001
[publish] seq=1 qos=0 policy={'qos': 0, 'compression': 'none', 'encryption': 'none', 'integrity': 'none'} rc=0
```

## Troubleshooting

### MQTT connection fails

Check:

- broker IP,
- broker port,
- firewall,
- MQTT authentication,
- whether TLS is required.

### Server receives unknown payload

Check that the payload contains:

- `sensor_id`
- `sensor_type`
- `value`
- `unit`
- `timestamp` or `publish_timestamp`

### APR encrypted payload fails on server

Check that both server and device use the same:

```text
APR_AES_KEY_HEX
```

Also check that `cryptography` is installed on the device.

### APR policy is not applied

Check that the device subscribed to:

```text
iot/sensor/policy/<sensor_id>
```

and that the server publishes to the same sensor ID.

### Messages publish but do not appear in dashboard

Check:

- server is running,
- server MQTT connection is active,
- topic begins with `iot/sensor/`,
- server subscribed to `iot/sensor/#`,
- DB writer queue is not full.

## Operational Notes

- Device policy state is in memory only.
- If the device restarts, it returns to default policy until the server pushes a new policy.
- Use stable `sensor_id` values because policy topics depend on sensor ID.
- Use unique MQTT `client-id` values for multiple devices.
- For production, use MQTT authentication and TLS.
