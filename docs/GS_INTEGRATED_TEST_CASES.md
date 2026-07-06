# GS 인증 통합 테스트 케이스

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 인증 범위에 포함된 기능의 기능·설치·보안·호환성 테스트 케이스 통합

## 1. 테스트 범위

본 테스트 케이스는 GS 인증 범위에 포함된 상용 운영 기능을 대상으로 한다. Voice streaming과 연구/논문용 실험 스크립트는 인증 범위에서 제외한다.

## 2. 통합 테스트 케이스

| TC ID | 분류 | 대상 기능 | 사전 조건 | 실행 절차 | 기대 결과 | 증적 |
|---|---|---|---|---|---|---|
| TC-INST-001 | 설치 | Docker compose 설정 검증 | `.env.cert` 준비 | `docker compose -f docker-compose.cert.yml --env-file .env.cert config --quiet` 실행 | compose 설정 검증 성공 | 명령 출력 |
| TC-INST-002 | 설치 | 서버 기동 | Docker 실행 가능 | `docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build` 실행 | dashboard container와 MQTT broker container 실행 | `docker compose ps` |
| TC-INST-003 | 설치 | Web 접속 | 서버 실행 중 | `http://localhost:4728` 접속 | 로그인 화면 표시 | 화면 캡처 |
| TC-SEC-001 | 보안 | 인증 모드 활성화 | `.env.cert` 준비 | `python tools/check_certification_config.py --env-file .env.cert` 실행 | `CERTIFICATION_MODE` OK | 명령 출력 |
| TC-SEC-002 | 보안 | 기본 secret 차단 | placeholder secret 사용 | 검증 스크립트 실행 | `FLASK_SECRET_KEY` FAIL | 명령 출력 |
| TC-SEC-003 | 보안 | 기본 계정 비밀번호 차단 | `admin1234` 또는 `user1234` 사용 | 검증 스크립트 실행 | password 항목 FAIL | 명령 출력 |
| TC-SEC-004 | 보안 | 기본 APR AES key 차단 | `010101...` key 사용 | 검증 스크립트 실행 | `APR_AES_KEY_HEX` FAIL | 명령 출력 |
| TC-USER-001 | 사용자 | 로그인 | 초기 관리자 계정 생성 | 관리자 email/password 입력 | Dashboard 진입 | 화면 캡처 |
| TC-USER-002 | 사용자 | 권한 제한 | 일반 사용자 로그인 | 관리자 API 또는 관리자 화면 접근 | 접근 제한 또는 forbidden 반환 | 화면/API 응답 |
| TC-DEV-001 | 장비 | Fleet 등록 | 관리자 로그인 | Fleet 생성 API 또는 화면 실행 | Fleet 목록에 신규 항목 표시 | 화면/API 응답 |
| TC-DEV-002 | 장비 | Device 등록 | Fleet 존재 | Device ID, OS, type 입력 후 등록 | Device 목록과 topic 경로 생성 | 화면/API 응답 |
| TC-DEV-003 | Client | PC client package 생성 | Device 등록 | `device_os=pc`로 client package 다운로드 | PC client 실행 파일과 config 포함 zip 생성 | zip 파일 목록 |
| TC-DEV-004 | Client | Raspberry Pi client package 생성 | Device 등록 | `device_os=raspberry_pi`로 client package 다운로드 | sensor publisher와 system metrics config 포함 | zip 파일 목록 |
| TC-DEV-005 | Client | Ubuntu/Linux client package 생성 | Device 등록 | `device_os=ubuntu` 또는 Linux 대상 package 다운로드 | Linux 실행 스크립트와 config 포함 | zip 파일 목록 |
| TC-MQTT-001 | 수집 | Telemetry publish/subscribe | MQTT broker와 server 실행 | client 실행 또는 MQTT publish | 서버 DB에 telemetry 저장 | DB/API 조회 |
| TC-MQTT-002 | 수집 | APR envelope decode | AES key 설정 완료 | 압축/암호화/무결성 payload publish | payload decode 및 저장 성공 | DB/API 조회 |
| TC-MON-001 | 모니터링 | System status API | 서버 실행 | `/api/system/status` 호출 | lock, DB writer 상태 반환 | API 응답 |
| TC-MON-002 | 모니터링 | Broker status API | MQTT broker 실행 | `/api/broker/status` 호출 | broker 연결 또는 startup 상태 반환 | API 응답 |
| TC-MON-003 | 모니터링 | Queue/backlog monitoring | telemetry 수집 중 | queue dashboard 또는 API 확인 | queue depth/topic rate 표시 | 화면/API 응답 |
| TC-APR-001 | APR | 정책 추천 | telemetry/metric 존재 | APR recommendation API 또는 dashboard 실행 | QoS/압축/암호화/무결성 정책 추천 | API 응답 |
| TC-APR-002 | APR | 정책 배포 | Device 또는 Fleet 존재 | policy apply 실행 | MQTT policy topic publish log 생성 | policy log/API 응답 |
| TC-APR-003 | APR | Dynamic Client Policy Control | client policy topic 구독 중 | 서버에서 정책 변경 publish | client runtime policy 변경 반영 | client log |
| TC-APR-004 | APR | Client Runtime Configuration Update | system metrics client 실행 중 | interval/metrics/pause/resume 정책 publish | client runtime option 변경 반영 | client log |
| TC-ML-001 | APR ML | Runtime artifact export | model artifact 존재 | `python tools/export_apr_xgb_runtime.py` 실행 | runtime model/preprocessor/meta 생성 | 명령 출력 |
| TC-ML-002 | APR ML | Runtime loading check | dependency 설치 완료 | `python tools/check_apr_ml_runtime.py` 실행 | model loading 또는 fallback 상태 확인 | JSON 출력 |
| TC-ML-003 | APR ML | 모델 자동화 증적 생성 | APR 파일 존재 | `python tools/run_apr_model_automation.py --skip-export` 실행 | `overall_status=ok` report 생성 | JSON report |
| TC-EVID-001 | 증적 | 통합 증적 리포트 생성 | `.env.cert` 준비 | `python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export` 실행 | `status=ok`와 JSON/Markdown report 생성 | report 파일 |
| TC-EVID-002 | 증적 | 필수 문서 존재 확인 | 제출 문서 작성 완료 | 통합 리포트의 Required Documents 확인 | 모든 문서 Exists=True | Markdown report |
| TC-ERR-001 | 오류 처리 | MQTT 연결 실패 허용 | broker 중지 | 서버 실행 | dashboard는 실행되고 startup error 표시 | 서버 로그/API 응답 |
| TC-ERR-002 | 오류 처리 | 보안 설정 오류 메시지 | 인증 모드 + 기본값 사용 | 서버 실행 | 시작 실패 및 보완 항목 메시지 표시 | 서버 로그 |
| TC-ERR-003 | 오류 처리 | DB health 확인 | DB 경로 설정 | 서버 시작 | DB health/schema 결과 출력 | 서버 로그 |

## 3. 테스트 증적 보관 기준

| 증적 유형 | 보관 위치 예시 | 비고 |
|---|---|---|
| 통합 검증 JSON | `runtime/gs_certification_evidence/gs_evidence_report.json` | secret 원문 포함 금지 |
| 통합 검증 Markdown | `runtime/gs_certification_evidence/gs_evidence_report.md` | 제출 전 검토용 |
| APR 자동화 JSON | `runtime/gs_certification_evidence/apr_model_automation_report.json` | 모델 파일/metric 상태 포함 |
| Docker 실행 로그 | 별도 제출 증적 폴더 | secret 마스킹 필요 |
| 화면 캡처 | 별도 제출 증적 폴더 | 로그인 이후 화면 기준 |
| client log | 별도 제출 증적 폴더 | device id, policy 변경 확인 |

## 4. 합격 기준

- 인증 범위 기능의 핵심 테스트는 모두 PASS여야 한다.
- 보안 negative test는 기본값 사용 시 FAIL이 발생해야 정상이다.
- `.env.cert` 기준 통합 증적 리포트는 `status=ok`가 되어야 한다.
- voice streaming 관련 테스트는 GS 인증 통합 테스트 케이스에 포함하지 않는다.