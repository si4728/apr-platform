# Windows Local Run

This mode runs the APR Optimization Gateway directly on Windows without Docker.

## 1. Install Python

Install Python 3.11 or newer. The current PC has `py.exe`, but no registered Python runtime was detected.

After installing Python, confirm:

```powershell
py -3 --version
```

## 2. Install Dependencies

```powershell
cd C:\access\iot\apr_gateway
.\install_windows.ps1
```

If PowerShell blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
```

Optional ML dependencies:

```powershell
.\install_windows.ps1 -WithMl
```

## 3. Configure

Create a local `.env` from the example:

```powershell
Copy-Item .env.example .env
```

Edit `.env` for your broker:

```text
SOURCE_MQTT_HOST=218.146.225.166
SOURCE_MQTT_PORT=1883
TARGET_MQTT_HOST=218.146.225.166
TARGET_MQTT_PORT=1883
SUBSCRIBE_TOPIC=iot/sensor/#
PUBLISH_PREFIX=iot/optimized
APR_MODE=proxy
HTTP_PORT=8080
```

## 4. Run

```powershell
.\run_gateway.ps1
```

If PowerShell blocks script execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_gateway.ps1
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8080/health
```

## 5. Test MQTT Flow

In a second terminal, listen for optimized output:

```powershell
.\.venv\Scripts\python.exe .\tools\subscribe_test.py
```

In a third terminal, publish one raw test message:

```powershell
.\.venv\Scripts\python.exe .\tools\publish_test.py
```

## Notes

- `APR_MODE=advisor` observes and recommends policies without forwarding messages.
- `APR_MODE=proxy` republishes optimized APR envelope messages to `PUBLISH_PREFIX`.
- If no model files exist in `models/`, the gateway uses the rule-based fallback.
