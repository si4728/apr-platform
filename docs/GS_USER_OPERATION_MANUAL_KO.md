# GS 인증 사용자취급설명서

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
문서 목적: GS 인증 제출용 사용자 설치, 운영, client 실행, APR 정책 운영, 증적 생성 절차 설명

## 1. 사용 대상

이 문서는 APR EdgeInsight Industrial IoT Platform을 설치하고 운영하는 시스템 관리자, 현장 운영자, 장비 관리자를 대상으로 한다.

| 사용자 | 주요 작업 |
|---|---|
| 시스템 관리자 | Docker 설치, `.env.cert` 작성, 서버 기동/중지, 보안 설정 검증, 사용자 관리 |
| 현장 운영자 | Dashboard 확인, 센서 데이터/latency/queue/schema/APR 상태 확인 |
| 장비 관리자 | Fleet/Device 등록, client package 다운로드, client 실행, 정책 적용 확인 |

## 2. 인증 범위 안내

본 사용자취급설명서는 GS 인증 범위에 포함된 상용 운영 기능을 설명한다.

| 구분 | 인증 범위 |
|---|---|
| Docker 기반 서버 실행 | 포함 |
| PC/Raspberry Pi/Ubuntu Linux client package 생성 및 실행 | 포함 |
| Dynamic Client Policy Control | 포함 |
| Client Runtime Configuration Update | 포함 |
| APR 모델 학습 자동화 및 증적 생성 | 포함 |
| E2E 사전 점검 리포트 생성 | 포함 |
| 제출 패키지 자동 구성 | 포함 |
| Voice streaming 관련 기능 | 기존 code/process는 유지하되 GS 인증 평가 범위에서는 제외 |

## 3. 설치 전 준비

필수 도구는 다음과 같다.

| 항목 | 권장 조건 |
|---|---|
| OS | Windows 11 + Docker Desktop 또는 Ubuntu Linux + Docker Engine |
| Docker Compose | Compose v2 |
| Python | 3.11 이상 권장 |
| Browser | Chrome 또는 Edge |
| Network port | Web 4728, MQTT 1883 |

## 4. 인증용 환경 파일 작성

1. 프로젝트 루트로 이동한다.
2. `.env.example`을 `.env.cert`로 복사한다.
3. `.env.cert`의 모든 `CHANGE_ME` 값을 실제 인증 환경 값으로 변경한다.
4. `.env.cert`는 secret을 포함하므로 Git에 커밋하지 않는다.

PowerShell 예시:

```powershell
cd C:\access\iot
copy .env.example .env.cert
notepad .env.cert
```

필수 변경 항목:

| 환경변수 | 설명 |
|---|---|
| `IOT_ADMIN_PASSWORD` | 초기 관리자 비밀번호. 기본값 또는 placeholder 사용 금지 |
| `IOT_USER_PASSWORD` | 초기 일반 사용자 비밀번호. 기본값 또는 placeholder 사용 금지 |
| `FLASK_SECRET_KEY` | Flask session secret. 24자 이상 권장 |
| `APR_AES_KEY_HEX` | APR AES-GCM key. 32/48/64자리 hex 문자열 |

## 5. 보안 설정 검증

서버 실행 전 보안 설정을 검증한다.

```powershell
python tools/check_certification_config.py --env-file .env.cert
```

정상 결과 예:

```text
status=ok
[OK] CERTIFICATION_MODE: ...
[OK] FLASK_SECRET_KEY: ...
[OK] IOT_ADMIN_PASSWORD: ...
[OK] IOT_USER_PASSWORD: ...
[OK] APR_AES_KEY_HEX: ...
```

`.env.example`은 템플릿이므로 그대로 검증하면 실패하는 것이 정상이다.

## 6. Docker 서버 실행

인증용 Docker compose를 사용하여 서버와 MQTT broker를 실행한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

상태 확인:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert ps
docker compose -f docker-compose.cert.yml --env-file .env.cert logs -f iot-dashboard
```

접속 주소:

```text
http://localhost:4728
```

서버 중지:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down
```

데이터 볼륨까지 삭제하려면 다음 명령을 사용한다. 시험 데이터가 삭제되므로 주의한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down -v
```

## 7. 로그인

초기 DB에 사용자가 없으면 `.env.cert` 기준으로 관리자와 일반 사용자 계정이 생성된다.

1. 브라우저에서 `http://localhost:4728` 접속
2. 관리자 email 입력
3. 관리자 비밀번호 입력
4. Dashboard 진입 확인

초기 email 기본값:

| 계정 | 기본 email |
|---|---|
| 관리자 | `admin@example.com` |
| 일반 사용자 | `user@example.com` |

비밀번호는 반드시 `.env.cert`에 설정한 값으로 사용한다.

## 8. Fleet 등록

1. 관리자 계정으로 로그인한다.
2. Device Management 화면으로 이동한다.
3. Fleet 추가 기능을 실행한다.
4. Fleet 이름과 설명을 입력한다.
5. 저장 후 Fleet 목록에 신규 Fleet가 표시되는지 확인한다.

검증 포인트:

- Fleet ID가 생성된다.
- Fleet별 topic prefix가 자동 구성된다.
- 이후 Device 등록 시 Fleet를 선택할 수 있다.

## 9. Device 등록

1. Device Management 화면으로 이동한다.
2. Device 추가 기능을 실행한다.
3. Device ID, Device name, Device type, Device OS, Fleet를 입력한다.
4. 저장 후 Device 목록에 신규 장비가 표시되는지 확인한다.

Device OS 선택 기준:

| OS | 용도 |
|---|---|
| `windows_pc` | Windows PC 테스트 publisher |
| `raspberry_pi` | Raspberry Pi 센서 및 system metrics publisher |
| `ubuntu_linux` | Ubuntu/Linux edge 또는 테스트 publisher |

등록 후 확인할 topic:

| Topic | 설명 |
|---|---|
| telemetry topic | client telemetry publish 대상 |
| policy topic | 서버가 동적 정책을 publish하는 대상 |

## 10. PC client package 다운로드 및 실행

1. Device Management에서 Windows PC 대상 장비를 선택한다.
2. Client package 다운로드를 실행한다.
3. zip 파일을 PC에 압축 해제한다.
4. `client.config`의 broker, topic, sensor_id를 확인한다.
5. Windows에서는 다음 파일을 실행한다.

```powershell
run_pc_test_publisher.bat
```

Linux PC에서 실행하는 경우:

```bash
./run_pc_test_publisher.sh
```

기대 결과:

- client가 MQTT broker로 telemetry를 publish한다.
- Dashboard에서 해당 device telemetry가 표시된다.

## 11. Raspberry Pi client package 다운로드 및 실행

1. Device Management에서 Raspberry Pi 대상 장비를 선택한다.
2. Client package를 다운로드한다.
3. Raspberry Pi에 압축 해제한다.
4. dependency를 설치한다.

```bash
pip install -r raspi-requirements.txt
```

센서 publisher 실행:

```bash
./run_raspi_client.sh
```

system metrics publisher 실행:

```bash
./run_raspi_system_metrics.sh
```

기대 결과:

- 센서 telemetry가 서버로 수집된다.
- CPU, memory, temperature, disk, load metric이 수집된다.
- policy topic을 통해 runtime 설정 변경을 받을 수 있다.

## 12. Ubuntu/Linux client package 다운로드 및 실행

1. Device OS를 `ubuntu_linux`로 등록한 장비를 선택한다.
2. Client package를 다운로드한다.
3. Ubuntu/Linux 환경에 압축 해제한다.
4. dependency를 설치한다.

```bash
pip install -r raspi-requirements.txt
```

실행:

```bash
./run_pc_test_publisher.sh
```

기대 결과:

- Linux 환경에서 telemetry publish가 수행된다.
- 서버 Dashboard와 API에서 데이터 수신을 확인할 수 있다.

## 13. Dashboard 상태 확인

주요 화면과 확인 내용은 다음과 같다.

| 화면/API | 확인 내용 |
|---|---|
| `/` | 전체 센서 및 시스템 요약 |
| `/device_management` | Fleet/Device/client package 관리 |
| `/queue_dashboard` | DB writer queue와 backlog |
| `/latency_dashboard` | latency 통계와 추세 |
| `/schema_dashboard` | unknown payload schema와 USI 관리 |
| `/apr_dashboard` | APR 추천, 정책 적용, 수집 상태 |
| `/api/system/status` | system lock, DB writer 상태 |
| `/api/broker/status` | MQTT broker 연결 상태 |
| `/api/db/status` | DB 상태 |

## 14. APR 정책 추천 및 배포

APR 정책 추천은 telemetry, payload 크기, latency, queue 상태 등을 기반으로 QoS, 압축, 암호화, 무결성 정책을 추천한다.

운영 절차:

1. client를 실행하여 telemetry를 수집한다.
2. APR Dashboard로 이동한다.
3. 대상 Device 또는 Fleet를 선택한다.
4. 정책 추천을 실행한다.
5. 추천 결과를 확인한다.
6. 정책 적용을 실행한다.
7. policy log와 client log에서 정책 변경 반영을 확인한다.

정책 항목:

| 항목 | 예시 |
|---|---|
| QoS | `0`, `1`, `2` |
| Compression | `none`, `zlib`, `gzip` |
| Encryption | `none`, `AES-GCM` |
| Integrity | `none`, `sha256` |

## 15. Dynamic Client Policy Control 확인

Dynamic Client Policy Control은 client가 policy topic을 구독하고, 서버가 publish한 정책을 runtime에 반영하는 기능이다.

확인 절차:

1. client 실행
2. 서버에서 Device 또는 Fleet 정책 적용
3. client log 확인
4. Dashboard/API에서 policy deployment log 확인

기대 결과:

- client runtime policy가 변경된다.
- telemetry publish 시 변경된 QoS/압축/암호화/무결성 정책이 적용된다.

## 16. Client Runtime Configuration Update 확인

System metrics client는 policy topic을 통해 수집 주기, metric 목록, pause/resume 등 runtime option을 변경할 수 있다.

확인 절차:

1. Raspberry Pi system metrics publisher 실행
2. 서버에서 runtime option 정책 publish
3. client log에서 interval, metrics, pause/resume 반영 확인
4. Dashboard에서 수집 주기 또는 metric 변화 확인

## 17. APR 모델 학습 자동화 증적 생성

APR 모델 학습 자동화는 GS 인증 범위에 포함된다. 다음 명령으로 모델 artifact, metric, runtime loading check 증적을 생성한다.

```powershell
python tools/run_apr_model_automation.py --skip-export
```

runtime export까지 포함하려면 `--skip-export`를 제거한다.

```powershell
python tools/run_apr_model_automation.py
```

기본 산출물:

```text
runtime/apr_model_automation_report.json
```

## 18. E2E 사전 점검 리포트 생성

실제 Docker E2E 실행 전 정적 준비 상태를 확인한다.

```powershell
python tools/generate_gs_e2e_preflight_report.py
```

산출물:

```text
runtime/gs_certification_evidence/gs_e2e_preflight_report.json
runtime/gs_certification_evidence/gs_e2e_preflight_report.md
```

## 19. 통합 증적 리포트 생성

보안 설정, Docker compose config, APR 모델 자동화, 필수 파일/문서 존재 여부를 통합 검증한다.

```powershell
python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export
```

산출물:

```text
runtime/gs_certification_evidence/gs_evidence_report.json
runtime/gs_certification_evidence/gs_evidence_report.md
runtime/gs_certification_evidence/apr_model_automation_report.json
```

## 20. GS 제출 패키지 생성

제출용 폴더와 zip을 자동 생성한다.

```powershell
python tools/build_gs_submission_package.py --clean --include-evidence --zip
```

산출물:

```text
runtime/gs_submission_package/apr-edgeinsight-gs-submission/
runtime/gs_submission_package/apr-edgeinsight-gs-submission.zip
```

`PACKAGE_MANIFEST.json`에서 포함 파일, 크기, SHA-256 hash를 확인한다.

## 21. 오류 조치

| 상황 | 원인 | 조치 |
|---|---|---|
| 보안 검증 실패 | `.env.cert`에 placeholder 또는 기본값 사용 | `CHANGE_ME`, `admin1234`, `user1234`, `010101...` 값을 실제 값으로 변경 |
| Docker compose config 실패 | 필수 환경변수 누락 | `.env.cert` 존재 여부와 필수 항목 확인 |
| Web 접속 실패 | container 미기동 또는 port 충돌 | `docker compose ps`, `logs`, port 4728 사용 여부 확인 |
| MQTT 연결 실패 | broker 미기동 또는 port 차단 | `mqtt-broker` container 상태와 port 1883 확인 |
| DB lock 오류 | 다른 서버 instance가 같은 DB 사용 | 기존 server/container 종료 후 재시작 |
| client package 다운로드 실패 | 장비 ID 오류 또는 권한 부족 | 관리자 로그인, Device 등록 상태 확인 |
| client 실행 실패 | dependency 미설치 또는 config 오류 | `pip install -r raspi-requirements.txt`, `client.config` 확인 |
| APR 모델 loading 실패 | ML dependency 또는 model artifact 누락 | `requirements.txt` 설치, `tools/run_apr_model_automation.py` 실행 |
| 통합 리포트 `attention_required` | 문서/파일/설정 일부 누락 | 리포트의 Required Files/Documents와 validation step 확인 |

## 22. 제출 전 확인

- `.env.cert`는 제출본과 Git에 포함하지 않는다.
- 운영 DB, 로그, cache, venv는 제출본에서 제외한다.
- 통합 증적 리포트는 `status=ok`이어야 한다.
- E2E 사전 점검 리포트는 `status=ok`이어야 한다.
- Voice streaming은 인증 범위 제외로 문서에 일관되게 표시한다.
- APR 모델 학습 자동화, 동적 client 정책 변경, client runtime 설정 변경은 인증 포함 기능으로 표시한다.