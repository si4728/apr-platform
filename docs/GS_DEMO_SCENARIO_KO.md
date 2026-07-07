# GS 인증 사전 상담용 시연 시나리오

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 인증 시험기관 사전 상담 또는 사전 기술 검토 시 제품 실행 흐름과 인증 범위를 설명하기 위한 시연 절차

## 1. 시연 목표

본 시연은 APR EdgeInsight Industrial IoT Platform v1.0이 Docker 환경에서 실행되고, 관리자 로그인, 시스템 상태 확인, 장비/client package 관리, APR 정책 운영, 증적 리포트 생성, 제출 패키지 구성까지 GS 인증 범위의 핵심 흐름을 수행할 수 있음을 보여주는 것을 목표로 한다.

## 2. 시연 전 준비

| 항목 | 준비 내용 |
|---|---|
| 실행 환경 | Windows Docker Desktop 또는 Ubuntu Docker Engine |
| 프로젝트 위치 | `C:\access\iot` 또는 시험기관 지정 경로 |
| 환경 파일 | `.env.example`을 `.env.cert`로 복사 후 secret 값 변경 |
| 포트 | Web 4728, MQTT 1883 사용 가능 상태 |
| 브라우저 | Chrome 또는 Edge |
| 제출 증적 | `runtime/gs_certification_evidence/` 내 report 파일 |

사전 명령:

```powershell
python tools/check_certification_config.py --env-file .env.cert
docker compose -f docker-compose.cert.yml --env-file .env.cert config --quiet
```

## 3. 시연 흐름 요약

| 순서 | 시연 항목 | 예상 시간 | 확인 결과 |
|---:|---|---:|---|
| 1 | 보안 설정 검증 | 1분 | `status=ok` |
| 2 | Docker 서버 기동 | 3~10분 | dashboard, MQTT broker container 실행 |
| 3 | Web 로그인 | 1분 | 관리자 Dashboard 진입 |
| 4 | 시스템/API 상태 확인 | 2분 | system/broker/db status 정상 |
| 5 | Fleet/Device 관리 설명 | 3분 | Device topic과 client package 생성 흐름 확인 |
| 6 | Client package 확인 | 3분 | PC/Raspberry Pi/Ubuntu Linux package 구성 확인 |
| 7 | APR 정책 추천·배포 설명 | 3분 | policy topic 기반 동적 변경 구조 설명 |
| 8 | APR 모델 자동화 증적 확인 | 2분 | APR automation report 확인 |
| 9 | Live E2E/Readiness report 확인 | 2분 | `status=ok` report 확인 |
| 10 | 제출 패키지 manifest 확인 | 2분 | secret/DB/log 제외 및 필수 문서 포함 확인 |

## 4. 상세 시연 절차

### 4.1 보안 설정 검증

```powershell
python tools/check_certification_config.py --env-file .env.cert
```

확인할 점:

- `CERTIFICATION_MODE=true`
- 기본 password, 기본 Flask secret, 기본 APR AES key 사용 차단
- secret 원문은 report에 표시하지 않음

### 4.2 Docker 서버 기동

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

상태 확인:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert ps
```

확인할 컨테이너:

| 컨테이너 | 역할 |
|---|---|
| `apr-cert-dashboard` | Flask Dashboard, REST API, MQTT subscriber |
| `apr-cert-mqtt` | 인증용 MQTT broker |

### 4.3 Web 로그인

브라우저에서 접속한다.

```text
http://localhost:4728
```

관리자 계정:

| 항목 | 값 |
|---|---|
| Email | `.env.cert`의 `IOT_ADMIN_EMAIL` |
| Password | `.env.cert`의 `IOT_ADMIN_PASSWORD` |

확인할 점:

- 로그인 성공
- Dashboard 화면 진입
- 사용자 권한에 따라 관리자 메뉴 접근 가능

### 4.4 시스템 상태 API 확인

로그인 후 다음 API를 확인한다.

```text
/api/system/status
/api/broker/status
/api/db/status
```

확인할 점:

- system lock 활성화
- DB writer 상태 반환
- MQTT broker 연결 또는 startup 상태 반환
- DB health/status 반환

### 4.5 Fleet/Device 등록 및 client package 설명

Device Management 화면에서 다음 흐름을 설명한다.

1. Fleet 등록
2. Device 등록
3. Device OS 선택
4. telemetry topic과 policy topic 자동 생성
5. client package 다운로드

Device OS별 package:

| OS | 주요 파일 |
|---|---|
| `windows_pc` | `pc_test_publisher.py`, `run_pc_test_publisher.bat`, `client.config` |
| `raspberry_pi` | `raspi_iot_publisher.py`, `raspi_system_metrics_publisher.py`, `run_raspi_client.sh`, `run_raspi_system_metrics.sh` |
| `ubuntu_linux` | `pc_test_publisher.py`, `run_pc_test_publisher.sh`, `client.config` |

### 4.6 Dynamic Client Policy Control 설명

정책 적용 흐름:

```text
관리자 Dashboard
  -> Device/Fleet 정책 적용
  -> MQTT policy topic publish
  -> client policy topic subscribe
  -> QoS/압축/암호화/무결성 runtime 반영
```

확인할 정책 항목:

| 항목 | 예시 |
|---|---|
| QoS | `0`, `1`, `2` |
| Compression | `none`, `zlib`, `gzip` |
| Encryption | `none`, `AES-GCM` |
| Integrity | `none`, `sha256` |

### 4.7 Client Runtime Configuration Update 설명

Raspberry Pi system metrics client는 policy topic을 통해 다음 runtime option을 변경할 수 있다.

| 항목 | 설명 |
|---|---|
| interval | 수집 주기 변경 |
| metrics | 수집 metric 목록 변경 |
| pause/resume | 수집 일시중지 및 재개 |

이 기능은 GS 인증 범위에 포함한다.

### 4.8 APR 모델 학습 자동화 증적 확인

```powershell
python tools/run_apr_model_automation.py --skip-export
```

확인할 산출물:

```text
runtime/apr_model_automation_report.json
```

확인할 점:

- model artifact 존재
- metric CSV 존재
- runtime loading/recommendation check 정상
- fallback 동작 가능성 문서화

### 4.9 E2E 및 readiness report 확인

```powershell
python tools/generate_gs_e2e_preflight_report.py
python tools/generate_gs_live_e2e_report.py --env-file .env.cert --no-build
python tools/generate_gs_readiness_review.py
```

확인할 산출물:

| 리포트 | 기대 상태 |
|---|---|
| `gs_e2e_preflight_report.json` | `ok` |
| `gs_live_e2e_report.json` | `ok` |
| `gs_readiness_review.json` | `ok` |

### 4.10 제출 패키지 생성 및 manifest 확인

```powershell
python tools/build_gs_submission_package.py --clean --include-evidence --zip
```

확인할 산출물:

```text
runtime/gs_submission_package/apr-edgeinsight-gs-submission/
runtime/gs_submission_package/apr-edgeinsight-gs-submission.zip
```

manifest 확인 항목:

- 제품 실행 파일 포함
- 제품설명서, 사용자취급설명서, 테스트 케이스 포함
- E2E/Live E2E/readiness 증적 포함
- `.env.cert`, DB, log, venv, cache 제외
- 각 파일 SHA-256 hash 기록

## 5. 시연 중 강조할 인증 범위

| 항목 | 설명 방식 |
|---|---|
| APR 모델 학습 자동화 | 인증 포함 기능. 모델 artifact와 runtime loading 증적 생성 가능 |
| Dynamic Client Policy Control | 인증 포함 기능. MQTT policy topic 기반 client runtime 정책 변경 |
| Client Runtime Configuration Update | 인증 포함 기능. system metrics client runtime option 변경 |
| PC/Raspberry Pi/Ubuntu Linux client | 인증 포함 기능. OS별 client package 생성과 실행 절차 제공 |
| Voice streaming | 기존 code/process는 유지하지만 GS 인증 범위에서는 제외 |

## 6. 예상 질문 및 답변

| 예상 질문 | 답변 요지 |
|---|---|
| Docker 기반으로 시험 가능한가? | `docker-compose.cert.yml`과 `.env.cert` 기준으로 동일 실행 조건 재현 가능 |
| secret은 어떻게 제출하는가? | `.env.example`만 제출하고 `.env.cert`는 시험 환경에서 별도 작성. report에는 secret 원문 미기록 |
| APR 모델 학습 자동화는 제품 기능인가? | 운영 정책 추천 모델을 갱신·검증하기 위한 제품 기능으로 인증 범위에 포함 |
| voice streaming은 왜 제외하는가? | 연구/확장 기능으로 code/process는 유지하되 상용 운영 인증 범위에서 제외 |
| 실제 실행 증적이 있는가? | Docker Live E2E report에서 Web/Login/System/Broker/DB API 200 응답 확인 |
| 제출 패키지에 DB나 로그가 들어가는가? | package builder가 DB, log, secret, venv, cache를 자동 제외하고 manifest로 검증 |

## 7. 시연 종료

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down
```

시험 데이터까지 초기화해야 하는 경우에만 다음 명령을 사용한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down -v
```