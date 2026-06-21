# APR 기반 Industrial IoT 플랫폼 사용설명서

작성일: 2026-06-21  
대상 버전: 현재 `C:\access\iot` 저장소 기준

## 1. 시스템 개요

이 플랫폼은 MQTT 기반 Industrial IoT 데이터 수집, 대시보드 시각화, SQLite 저장, APR(Adaptive Policy Recommendation) 기반 통신 정책 추천/배포, 장치별 클라이언트 패키지 생성 기능을 제공한다.

주요 목적은 다음과 같다.

- IoT 장치와 센서가 MQTT로 보낸 텔레메트리 수집
- 정상 센서 데이터와 미정의 payload 분리 저장
- payload 크기, 지연시간, QoS, 압축, 암호화, 무결성 정책 기록
- APR 모델 또는 규칙 기반 로직으로 최적 통신 정책 추천
- 장치 또는 Fleet 단위로 정책을 MQTT policy topic에 배포
- PC, Raspberry Pi, Ubuntu/Linux 장치에서 실행 가능한 client code 제공
- 관리자/사용자, Site, Group, Fleet, Device, topic 경로 관리
- Queue, latency, schema, experiment, voice streaming 대시보드 제공

전체 실행 구조는 다음과 같다.

```text
Device / PC / Raspberry Pi / Ubuntu Client
    -> MQTT broker
    -> server.py MQTT subscriber
    -> APR envelope decode
    -> Async DB writer
    -> SQLite iot_data.db
    -> Flask dashboard / REST API
    -> APR policy push
    -> Device policy topic
```

## 2. 주요 폴더와 파일

| 경로 | 설명 |
|---|---|
| `server.py` | Flask 대시보드, REST API, MQTT subscriber, APR 정책 배포의 메인 서버 |
| `config.json` | MQTT broker, APR, DB writer, platform runtime 설정 |
| `iot_data.db` | SQLite 운영 데이터베이스 |
| `policy/apr_policy.py` | APR 추천 엔진. XGBoost 모델이 있으면 ML 추천, 실패하면 규칙 기반 추천 |
| `policy/codec.py` | APR envelope 압축, 암호화, 무결성 검증, 복호화 |
| `database/db_manager.py` | 비동기 SQLite batch writer |
| `monitor/queue_monitor.py` | queue depth, topic rate 모니터링 |
| `device/raspi_iot_publisher.py` | Raspberry Pi/Ubuntu/Linux용 일반 센서 publisher |
| `device/raspi_system_metrics_publisher.py` | Raspberry Pi/Ubuntu 시스템 메트릭 publisher |
| `device/pc_test_publisher.py` | Windows PC 또는 Linux PC 테스트 publisher |
| `device/client.config` | 일반 센서/PC 테스트 publisher 설정 파일 |
| `device/system_metrics.config` | 시스템 메트릭 publisher 설정 파일 |
| `templates/`, `static/` | 웹 대시보드 화면, CSS, JavaScript |
| `tools/` | 런타임 점검, E2E 테스트, APR 검증 도구 |
| `experiment/` | QoS, payload size, queue, schema, voice 실험 스크립트 |
| `docker-compose.yml` | Docker Desktop 실행 설정 |

## 3. 서버 설치와 실행

### 3.1 Windows 직접 실행

PowerShell에서 실행한다.

```powershell
cd C:\access\iot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

기본 접속 주소는 다음과 같다.

```text
http://localhost:4728
http://<server-ip>:4728
```

다른 PC, Raspberry Pi, Ubuntu 장치에서 접속하려면 Windows 방화벽에서 TCP `4728`, MQTT broker 포트 `1883` 접근이 가능해야 한다.

### 3.2 Docker Desktop 실행

```powershell
cd C:\access\iot
docker compose up -d --build
```

접속 주소:

```text
http://localhost:4728
```

상태 확인:

```powershell
docker ps
docker logs -f iot-dashboard
docker inspect --format='{{json .State.Health}}' iot-dashboard
```

종료:

```powershell
docker compose down
```

### 3.3 서버 종료

웹 API로 종료:

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:4728/api/system/shutdown
```

터미널에서는 `Ctrl+C`로 종료한다. 서버는 MQTT loop 중지, broker disconnect, DB writer flush를 수행한다.

## 4. 기본 설정

`config.json`의 현재 핵심 설정은 다음과 같다.

```json
{
  "mqtt": {
    "broker": "218.146.225.166",
    "port": 1883,
    "topic_prefix": "iot/sensor"
  },
  "platform": {
    "enable_apr": true,
    "auto_apr": true,
    "apr_min_samples": 5,
    "apr_evaluation_interval_seconds": 30,
    "default_qos": 0,
    "default_policy": {
      "compression": "none",
      "encryption": "none",
      "integrity": "none"
    }
  }
}
```

서버는 기본적으로 다음 topic을 구독한다.

```text
iot/sensor/#
```

정책 topic은 일반적으로 다음 형식을 사용한다.

```text
iot/sensor/policy/<device_id 또는 sensor_id>
```

## 5. 웹 화면 사용법

| URL | 용도 |
|---|---|
| `/` | 메인 텔레메트리 대시보드 |
| `/all_dashboard` | 여러 센서의 데이터를 한 화면에서 확인 |
| `/sensor_config` | 센서 정의 등록, 수정, 삭제 |
| `/device_management` | 사용자, Fleet, Device, topic, client package 관리 |
| `/queue_dashboard` | DB writer queue, backlog, topic rate 확인 |
| `/latency_dashboard` | latency 통계, trend, histogram 확인 |
| `/experiment_dashboard` | QoS, payload, queue, schema, voice 실험 실행 |
| `/schema_dashboard` | unknown payload, schema profile, USI 승인/거절 |
| `/apr_dashboard` | APR 추천, 정책 배포, 수집/평가 |
| `/voice_dashboard` | G.711 voice streaming 실험 결과 |
| `/device_edge_doc` | Raspberry Pi edge 문서 |
| `/server_operation_manual` | 서버 운영 문서 |

예: 서버가 로컬에서 실행 중이면 브라우저에서 다음을 연다.

```text
http://localhost:4728/device_management
```

## 6. 사용자, Site, Group, Fleet, Device 관리

`/device_management` 화면에서 운영 단위를 관리한다.

권장 순서:

1. 관리자 계정으로 로그인한다.
2. 사용자 또는 운영자를 생성한다.
3. Site와 Group을 생성한다.
4. Fleet을 생성하고 owner user를 지정한다.
5. Device를 생성하고 OS를 선택한다.
6. 생성된 telemetry topic과 policy topic을 확인한다.
7. Device client package를 다운로드한다.
8. 장치에서 압축을 풀고 client를 실행한다.

Topic 생성 규칙은 대략 다음과 같다.

```text
<site_topic>/<group_topic>/<user_topic>/<fleet_topic>/<device_type>/<device_id>
```

정책 topic:

```text
<site_topic>/<group_topic>/<user_topic>/<fleet_topic>/policy/<device_id>
```

예:

```text
Telemetry: default_site/default_group/user01/line_a/raspberry_pi/raspi_001
Policy:    default_site/default_group/user01/line_a/policy/raspi_001
```

## 7. Device Client Package 다운로드

장치 관리 화면에서 Device를 선택한 뒤 client package를 다운로드한다. 내부적으로 다음 API를 사용한다.

```http
GET /api/devices/<row_id>/client-package
```

예:

```powershell
Invoke-WebRequest `
  -Uri "http://127.0.0.1:4728/api/devices/1/client-package?device_os=raspberry_pi" `
  -OutFile "apr_client_raspi_001_raspberry_pi.zip"
```

ZIP에는 OS에 따라 다음 파일이 포함된다.

공통:

```text
raspi_iot_publisher.py
raspi-requirements.txt
client.config
START_HERE.txt
```

Raspberry Pi:

```text
raspi_system_metrics_publisher.py
system_metrics.config
run_raspi_client.sh
run_raspi_system_metrics.sh
apr-raspi-client.service
```

PC/Ubuntu 테스트:

```text
pc_test_publisher.py
run_pc_test_publisher.bat
run_pc_test_publisher.sh
```

## 8. Client 설정 파일

### 8.1 일반 센서/PC 테스트용 `client.config`

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

중요 항목:

| 항목 | 설명 |
|---|---|
| `broker` | MQTT broker IP 또는 hostname |
| `port` | MQTT broker port. 기본 `1883` |
| `sensor_id` | 장치 또는 센서 ID |
| `sensor_type` | `temperature`, `humidity`, `vibration` 등 |
| `telemetry` | 데이터 publish topic |
| `policy` | APR 정책 command subscribe topic |
| `interval` | publish 주기, 초 단위 |
| `apr_aes_key_hex` | AES-GCM 사용 시 서버와 동일해야 하는 key |

### 8.2 시스템 메트릭용 `system_metrics.config`

```ini
[mqtt]
broker = 218.146.225.166
port = 1883
username =
password =
tls = false

[device]
device_id = raspi_001
device_name = raspberry-pi-edge-001
location = factory-line-1
client_id = raspi-system-001

[topics]
topic_prefix = iot/sensor/system
telemetry = iot/sensor/system/raspi_001_system
policy = iot/sensor/policy/raspi_001

[runtime]
enabled = true
interval = 5.0
experiment_id = RASPI_SYSTEM_RUNTIME
metrics = cpu_percent,memory_percent,cpu_temp_c,disk_percent,load_1m

[security]
apr_aes_key_hex = 01010101010101010101010101010101
```

지원 메트릭:

```text
cpu_percent
memory_percent
memory_used_mb
memory_total_mb
cpu_temp_c
disk_percent
disk_used_gb
disk_total_gb
load_1m
```

## 9. PC Client Code 사용법

PC 테스트 publisher는 실제 장비 없이 Windows PC 또는 Linux PC에서 MQTT 발행과 APR 정책 적용을 검증할 때 사용한다.

파일:

```text
device/pc_test_publisher.py
device/run_pc_test_publisher.bat
device/run_pc_test_publisher.sh
device/client.config
```

### 9.1 Windows PC 실행

```powershell
cd C:\access\iot\device
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r raspi-requirements.txt
python pc_test_publisher.py --config client.config
```

또는:

```powershell
cd C:\access\iot\device
.\run_pc_test_publisher.bat
```

예상 로그:

```text
[mqtt] connected rc=0
[mqtt] subscribed policy topic: iot/sensor/policy/temp_001
[pc-test] publishing fixed topic: iot/sensor/temperature/temp_001
[pc-test] seq=1 qos=0 rc=0
```

### 9.2 PC payload 예시

```json
{
  "experiment_id": "RASPI_RUNTIME",
  "platform_mode": "pc_test",
  "seq": 1,
  "sensor_id": "temp_001",
  "sensor_type": "temperature",
  "value": 24.517,
  "unit": "C",
  "topic": "iot/sensor/temperature/temp_001",
  "timestamp": "2026-06-21T07:00:00+00:00",
  "publish_timestamp": "2026-06-21T07:00:00+00:00",
  "policy": {
    "qos": 0,
    "compression": "none",
    "encryption": "none",
    "integrity": "none"
  },
  "pc_test": {
    "hostname": "DESKTOP-TEST",
    "os": "Windows-10",
    "python": "3.12.0",
    "sample_noise": 0.3812
  }
}
```

## 10. Raspberry Pi Client Code 사용법

Raspberry Pi에서는 일반 센서 publisher와 시스템 메트릭 publisher를 사용할 수 있다.

### 10.1 설치

다운로드한 ZIP을 Raspberry Pi에 복사한 뒤 압축을 푼다.

```bash
mkdir -p ~/raspi_client
cd ~/raspi_client
unzip apr_client_raspi_001_raspberry_pi.zip
python3 -m venv .venv
source .venv/bin/activate
pip install -r raspi-requirements.txt
chmod +x run_raspi_client.sh run_raspi_system_metrics.sh
```

### 10.2 일반 센서 publisher 실행

```bash
cd ~/raspi_client
./run_raspi_client.sh
```

직접 실행:

```bash
source .venv/bin/activate
python raspi_iot_publisher.py --config client.config
```

예상 로그:

```text
[mqtt] connected rc=0
[mqtt] subscribed policy topic: iot/sensor/policy/temp_001
[edge] publishing topic: iot/sensor/temperature/temp_001
[publish] seq=1 qos=0 policy={'qos': 0, 'compression': 'none', 'encryption': 'none', 'integrity': 'none'} rc=0
```

### 10.3 실제 센서 연동

`raspi_iot_publisher.py`의 다음 함수를 실제 센서 코드로 교체한다.

```python
def read_sensor_value(sensor_type):
    if sensor_type == "temperature":
        return round(24.0 + random.uniform(-1.5, 1.5), 3), "C"
    if sensor_type == "humidity":
        return round(55.0 + random.uniform(-6.0, 6.0), 3), "%"
    if sensor_type == "vibration":
        return round(2.0 + random.uniform(-0.4, 0.4), 3), "mm/s"
    return round(random.random() * 100.0, 3), "unit"
```

DHT 온도 센서 예시:

```python
def read_sensor_value(sensor_type):
    temperature = read_temperature_from_dht22()
    return round(temperature, 3), "C"
```

I2C 센서 예시:

```python
def read_sensor_value(sensor_type):
    value = read_value_from_i2c_sensor(bus=1, address=0x40)
    return round(value, 3), "C"
```

### 10.4 시스템 메트릭 publisher 실행

```bash
cd ~/raspi_client
./run_raspi_system_metrics.sh
```

직접 실행:

```bash
source .venv/bin/activate
python raspi_system_metrics_publisher.py --config system_metrics.config
```

payload 예시:

```json
{
  "experiment_id": "RASPI_SYSTEM_RUNTIME",
  "platform_mode": "edge_device",
  "seq": 1,
  "device_id": "raspi_001",
  "device_name": "raspberry-pi-edge-001",
  "location": "factory-line-1",
  "sensor_id": "raspi_001_system",
  "sensor_type": "system_metrics",
  "payload_type": "system_metrics",
  "metrics": {
    "cpu_percent": 12.4,
    "memory_percent": 45.2,
    "cpu_temp_c": 52.1,
    "disk_percent": 31.8,
    "load_1m": 0.42
  },
  "metric_units": {
    "cpu_percent": "%",
    "memory_percent": "%",
    "cpu_temp_c": "C",
    "disk_percent": "%",
    "load_1m": "load"
  },
  "topic": "iot/sensor/system/raspi_001_system",
  "timestamp": "2026-06-21T07:00:00+00:00",
  "publish_timestamp": "2026-06-21T07:00:00+00:00",
  "policy": {
    "qos": 0,
    "compression": "none",
    "encryption": "none",
    "integrity": "none"
  }
}
```

### 10.5 systemd 서비스 등록

`apr-raspi-client.service` 예시:

```ini
[Unit]
Description=APR Raspberry Pi MQTT Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/pi/raspi_client
ExecStart=/home/pi/raspi_client/.venv/bin/python /home/pi/raspi_client/raspi_iot_publisher.py --config /home/pi/raspi_client/client.config
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

등록:

```bash
sudo cp apr-raspi-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable apr-raspi-client
sudo systemctl start apr-raspi-client
sudo systemctl status apr-raspi-client
```

로그 확인:

```bash
journalctl -u apr-raspi-client -f
```

## 11. Ubuntu Client Code 사용법

Ubuntu에서는 Raspberry Pi용 일반 publisher와 PC test publisher를 모두 사용할 수 있다. 실제 센서가 없으면 `pc_test_publisher.py`를 권장한다.

### 11.1 Ubuntu 테스트 publisher

```bash
sudo apt update
sudo apt install -y python3 python3-venv unzip
mkdir -p ~/apr_client
cd ~/apr_client
unzip apr_client_ubuntu.zip
python3 -m venv .venv
source .venv/bin/activate
pip install -r raspi-requirements.txt
chmod +x run_pc_test_publisher.sh
./run_pc_test_publisher.sh
```

직접 실행:

```bash
python3 pc_test_publisher.py --config client.config
```

### 11.2 Ubuntu 일반 센서 publisher

Ubuntu에 USB serial, Modbus, GPIO bridge, 산업용 gateway 출력이 연결되어 있다면 `raspi_iot_publisher.py`를 사용하고 `read_sensor_value()`만 장비에 맞게 수정한다.

```bash
cd ~/apr_client
source .venv/bin/activate
python3 raspi_iot_publisher.py --config client.config
```

예: USB serial에서 값을 읽는 구조

```python
def read_sensor_value(sensor_type):
    raw = read_line_from_usb_serial("/dev/ttyUSB0")
    return float(raw), "C"
```

### 11.3 Ubuntu systemd 서비스 예시

```ini
[Unit]
Description=APR Ubuntu MQTT Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/apr_client
ExecStart=/home/ubuntu/apr_client/.venv/bin/python /home/ubuntu/apr_client/pc_test_publisher.py --config /home/ubuntu/apr_client/client.config
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

등록:

```bash
sudo nano /etc/systemd/system/apr-ubuntu-client.service
sudo systemctl daemon-reload
sudo systemctl enable apr-ubuntu-client
sudo systemctl start apr-ubuntu-client
journalctl -u apr-ubuntu-client -f
```

## 12. APR 정책과 Envelope

지원 정책:

| 필드 | 값 |
|---|---|
| `qos` | `0`, `1`, `2` |
| `compression` | `none`, `zlib`, `gzip` |
| `encryption` | `none`, `AES-GCM` |
| `integrity` | `none`, `sha256` |

정책 명령 예시:

```json
{
  "qos": 1,
  "compression": "zlib",
  "encryption": "AES-GCM",
  "integrity": "sha256"
}
```

장치는 policy topic에서 이 메시지를 수신한 뒤 다음 publish부터 적용한다.

APR envelope 예시:

```json
{
  "metadata": {
    "publish_timestamp": "2026-06-21T07:00:00+00:00",
    "experiment_id": "RASPI_RUNTIME",
    "seq": 10,
    "qos": 1,
    "compression": "zlib",
    "encryption": "AES-GCM",
    "integrity": "sha256",
    "hash": "..."
  },
  "data": "Base64(Nonce + AES-GCM(Zlib(JSON)))"
}
```

AES-GCM을 사용할 경우 서버와 장치의 key가 반드시 같아야 한다.

서버 PowerShell:

```powershell
$env:APR_AES_KEY_HEX="00112233445566778899aabbccddeeff"
python server.py
```

Raspberry Pi/Ubuntu:

```bash
export APR_AES_KEY_HEX=00112233445566778899aabbccddeeff
python3 raspi_iot_publisher.py --config client.config
```

또는 config의 `[security] apr_aes_key_hex`에 입력한다.

## 13. APR 추천과 정책 배포 API

### 13.1 정책 추천

```http
POST /api/apr/recommend
```

PowerShell 예시:

```powershell
$body = @{
  payload_size = 512
  network_latency_ms = 20
  queue_depth = 10
  topic = "iot/sensor/temperature/temp_001"
  schema_type = "standard"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method POST `
  -Uri "http://127.0.0.1:4728/api/apr/recommend" `
  -ContentType "application/json" `
  -Body $body
```

응답 예시:

```json
{
  "qos": 0,
  "compression": "gzip",
  "encryption": "none",
  "integrity": "none"
}
```

### 13.2 장치 단위 정책 적용

```http
POST /api/devices/<row_id>/policy/apply
```

예:

```powershell
$body = @{
  policy = @{
    qos = 1
    compression = "zlib"
    encryption = "AES-GCM"
    integrity = "sha256"
  }
} | ConvertTo-Json -Depth 4

Invoke-RestMethod `
  -Method POST `
  -Uri "http://127.0.0.1:4728/api/devices/1/policy/apply" `
  -ContentType "application/json" `
  -Body $body
```

### 13.3 Fleet 단위 정책 적용

```http
POST /api/fleets/<fleet_id>/policy/apply
```

Fleet에 속한 장치들에게 동일한 정책을 배포할 때 사용한다.

### 13.4 정책 적용 확인

```http
GET /api/devices/<row_id>/policy
GET /api/fleets/<fleet_id>/policy
```

## 14. 장치 제어 명령

일반 publisher가 이해하는 command:

```json
{ "command": "collect" }
```

```json
{ "command": "reset_policy" }
```

```json
{ "command": "default_policy" }
```

시스템 메트릭 publisher가 추가로 이해하는 command:

```json
{ "command": "pause" }
```

```json
{ "command": "resume" }
```

```json
{
  "command": "set_options",
  "interval": 10,
  "metrics": ["cpu_percent", "memory_percent", "cpu_temp_c"]
}
```

## 15. 센서 데이터 형식

서버가 정상 센서 데이터로 분류하려면 아래 필드가 필요하다.

```json
{
  "sensor_id": "temp_001",
  "sensor_type": "temperature",
  "value": 24.85,
  "unit": "C",
  "timestamp": "2026-06-21T07:00:00+00:00",
  "publish_timestamp": "2026-06-21T07:00:00+00:00"
}
```

필수 성격의 필드:

```text
sensor_id
sensor_type
value
unit
timestamp 또는 publish_timestamp
```

필드가 없거나 JSON이 아니면 `unknown_payload_data`에 저장되고 schema dashboard에서 확인할 수 있다.

## 16. 센서 등록 API

센서 목록:

```http
GET /api/sensors
```

센서 등록 예:

```powershell
$body = @{
  sensor_id = "temp_001"
  sensor_type = "temperature"
  unit = "C"
  topic = "iot/sensor/temperature/temp_001"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method POST `
  -Uri "http://127.0.0.1:4728/api/sensors" `
  -ContentType "application/json" `
  -Body $body
```

센서 수정:

```http
PUT /api/sensors/<sensor_id>
```

센서 삭제:

```http
DELETE /api/sensors/<sensor_id>
```

## 17. 모니터링 API

| API | 설명 |
|---|---|
| `GET /api/system/status` | 서버 프로세스, lock, runtime 상태 |
| `GET /api/broker/status` | MQTT broker 설정과 active broker |
| `GET /api/db/status` | SQLite, DB writer queue, commit/drop 상태 |
| `GET /api/queue-stats` | queue monitor 상태 |
| `GET /api/topic-rate` | topic별 수신 rate |
| `GET /api/backlog-estimation` | backlog 추정 |
| `GET /api/stats` | 전체 센서 통계 |
| `GET /api/chart/<sensor_id>` | 특정 센서 차트 데이터 |
| `GET /api/latency-stats` | latency 통계 |
| `GET /api/latency-histogram` | latency histogram |
| `GET /api/latency-trend` | latency trend |
| `GET /api/experiment-log` | MQTT experiment log |
| `GET /api/schema-stats` | schema profile 통계 |
| `GET /api/unknown-payloads` | unknown payload 목록 |
| `GET /api/voice/results` | voice streaming 실험 결과 |

예:

```powershell
Invoke-RestMethod http://127.0.0.1:4728/api/db/status
Invoke-RestMethod http://127.0.0.1:4728/api/broker/status
Invoke-RestMethod "http://127.0.0.1:4728/api/latency-stats?limit=200"
```

## 18. 실험 실행

실험 대시보드 또는 API를 사용할 수 있다.

```http
POST /api/experiment/run
```

지원 실험 스크립트:

```text
experiment/qos_test.py
experiment/payload_size_test.py
experiment/queue_test.py
experiment/schema_variation_test.py
experiment/apr_validation.py
experiment/voice_stream_test.py
```

Voice 실험 직접 실행 예:

```powershell
python experiment/voice_stream_test.py --duration 15 --fps 50 --prebuffer 300 --qos 0 --drop-on
```

연구 프로파일 리포트 생성:

```powershell
python experiment/research_profile_runner.py
```

결과 예:

```text
experiment_results/research_performance_report.md
```

## 19. 운영 점검 도구

`tools/` 폴더에는 점검 스크립트가 있다.

```powershell
python tools/check_db_health.py
python tools/check_mqtt_connectivity.py
python tools/check_runtime_status.py
python tools/check_apr_ml_runtime.py
```

E2E 테스트 예:

```powershell
python tools/e2e_device_package_test.py
python tools/e2e_apr_policy_push_test.py
python tools/e2e_mqtt_publish_path_test.py
python tools/e2e_user_device_linkage_test.py
python tools/e2e_usi_approval_test.py
```

## 20. 정상 운영 체크리스트

서버 시작 전:

- `config.json`의 MQTT broker 주소와 port 확인
- `iot_data.db` 백업 여부 확인
- AES-GCM 사용 시 `APR_AES_KEY_HEX` 확인
- 같은 DB를 Windows 서버와 Docker가 동시에 쓰지 않는지 확인
- `runtime/iot_dashboard.lock`이 오래된 lock인지 확인

서버 시작 후:

- `http://localhost:4728/api/system/status` 확인
- `http://localhost:4728/api/broker/status` 확인
- `http://localhost:4728/api/db/status` 확인
- 대시보드 `/` 접속 확인
- 장치 client 실행
- `/all_dashboard`에서 데이터 수신 확인
- DB writer `dropped` 값이 `0`인지 확인

장치 시작 후:

- MQTT 연결 로그 확인
- policy topic subscribe 로그 확인
- publish `rc=0` 확인
- 장치 topic이 서버의 구독 범위에 포함되는지 확인
- APR 정책 적용 시 `[policy] updated` 로그 확인

## 21. 문제 해결

### 서버가 시작되지 않을 때

확인 항목:

- Python package 설치 여부
- `PORT=4728` 충돌 여부
- `config.json` JSON 문법 오류
- DB 파일 손상 여부
- 다른 서버 또는 Docker 컨테이너가 같은 DB를 사용 중인지 여부

### MQTT 연결 실패

확인 항목:

- broker IP: `218.146.225.166`
- port: `1883`
- 방화벽
- MQTT username/password
- TLS 필요 여부

### 데이터가 대시보드에 나오지 않을 때

확인 항목:

- client가 publish 중인지
- topic이 서버 구독 범위에 들어오는지
- payload에 `sensor_id`, `sensor_type`, `value`, `unit`이 있는지
- DB writer queue가 가득 차지 않았는지
- `/api/unknown-payloads`에 들어가고 있지 않은지

### APR 암호화 payload 복호화 실패

확인 항목:

- 서버와 장치의 `APR_AES_KEY_HEX`가 같은지
- `cryptography` package가 장치에 설치되어 있는지
- 정책 값이 정확히 `AES-GCM`인지
- 중간에서 payload가 변조되지 않았는지

### 정책이 장치에 적용되지 않을 때

확인 항목:

- 장치가 올바른 policy topic을 subscribe했는지
- 서버가 같은 policy topic으로 publish했는지
- 장치 로그에 `[policy] updated`가 찍히는지
- MQTT broker에 policy message가 실제 도착하는지

### DB queue가 계속 증가할 때

확인 항목:

- `/api/db/status`의 `queue_depth`, `last_error`
- 디스크 I/O 병목
- SQLite lock
- `DB_BUSY_TIMEOUT_MS`, `DB_LOCK_RETRIES`
- MQTT message rate가 너무 높은지

## 22. 보안과 운영 권장사항

PoC 기본값은 편의성을 우선한다. 실제 운영에서는 다음을 권장한다.

- MQTT 인증 사용
- MQTT TLS 사용
- 기본 AES key `01010101010101010101010101010101` 변경
- `APR_AES_KEY_HEX`를 환경변수 또는 안전한 secret 저장소로 관리
- dashboard/API 접근 제한
- DB 정기 백업
- 로그 rotation 적용
- Windows 직접 실행과 Docker 실행을 동시에 사용하지 않기
- 운영 DB는 장기적으로 PostgreSQL 또는 TimescaleDB 전환 검토

## 23. 빠른 실행 예시

### 서버

```powershell
cd C:\access\iot
.\.venv\Scripts\Activate.ps1
python server.py
```

### Windows PC 테스트 장치

```powershell
cd C:\access\iot\device
python pc_test_publisher.py --config client.config
```

### Raspberry Pi 센서 장치

```bash
cd ~/raspi_client
source .venv/bin/activate
python raspi_iot_publisher.py --config client.config
```

### Raspberry Pi 시스템 메트릭

```bash
cd ~/raspi_client
source .venv/bin/activate
python raspi_system_metrics_publisher.py --config system_metrics.config
```

### Ubuntu 테스트 장치

```bash
cd ~/apr_client
source .venv/bin/activate
python3 pc_test_publisher.py --config client.config
```

### APR 추천 확인

```powershell
$body = @{
  payload_size = 2048
  network_latency_ms = 35
  queue_depth = 5
  topic = "iot/sensor/temperature/temp_001"
  schema_type = "standard"
} | ConvertTo-Json

Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:4728/api/apr/recommend" -ContentType "application/json" -Body $body
```

