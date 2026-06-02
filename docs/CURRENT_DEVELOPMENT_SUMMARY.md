# IoT APR Platform Current Development Summary

작성일: 2026-06-02

## 1. 시스템 개요

본 시스템은 MQTT 기반 IoT 데이터 수집, 대시보드 시각화, APR 정책 제어, Raspberry Pi edge publisher, 시스템 메트릭 수집 기능을 포함하는 IoT 운영/실험 플랫폼이다.

핵심 목적은 기존 MQTT payload를 최대한 유지하면서 센서 데이터, unknown payload, latency, payload size, queue 상태를 수집하고, APR 정책을 통해 QoS, 압축, 암호화, 무결성 옵션을 원격으로 조정하는 것이다.

## 2. 주요 구성

| 구분 | 파일/경로 | 설명 |
|---|---|---|
| Dashboard server | `server.py` | Flask 기반 IoT dashboard, MQTT subscriber, DB writer, APR 제어 API |
| Docker 실행 | `docker-compose.yml` | `iot-dashboard` 컨테이너 실행 설정 |
| Dashboard UI | `templates/`, `static/` | 단일/전체 센서 대시보드, shutdown 버튼, 수집 지연 경고 |
| DB writer | `database/db_manager.py` | 비동기 SQLite writer, lock retry 처리 |
| Raspberry sensor publisher | `device/raspi_iot_publisher.py` | 기존 센서 데이터 publisher, APR policy 수신 |
| Raspberry system metrics publisher | `device/raspi_system_metrics_publisher.py` | Raspberry CPU/MEM/TEMP/DISK/LOAD 수집 publisher |
| Sensor client config | `device/client.config` | 기존 센서 publisher 전용 설정 |
| System metrics config | `device/system_metrics.config` | Raspberry 시스템 메트릭 publisher 전용 설정 |
| APR Gateway | `apr_gateway/` | 별도 APR optimization gateway 서비스 |

## 3. Dashboard/Server 기능

현재 `server.py`에는 다음 기능이 포함되어 있다.

- MQTT broker 구독: `iot/sensor/#`
- 정의된 센서 payload 저장
- 미정의/unknown payload 별도 저장
- payload schema fingerprint 관리
- latency, payload size, QoS, compression, encryption, integrity 기록
- APR policy 평가 및 device policy topic으로 push
- 수집 지연 경고 API
- 시스템 상태 API
- dashboard shutdown API
- DB lock/busy timeout 처리

주요 API:

```text
GET  /api/config
GET  /api/sensors
GET  /api/stats
GET  /api/chart/<sensor_id>
GET  /api/collection-warnings
GET  /api/db/status
GET  /api/system/status
POST /api/system/shutdown
```

## 4. Dashboard Shutdown 기능

대시보드 왼쪽 시스템 상태 영역에 `System Shutdown` 버튼을 추가했다.

동작 순서:

```text
System Shutdown 클릭
→ 확인창 표시
→ MQTT loop stop
→ MQTT disconnect
→ DB writer stop/flush
→ runtime/iot_dashboard.lock 제거
→ process 종료
```

PowerShell에서 API로도 종료 가능하다.

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:5000/api/system/shutdown
```

## 5. Windows/Docker 단일 실행 보호

Windows와 Docker가 같은 SQLite DB 파일을 동시에 쓰면 DB 손상 위험이 있으므로 실행 lock 기능을 추가했다.

공유 lock 파일:

```text
runtime/iot_dashboard.lock
```

Docker 실행 시:

```text
SYSTEM_MODE=docker
SYSTEM_LOCK_FILE=/app/runtime/iot_dashboard.lock
```

Windows에서 `python server.py` 실행 시 Docker가 이미 운영 중이면 다음과 같이 차단된다.

```text
RuntimeError: Another system instance is already using the shared DB
```

이는 정상 동작이며, DB 보호를 위한 단일 실행 정책이다.

## 6. Docker 운영 설정

현재 `docker-compose.yml` 기준:

```yaml
services:
  iot-dashboard:
    ports:
      - "5000:5000"
    environment:
      TZ: Asia/Seoul
      DB_NAME: /app/iot_data.db
      DB_JOURNAL_MODE: DELETE
      DB_LOCK_RETRIES: 10
      DB_BUSY_TIMEOUT_MS: 30000
      SYSTEM_MODE: docker
      SYSTEM_LOCK_FILE: /app/runtime/iot_dashboard.lock
    volumes:
      - ./iot_data.db:/app/iot_data.db
      - ./runtime:/app/runtime
      - ./config.json:/app/config.json:ro
      - ./experiment_results:/app/experiment_results
    restart: "no"
```

실행:

```powershell
cd C:\access\iot
docker compose up -d iot-dashboard
```

중지:

```powershell
docker compose stop iot-dashboard
```

상태 확인:

```powershell
docker ps
curl http://127.0.0.1:5000/api/system/status
curl http://127.0.0.1:5000/api/db/status
```

## 7. DB 운영 상태와 주의점

현재 구조는 Docker가 Windows의 SQLite DB 파일을 직접 bind mount하여 사용한다.

운영 DB:

```text
C:\access\iot\iot_data.db
```

Docker 내부 경로:

```text
/app/iot_data.db
```

DB 보호를 위해 다음 설정을 적용했다.

```text
DB_JOURNAL_MODE=DELETE
DB_BUSY_TIMEOUT_MS=30000
DB_LOCK_RETRIES=10
```

주의:

- Windows와 Docker가 같은 SQLite 파일을 직접 공유하면 성능 저하와 lock 대기가 발생할 수 있다.
- DB 손상 방지를 위해 한쪽만 운영해야 한다.
- 장기 상용 운영에서는 Docker volume SQLite 또는 PostgreSQL/TimescaleDB 전환이 권장된다.

## 8. 수집 지연 경고 기능

대시보드에 평균 수집 간격 대비 지연 여부를 표시하는 옵션을 추가했다.

설정 위치:

```json
"collection_delay_warning": {
  "enabled": true,
  "late_multiplier": 2,
  "window": 200,
  "min_samples": 5
}
```

UI 옵션:

- 수집 지연 경고 ON/OFF
- 지연 기준: 평균 x 1.5, x 2, x 3, x 5

관련 API:

```text
GET /api/collection-warnings
```

## 9. 기존 Raspberry Sensor Publisher

파일:

```text
device/raspi_iot_publisher.py
```

설정:

```text
device/client.config
```

역할:

- Raspberry에서 센서 payload 발행
- APR policy topic 구독
- QoS, compression, encryption, integrity policy 반영
- 기존 센서 데이터 포맷 유지

실행:

```bash
cd ~/client
python raspi_iot_publisher.py --config client.config
```

또는:

```bash
./run_raspi_client.sh
```

기존 publisher 파일은 시스템 메트릭 기능 추가 과정에서 수정하지 않았다.

## 10. Raspberry System Metrics Publisher

새 파일:

```text
device/raspi_system_metrics_publisher.py
```

전용 설정:

```text
device/system_metrics.config
```

실행:

```bash
cd ~/client
python raspi_system_metrics_publisher.py --config system_metrics.config
```

또는:

```bash
./run_raspi_system_metrics.sh
```

수집 항목:

- `cpu_percent`
- `memory_percent`
- `cpu_temp_c`
- `disk_percent`
- `load_1m`

추가 지원 항목:

- `memory_used_mb`
- `memory_total_mb`
- `disk_used_gb`
- `disk_total_gb`

## 11. System Metrics Config

현재 `device/system_metrics.config`:

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
policy = iot/sensor/policy/raspi_001

[runtime]
enabled = true
interval = 5.0
experiment_id = RASPI_SYSTEM_RUNTIME
metrics = cpu_percent,memory_percent,cpu_temp_c,disk_percent,load_1m

[security]
apr_aes_key_hex = 01010101010101010101010101010101
```

## 12. System Metrics Topic 구조

현재 시스템 메트릭은 metric별 topic을 만들지 않고 하나의 topic으로 관리한다.

구성 규칙:

```text
{topic_prefix}/{device_id}_system
```

현재 실제 publish topic:

```text
iot/sensor/system/raspi_001_system
```

원격 제어/APR policy 구독 topic:

```text
iot/sensor/policy/raspi_001
iot/sensor/policy/raspi_001/system
iot/sensor/policy/raspi_001_system
```

## 13. System Metrics Payload 예시

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
  "timestamp": "2026-06-02T00:00:00+00:00",
  "publish_timestamp": "2026-06-02T00:00:00+00:00",
  "policy": {
    "qos": 0,
    "compression": "none",
    "encryption": "none",
    "integrity": "none"
  }
}
```

현재 서버 기준으로 이 payload는 `value` 필드가 없는 복합 JSON이므로 `unknown_payload_data`로 분류될 수 있다. 단일 topic 관리와 device health 모니터링 목적에는 적합하지만, dashboard 그래프에 metric별 선 그래프로 표시하려면 `server.py`에 `system_metrics` payload 파싱 로직을 추가하는 것이 좋다.

## 14. 원격 옵션 변경

System metrics publisher는 policy/control topic을 구독하여 런타임 옵션 변경을 지원한다.

전송 주기 변경:

```json
{
  "command": "set_options",
  "interval": 10
}
```

수집 metric 변경:

```json
{
  "command": "set_options",
  "metrics": ["cpu_percent", "memory_percent", "cpu_temp_c"]
}
```

일시 중지:

```json
{
  "command": "pause"
}
```

재개:

```json
{
  "command": "resume"
}
```

APR policy 변경:

```json
{
  "qos": 1,
  "compression": "gzip",
  "encryption": "AES-GCM",
  "integrity": "sha256"
}
```

## 15. APR Gateway

APR Gateway는 `apr_gateway/`에 별도 서비스로 구성되어 있다.

역할:

- MQTT source broker 구독
- APR decision engine 적용
- 필요 시 payload forwarding
- XGBoost 기반 모델 로딩
- Docker/Ubuntu 운영 준비

현재 gateway는 IoT dashboard와 별도 서비스로 운영 가능하다.

## 16. 현재 성능 이슈

최근 dashboard 출력 지연 원인:

```text
Windows SQLite 파일 공유
Docker bind mount
DELETE journal mode
DB lock 대기
데이터 증가
대시보드 다중 API 호출
```

보완 조치:

- `DB_BUSY_TIMEOUT_MS=30000`
- `DB_LOCK_RETRIES=10`
- dashboard API lock 대기 개선

장기 권장:

```text
1. Docker volume SQLite로 운영하고 Windows는 API/백업으로 접근
2. 또는 PostgreSQL/TimescaleDB로 전환
3. system_metrics payload 전용 테이블 추가
```

## 17. 향후 개선 과제

우선순위 높은 개선:

1. `system_metrics` payload를 서버에서 별도 테이블로 정규 저장
2. Raspberry device health dashboard 추가
3. Windows/Docker DB 직접 공유 구조 제거
4. PostgreSQL 또는 TimescaleDB 전환 검토
5. APR Gateway와 dashboard 간 운영 상태 연계
6. 원격 config 변경 이력 저장
7. device별 heartbeat/last seen 관리
8. system shutdown/start operation manual 정리

## 18. 현재 운영 명령 요약

Dashboard Docker 실행:

```powershell
cd C:\access\iot
docker compose up -d iot-dashboard
```

Dashboard 상태:

```powershell
docker ps
curl http://127.0.0.1:5000/api/system/status
curl http://127.0.0.1:5000/api/db/status
```

Dashboard 안전 종료:

```powershell
Invoke-WebRequest -UseBasicParsing -Method POST http://127.0.0.1:5000/api/system/shutdown
```

Raspberry 센서 publisher:

```bash
python raspi_iot_publisher.py --config client.config
```

Raspberry 시스템 메트릭 publisher:

```bash
python raspi_system_metrics_publisher.py --config system_metrics.config
```

## 19. 결론

현재 시스템은 단순 MQTT 수집 대시보드에서 출발하여 APR 정책 제어, payload 분석, Raspberry edge publisher, Raspberry system health publisher, Docker 운영 보호 기능까지 확장되었다.

PoC 단계에서는 현재 구조로 운영 가능하지만, 상용화 또는 장기 운영을 위해서는 DB 공유 구조 개선, system metrics 전용 저장 구조, device 상태 관리 dashboard 추가가 다음 단계 핵심 과제다.
