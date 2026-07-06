# GS 인증 제출 패키지 체크리스트

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 인증 신청 전 제출 파일, 제외 파일, 사전 검증 항목 확인

## 1. 제출 패키지 기본 원칙

- 제출 패키지는 Docker 기준 실행이 가능한 최소 상용 제품 구성으로 만든다.
- 기존 기능과 code/process는 삭제하지 않지만, GS 인증 범위와 제출 문서는 상용 운영 기능 중심으로 구성한다.
- Voice streaming 관련 code/process는 유지하되 인증 범위와 테스트 케이스에서는 제외한다.
- `.env.cert`, 운영 DB, 로그, secret 원문은 Git 또는 공개 제출본에 포함하지 않는다.

## 2. 필수 실행 파일 체크리스트

| 확인 | 경로 | 설명 |
|---|---|---|
| [ ] | `Dockerfile` | 제품 서버 Docker image 생성 |
| [ ] | `docker-compose.cert.yml` | 인증용 Docker compose |
| [ ] | `requirements.txt` | Python dependency |
| [ ] | `server.py` | 메인 서버 |
| [ ] | `config.example.json` | 인증용 설정 예시 |
| [ ] | `.env.example` | 인증용 환경변수 템플릿 |
| [ ] | `mosquitto/config/mosquitto.conf` | 인증용 MQTT broker 설정 |
| [ ] | `device/` | PC/Raspberry Pi/Ubuntu client code |
| [ ] | `policy/` | APR policy, codec |
| [ ] | `database/` | DB writer |
| [ ] | `monitor/` | queue/topic monitoring |
| [ ] | `tools/check_certification_config.py` | 보안 설정 검증 |
| [ ] | `tools/run_apr_model_automation.py` | APR 모델 자동화 증적 |
| [ ] | `tools/generate_gs_evidence_report.py` | 통합 증적 리포트 생성 |
| [ ] | `tools/build_gs_submission_package.py` | GS 제출 패키지 자동 구성 |

## 3. 필수 문서 체크리스트

| 확인 | 문서 | 설명 |
|---|---|---|
| [ ] | `docs/GS_CERTIFICATION_SCOPE_V1.md` | 인증 범위 정의 |
| [ ] | `docs/GS_PRODUCT_DESCRIPTION_KO.md` | 제품설명서 초안 |
| [ ] | `docs/USER_MANUAL_KO.md` | 사용자취급설명서 |
| [ ] | `docs/GS_DOCKER_INSTALLATION_GUIDE.md` | Docker 설치/운영 가이드 |
| [ ] | `docs/GS_RELEASE_PACKAGE_STRUCTURE.md` | 제출 패키지 구조 |
| [ ] | `docs/GS_SECURITY_CONFIGURATION_GUIDE.md` | 보안 설정 가이드 |
| [ ] | `docs/GS_SECURITY_TEST_CASES.md` | 보안 테스트 케이스 |
| [ ] | `docs/GS_APR_MODEL_TRAINING_AUTOMATION.md` | APR 모델 자동화 설명 |
| [ ] | `docs/GS_APR_MODEL_TEST_CASES.md` | APR 모델 자동화 테스트 케이스 |
| [ ] | `docs/GS_INTEGRATED_TEST_CASES.md` | 통합 테스트 케이스 |
| [ ] | `docs/GS_INTEGRATED_EVIDENCE_REPORT_GUIDE.md` | 통합 증적 리포트 가이드 |
| [ ] | `docs/GS_SUBMISSION_PACKAGE_CHECKLIST.md` | 제출 패키지 체크리스트 |
| [ ] | `docs/GS_SUBMISSION_PACKAGE_BUILD_GUIDE.md` | 제출 패키지 자동 구성 가이드 |

## 4. 제출 전 실행 검증 체크리스트

| 확인 | 검증 항목 | 명령 |
|---|---|---|
| [ ] | 보안 설정 검증 | `python tools/check_certification_config.py --env-file .env.cert` |
| [ ] | Docker compose 설정 검증 | `docker compose -f docker-compose.cert.yml --env-file .env.cert config --quiet` |
| [ ] | Python 문법 검증 | `python -m py_compile server.py tools/check_certification_config.py tools/run_apr_model_automation.py tools/generate_gs_evidence_report.py` |
| [ ] | APR 모델 자동화 검증 | `python tools/run_apr_model_automation.py --skip-export` |
| [ ] | 통합 증적 리포트 생성 | `python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export` |
| [ ] | 제출 패키지 자동 구성 | `python tools/build_gs_submission_package.py --clean --include-evidence --zip` |
| [ ] | Docker 서버 실행 | `docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build` |
| [ ] | Dashboard 접속 | `http://localhost:4728` |
| [ ] | Client package 다운로드 | 장비 등록 후 PC/Raspberry Pi/Ubuntu package 생성 |

## 5. 제출 제외 파일 체크리스트

| 제외 대상 | 제외 사유 |
|---|---|
| `.env.cert` | 실제 secret 포함 |
| `iot_data.db`, `*.db-wal`, `*.db-shm` | 운영/개발 DB 또는 개인정보 가능성 |
| `*.log`, `*.err.log`, `*.out.log` | 개발/운영 로그 |
| `runtime/` | 실행 중 생성 증적. 제출용으로 별도 선별 필요 |
| `Lib/`, `Scripts/`, `pyvenv.cfg` | 로컬 Python venv |
| `__pycache__/` | Python cache |
| `*.bak`, `*.malformed*`, `*.recovered*` | DB 복구/백업 산출물 |
| 논문/발표/영업 자료 | 제품 실행 패키지가 아님 |
| voice streaming 시험 증적 | 현재 GS 인증 범위 제외 |

## 6. 최종 제출 전 확인 사항

| 확인 | 항목 |
|---|---|
| [ ] | 제품설명서, 사용자취급설명서, 테스트 케이스의 기능 범위가 동일하다 |
| [ ] | Voice streaming은 “기존 기능 유지, 인증 범위 제외”로 일관되게 표시되어 있다 |
| [ ] | APR 모델 학습 자동화는 인증 포함 기능으로 표시되어 있다 |
| [ ] | Dynamic Client Policy Control과 Client Runtime Configuration Update가 인증 포함 기능으로 표시되어 있다 |
| [ ] | PC, Raspberry Pi, Ubuntu/Linux client code와 사용 절차가 문서에 포함되어 있다 |
| [ ] | `.env.example`에는 실제 secret이 없다 |
| [ ] | 통합 증적 리포트가 `status=ok`이다 |
| [ ] | 제출본에는 운영 DB, 로그, secret, 임시 파일이 포함되어 있지 않다 |

## 7. 권장 제출 폴더 구조

```text
apr-edgeinsight-gs-submission/
  product/
    Dockerfile
    docker-compose.cert.yml
    config.example.json
    .env.example
    requirements.txt
    server.py
    device/
    policy/
    database/
    monitor/
    tools/
    mosquitto/config/mosquitto.conf
  documents/
    GS_CERTIFICATION_SCOPE_V1.md
    GS_PRODUCT_DESCRIPTION_KO.md
    USER_MANUAL_KO.md
    GS_INTEGRATED_TEST_CASES.md
    GS_SUBMISSION_PACKAGE_CHECKLIST.md
    GS_DOCKER_INSTALLATION_GUIDE.md
    GS_SECURITY_CONFIGURATION_GUIDE.md
    GS_APR_MODEL_TRAINING_AUTOMATION.md
  evidence/
    gs_evidence_report.md
    gs_evidence_report.json
    apr_model_automation_report.json
```