# GS 인증 제품설명서 초안

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
문서 목적: GS 인증 제출용 제품 규격, 기능 범위, 운영 환경, 제약사항 정의

## 1. 제품 개요

APR EdgeInsight Industrial IoT Platform은 산업 IoT 환경에서 PC, Raspberry Pi, Ubuntu/Linux edge client가 MQTT로 전송하는 센서 및 시스템 데이터를 수집하고, 대시보드와 REST API를 통해 장비 상태, 통신 지연, payload schema, queue 상태, APR 정책 상태를 관리하는 소프트웨어 제품이다.

본 제품은 APR(Adaptive Policy Recommendation) 기능을 통해 수집 데이터와 모델 기반 판단을 활용하여 QoS, 압축, 암호화, 무결성 정책을 추천하고, 장비 또는 Fleet 단위로 MQTT policy topic을 통해 동적으로 배포한다.

## 2. 인증 대상 제품

| 항목 | 내용 |
|---|---|
| 제품명 | APR EdgeInsight Industrial IoT Platform |
| 버전 | v1.0 |
| 제품 유형 | 산업 IoT 데이터 수집·관제·통신 정책 최적화 플랫폼 |
| 실행 방식 | Docker 기반 서버 실행, Python 기반 client 실행 |
| 주요 사용자 | 시스템 관리자, 현장 운영자, 장비 관리자 |
| 주요 운영 환경 | Windows Docker Desktop, Ubuntu Docker Engine, PC/Raspberry Pi/Ubuntu client |

## 3. 인증 범위

GS 인증 범위는 상용 운영에 필요한 기능으로 고정한다. 기존 저장소에 존재하는 연구/실험 기능과 voice stream 관련 code/process는 삭제하지 않지만, GS 인증 기능 평가 범위에서는 제외한다.

인증 포함 기능은 다음과 같다.

| 기능 ID | 기능명 | 설명 |
|---|---|---|
| F-001 | 사용자 인증 및 권한 관리 | 로그인, 관리자/일반 사용자 권한, 사용자 상태 관리 |
| F-002 | Dashboard 관제 | 센서 데이터, 시스템 상태, latency, queue, schema, APR 상태 확인 |
| F-003 | MQTT 데이터 수집 | client가 publish한 telemetry payload 수신 및 저장 |
| F-004 | SQLite 데이터 저장 | 센서 데이터, unknown schema, latency, 정책 로그 저장 |
| F-005 | 비동기 DB writer | queue 기반 batch write와 backlog 모니터링 |
| F-006 | Site/Group/Fleet/Device 관리 | 조직·그룹·Fleet·장비 등록, 수정, 삭제, topic 경로 관리 |
| F-007 | Client package 생성 | PC, Raspberry Pi, Ubuntu/Linux용 실행 패키지 생성 |
| F-008 | APR envelope codec | zlib/gzip 압축, AES-GCM 암호화, sha256 무결성 지원 |
| F-009 | APR 정책 추천 | XGBoost runtime model 또는 rule-based fallback 기반 정책 추천 |
| F-010 | APR 정책 배포 | 장비/Fleet policy topic으로 동적 정책 publish |
| F-011 | Dynamic Client Policy Control | client가 policy topic을 구독하여 QoS, 압축, 암호화, 무결성 정책을 runtime에 반영 |
| F-012 | Client Runtime Configuration Update | system metrics client 수집 주기, metric 목록, pause/resume 등 runtime option 변경 |
| F-013 | APR 모델 학습 자동화 | XGBoost 모델 artifact, 평가 지표, runtime export, runtime loading check 증적 생성 |
| F-014 | 보안 설정 검증 | 인증 모드에서 기본 secret, 기본 비밀번호, 기본 AES key 사용 차단 |
| F-015 | Docker 인증 실행 환경 | `docker-compose.cert.yml` 기반 서버와 MQTT broker 실행 |
| F-016 | 통합 증적 리포트 생성 | 필수 파일·문서·보안·Docker·APR 자동화 검증 결과 생성 |

## 4. 인증 제외 기능

| 제외 항목 | 처리 방침 |
|---|---|
| Voice streaming dashboard/API/process | code/process는 유지하되 GS 인증 평가 범위에서 제외 |
| 논문/연구용 실험 스크립트 | 제품 핵심 기능 평가 범위에서 제외 |
| 대용량 연구 산출물, 발표자료, 임시 DB, 로그 | 제출 패키지에서 제외 |
| DB 복구/논문 수정 등 보조 도구 | 운영자 유지보수 또는 연구 보조 도구로 분리 |

## 5. 제품 구성

| 구성 파일 | 설명 |
|---|---|
| `server.py` | Flask dashboard, REST API, MQTT subscriber, APR 정책 배포 메인 서버 |
| `Dockerfile` | 제품 서버 Docker image 생성 정의 |
| `docker-compose.cert.yml` | GS 인증 기준 Docker compose 실행 파일 |
| `.env.example` | 인증용 환경변수 템플릿 |
| `config.example.json` | 인증용 MQTT/APR/platform 설정 예시 |
| `requirements.txt` | Python dependency 목록 |
| `device/` | PC, Raspberry Pi, Ubuntu/Linux client code |
| `policy/` | APR 정책 추천 및 payload codec |
| `database/` | SQLite DB writer |
| `monitor/` | queue/topic 상태 모니터링 |
| `tools/check_certification_config.py` | 인증용 보안 설정 검증 |
| `tools/run_apr_model_automation.py` | APR 모델 자동화 증적 생성 |
| `tools/generate_gs_evidence_report.py` | GS 통합 증적 리포트 생성 |

## 6. 운영 환경

### 6.1 서버 환경

| 항목 | 권장 조건 |
|---|---|
| OS | Windows 11 + Docker Desktop 또는 Ubuntu Linux + Docker Engine |
| Runtime | Docker, Docker Compose v2 |
| Application port | TCP 4728 |
| MQTT broker port | TCP 1883 |
| Database | SQLite, Docker volume `/app/data` |
| Timezone | Asia/Seoul |

### 6.2 Client 환경

| Client | 설명 |
|---|---|
| PC client | Windows/Linux PC에서 테스트 telemetry publish |
| Raspberry Pi client | Raspberry Pi 센서 데이터 및 system metrics publish |
| Ubuntu/Linux client | Linux edge 환경에서 telemetry/system metrics publish |

## 7. 설치 및 실행 개요

1. `.env.example`을 `.env.cert`로 복사한다.
2. `.env.cert`의 모든 `CHANGE_ME` 값을 실제 인증 환경 값으로 변경한다.
3. 보안 설정을 검증한다.
4. Docker compose로 서버와 MQTT broker를 실행한다.
5. 브라우저에서 `http://localhost:4728`에 접속한다.
6. 장비를 등록하고 client package를 다운로드한다.
7. client를 실행하여 telemetry 수집과 APR 정책 적용을 확인한다.
8. 통합 증적 리포트를 생성한다.

## 8. 품질 특성 대응

| GS 품질 특성 | 제품 대응 |
|---|---|
| 기능 적합성 | 기능 ID 기준 인증 범위 고정, 기능별 테스트 케이스 작성 |
| 성능 효율성 | 비동기 DB writer, queue/backlog 모니터링, latency 통계 제공 |
| 호환성 | Docker 실행 환경, PC/Raspberry Pi/Ubuntu client 지원 |
| 사용성 | Dashboard, client package 자동 생성, 사용자 설명서 제공 |
| 신뢰성 | DB health check, system lock, MQTT startup error 표시, APR fallback 제공 |
| 보안성 | 인증 모드 보안 설정 검증, password hash 저장, AES-GCM envelope 지원 |
| 유지보수성 | Docker 패키지 구조, 기능 범위 문서, 통합 증적 자동화 제공 |

## 9. 제약사항 및 유의사항

- `.env.cert`에는 실제 secret이 포함되므로 Git에 커밋하지 않는다.
- `.env.example`은 템플릿이며 그대로 실행하면 보안 검증이 실패하는 것이 정상이다.
- APR 모델 자동화 기능은 제품 기능에 포함하되, 논문 분석 자료나 연구용 부가 산출물은 인증 제출 범위에서 제외한다.
- Voice streaming 관련 기능은 현재 code/process를 유지하지만 GS 인증 평가 기능에서는 제외한다.
- Docker compose 상세 출력에는 secret이 표시될 수 있으므로 제출 증적에는 마스킹된 결과 또는 `config --quiet` 검증 결과를 사용한다.