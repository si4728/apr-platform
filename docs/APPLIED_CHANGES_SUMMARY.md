# APR / IoT Dashboard 적용 내역 요약

작성일: 2026-06-03

## 1. 전체 개요

현재 시스템은 기존 MQTT 기반 IoT 수집 대시보드에 APR 최적화, Docker 운영, DB 보호, 사용자 권한 관리, Device/Fleet 관리 기능을 단계적으로 추가한 상태이다.

핵심 방향은 기존 MQTT payload를 가능한 그대로 수집하면서, 운영 장치와 사용자를 분리 관리하고, 향후 APR Optimization Gateway 및 Raspberry Pi edge client와 연계 가능한 구조를 만드는 것이다.

## 2. Docker 운영 구조

적용된 내용:

- `iot-dashboard` Docker 서비스 운영 확인
- `docker compose up -d --build iot-dashboard` 기반 재빌드 및 실행 확인
- Docker 실행 후 `http://127.0.0.1:5000/login` 접속 확인
- Docker 컨테이너 상태 `healthy` 확인
- 이전 컨테이너 종료 후 남은 stale lock 정리 절차 확인

운영 확인 명령:

```powershell
cd C:\access\iot
docker compose ps
docker ps
curl http://127.0.0.1:5000/login
```

주의:

- 화면에 나타난 `Error launching app / Unable to find Electron app` 메시지는 Docker 문제가 아니라 Codex/OpenAI Electron 앱 연결 오류이다.
- Docker 컨테이너가 `healthy`이면 IoT Dashboard 운영에는 직접 영향이 없다.

## 3. DB 보호 및 시스템 Lock

적용된 내용:

- Windows 실행과 Docker 실행이 같은 SQLite DB를 동시에 쓰지 않도록 system lock 기능 추가
- 실행 중인 시스템 정보 저장
- stale lock 판정
- dashboard에서 시스템 shutdown 가능
- 비정상 종료 후 남은 lock으로 새 컨테이너가 시작되지 않는 경우 확인 및 정리 절차 검증

관련 기능:

- `/api/system/status`
- `/api/system/shutdown`

효과:

- Windows/Docker 양쪽 동시 실행으로 인한 SQLite DB 손상 위험 감소
- 운영자가 현재 어느 환경에서 DB를 사용 중인지 확인 가능

## 4. 사용자 및 권한 관리

적용된 내용:

- 로그인/로그아웃 기능 추가
- 사용자 테이블 추가
- 관리자/일반 사용자 역할 분리
- 계정 상태 `ACTIVE`, `SUSPENDED` 관리
- 접근 로그 및 감사 로그 저장
- 일반 사용자와 관리자 메뉴 분리

기본 계정:

```text
ADMIN: admin@example.com / admin1234
USER : user@example.com  / user1234
```

운영 시 권장:

- 운영 배포 전 기본 비밀번호 변경
- 환경변수로 초기 계정 변경 가능
  - `IOT_ADMIN_EMAIL`
  - `IOT_ADMIN_PASSWORD`
  - `IOT_USER_EMAIL`
  - `IOT_USER_PASSWORD`

관리자 전용 기능:

- User Management
- Access Logs
- Audit Logs
- Sensor Config
- Queue Monitor
- Experiment Runner
- Schema Intelligence
- APR Dashboard
- Voice Streaming
- Server Operation Manual

일반 사용자 기능:

- Telemetry Dashboard
- All Sensors
- Latency Analysis
- Device/Fleet Management
- Device Edge README

## 5. Device/Fleet 관리

적용된 내용:

- 운영 장치를 `config.json`의 시뮬레이션 센서 설정과 분리
- DB 기반 `fleets`, `devices` 테이블 추가
- 사용자별 기본 Fleet 자동 생성
- Device 등록 시 소유 사용자 지정
- Device를 Fleet 단위로 그룹 관리
- 일반 사용자는 자기 Fleet/Device만 조회 및 관리
- 관리자는 전체 사용자 Fleet/Device 조회 및 관리
- Device와 Fleet의 소유자가 다르면 등록 차단

추가된 화면:

- `/device_management`

추가된 API:

- `GET /api/fleets`
- `POST /api/fleets`
- `PUT /api/fleets/<fleet_id>`
- `DELETE /api/fleets/<fleet_id>`
- `GET /api/devices`
- `POST /api/devices`
- `PUT /api/devices/<device_row_id>`
- `DELETE /api/devices/<device_row_id>`
- `GET /api/admin/users/options`

Device 주요 필드:

- `device_id`
- `device_name`
- `device_type`
- `fleet_id`
- `owner_user_id`
- `status`
- `topic_prefix`
- `telemetry_topic`
- `policy_topic`
- `description`

기본 topic 생성 방식:

```text
telemetry_topic = {topic_prefix}/{device_type}/{device_id}
policy_topic    = iot/sensor/policy/{device_id}
```

## 6. Sensor Config와 Device Management의 차이

`Sensor Config`:

- `config.json` 기반
- 시뮬레이션 센서 및 대시보드 정의 관리
- 관리자 전용
- 기존 sensor topic, payload schema mode, graph color rule 관리

`Device/Fleet Management`:

- DB 기반
- 실제 운영 장치 등록부
- 사용자별 소유권 관리
- Fleet 단위 관리
- 일반 사용자도 자기 장치 관리 가능

## 7. 수집 지연 경고 기능

적용된 내용:

- Dashboard 수집 데이터 기준 평균 수집 시간보다 늦어지는 경우 경고 가능
- `collection_warning` 상태 계산
- 수집 지연 임계값 설정
- 화면에서 정상/지연 상태 표시

관련 API:

- `/api/collection-warnings`

효과:

- 특정 sensor/topic의 데이터 도착 지연을 운영자가 빠르게 확인 가능
- MQTT broker, client, network, DB writer 지연 문제 진단에 활용 가능

## 8. Raspberry Pi Client / System Metrics

적용된 내용:

- 기존 `raspi_iot_publisher.py`에 영향 없이 별도 system metrics publisher 설계
- Raspberry Pi 자체 상태 수집 항목 추가
  - CPU
  - Memory
  - Temperature
  - Disk
  - Network
- 별도 config 파일 기반 실행 구조 적용
- metric별 topic 분리 대신 하나의 system metrics topic으로 전송하도록 정리
- 원격 정책 변경을 받을 수 있는 양방향 구조 반영

설계 방향:

- 기존 sensor publisher는 유지
- system metrics publisher는 별도 파일로 운영
- device id, device name, publish interval 등은 config에서 관리
- 향후 Device/Fleet 등록부와 연계 가능

## 9. APR Optimization Gateway

적용된 내용:

- APR Gateway를 별도 Docker/Windows 실행 대상으로 분리하는 방향 검토
- 초기 단계에서는 Docker보다 Windows 직접 실행 우선
- 원격 MQTT broker IP 사용
- XGBoost 모델 기반 decision engine 로딩 확인
- proxy mode 실행 확인
- message received/forwarded/failed metric 확인
- XGBoost joblib 직렬화 경고 대응을 위해 `save_model` export 방식 검토 및 export script 작성 방향 정리

현재 방향:

- ThingsBoard 같은 전체 IoT 플랫폼을 대체하기보다, ThingsBoard/EMQX/AWS IoT Core 앞단 또는 옆단의 최적화 Gateway로 포지셔닝
- 기존 MQTT payload를 수정 없이 수집 가능
- 정확한 측정을 위해 client module 일부 변경이 필요한 문제는 단계적 PoC 전략으로 대응

## 10. Unknown Payload / Schema 대응

적용된 내용:

- 정의된 sensor schema에 맞지 않는 payload는 별도 unknown payload 테이블에 저장
- payload schema hash/fingerprint 관리
- unknown schema profile 저장
- 기존 payload를 강제로 변경하지 않고도 수집 및 분석 가능

효과:

- PoC 초기 단계에서 기존 MQTT payload를 그대로 받아 데이터 손실 없이 분석 가능
- 이후 표준 schema 전환 또는 client module 개선 근거 확보 가능

## 11. 테스트 완료 내역

수행한 테스트:

- `server.py` Python 문법 검사 통과
- `database/db_manager.py` Python 문법 검사 통과
- `static/js/common_menu.js` JS 문법 검사 통과
- `static/js/device_management.js` JS 문법 검사 통과
- 임시 DB 기반 Flask 권한/API 테스트 통과
  - 총 15개 테스트 통과
  - 익명 사용자 redirect 확인
  - 일반 사용자 Device/Fleet 접근 확인
  - 관리자 전체 조회 확인
  - 일반 사용자가 관리자 장치를 볼 수 없음 확인
  - 일반 사용자가 관리자 Fleet에 장치를 붙일 수 없음 확인
- Docker 재빌드 및 실행 확인
- Docker container `healthy` 확인
- 실제 Docker HTTP smoke test 통과
  - 로그인
  - `/device_management` 접속
  - Fleet 생성
  - Device 생성
  - Device 조회
  - Device 삭제
  - Fleet 삭제

## 12. 현재 주요 변경 파일

서버:

- `server.py`

Frontend:

- `static/js/common_menu.js`
- `static/js/device_management.js`
- `static/css/dashboard_common.css`

Templates:

- `templates/login.html`
- `templates/permission_denied.html`
- `templates/admin_users.html`
- `templates/admin_logs.html`
- `templates/device_management.html`

문서:

- `docs/USER_PERMISSION_IMPLEMENTATION.md`
- `docs/SYSTEM_DETAILED_ANALYSIS.md`
- `docs/APPLIED_CHANGES_SUMMARY.md`

## 13. 운영 시 확인 절차

Docker 실행:

```powershell
cd C:\access\iot
docker compose up -d iot-dashboard
```

상태 확인:

```powershell
docker ps
curl http://127.0.0.1:5000/login
```

웹 접속:

```text
http://127.0.0.1:5000/login
```

시스템 상태 확인:

```text
http://127.0.0.1:5000/api/system/status
```

DB 테이블 확인:

```powershell
docker exec iot-dashboard python -c "import sqlite3; conn=sqlite3.connect('/app/iot_data.db'); cur=conn.cursor(); [print(t, cur.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('users','fleets','devices')]; conn.close()"
```

## 14. 남은 개선 과제

우선순위가 높은 항목:

- 기본 관리자 비밀번호 변경 UI 추가
- Device/Fleet와 실제 수집 topic 매핑 강화
- Raspberry Pi client가 서버의 Device/Fleet 등록 정보를 원격 조회하도록 개선
- Device별 API key 또는 token 인증 추가
- 사용자별 dashboard filtering 적용
- Fleet 단위 통계 화면 추가
- APR 정책을 device/fleet 단위로 적용하는 기능 추가
- SQLite 장기 운영 시 PostgreSQL 전환 검토
- Docker 운영 환경에서 `.env` 기반 secret 관리 강화

## 15. 결론

현재 시스템은 단순 IoT Dashboard에서 벗어나 사용자, 장치, Fleet, 수집 지연, APR 최적화 Gateway까지 확장 가능한 운영 플랫폼 구조로 발전했다.

특히 Device/Fleet 관리 기능이 추가되면서 향후 스마트팩토리 업체와 협업할 때 고객사별 장치 등록, 라인별 Fleet 관리, APR 정책 적용 범위 설정이 가능해졌다.

다음 단계는 실제 Raspberry Pi client와 Device/Fleet 등록부를 연결하고, Fleet 단위 APR 정책 및 운영 통계를 제공하는 것이다.
