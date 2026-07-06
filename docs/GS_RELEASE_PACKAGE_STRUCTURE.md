# GS Certification Release Package Structure

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0

## 1. 목적

이 문서는 GS 인증 제출용 제품 패키지의 구성 기준을 정의한다. 인증 패키지는 Docker 기준 실행을 우선으로 하며, 기존 기능과 code/process는 삭제하지 않는다. 단, 인증 평가 범위와 제출 문서는 상용 운영 기능 중심으로 구성한다.

## 2. 인증용 기본 실행 파일

| 파일 | 용도 |
|---|---|
| `Dockerfile` | 제품 서버 이미지 생성 |
| `docker-compose.cert.yml` | GS 인증 기준 Docker compose |
| `config.example.json` | 인증용 MQTT/APR/platform 설정 예시 |
| `.env.example` | 인증용 환경변수 예시 |
| `mosquitto/config/mosquitto.conf` | 인증용 로컬 MQTT broker 설정 |

## 3. 권장 패키지 구조

```text
apr-edgeinsight-v1.0/
  Dockerfile
  docker-compose.cert.yml
  config.example.json
  .env.example
  requirements.txt
  server.py
  distributed_broker.py
  sensor_registry.py
  policy/
  database/
  monitor/
  publisher/
  device/
  apr/
  templates/
  static/
  tools/
  mosquitto/
    config/
      mosquitto.conf
  docs/
```

## 4. 인증 패키지 포함 기준

| 경로 | 포함 사유 |
|---|---|
| `server.py` | 메인 서버 및 REST API |
| `policy/` | APR 추천 및 codec |
| `database/` | SQLite writer |
| `monitor/` | queue monitor |
| `publisher/` | MQTT publish helper |
| `device/` | PC/Raspberry Pi/Ubuntu client |
| `apr/` | APR runtime model 및 모델 학습 자동화 |
| `templates/`, `static/` | 인증 대상 UI |
| `tools/check_*.py` | 상태 점검 도구 |
| `tools/e2e_*.py` | 자체 테스트 도구 |
| `tools/export_apr_xgb_runtime.py` | 모델 runtime export 도구 |

## 5. 인증 패키지 제외 기준

| 경로/패턴 | 제외 사유 |
|---|---|
| `iot_data.db`, `iot_data.db-wal`, `iot_data.db-shm` | 운영 데이터 |
| `*.bak`, `*.corrupt*`, `*.malformed*`, `*.recovered*` | 백업/복구 파일 |
| `*.log` | 운영 로그 |
| `experiment_results/` | 실험 결과 |
| `docs/thesis_*`, `docs/thesis_review_sections/` | 논문 자료 |
| 대용량 발표/제안 자료 | 인증 실행 제품과 직접 관련 없음 |
| `__pycache__/` | Python cache |

## 6. 인증 실행 명령

```powershell
copy .env.example .env.cert
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

접속 URL:

```text
http://localhost:4728
```

초기 관리자 예시:

```text
admin@example.com / admin1234
```

실제 운영 전에는 `.env.cert`의 계정, Flask secret, APR AES key를 변경해야 한다.

