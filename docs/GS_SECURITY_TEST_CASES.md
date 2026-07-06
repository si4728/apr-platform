# GS Security Configuration Test Cases

작성일: 2026-07-06  
대상 단계: 보안·설치·오류 처리 안정화

| TC ID | 분류 | 테스트 항목 | 사전 조건 | 실행 절차 | 기대 결과 | 증적 |
|---|---|---|---|---|---|---|
| TC-SEC-001 | Config | 인증 모드 활성화 확인 | `.env.cert` 준비 | `python tools/check_certification_config.py --env-file .env.cert` 실행 | `CERTIFICATION_MODE` 항목 OK | 명령 출력 |
| TC-SEC-002 | Secret | Flask secret 기본값 차단 | `.env.cert`의 `FLASK_SECRET_KEY`를 placeholder로 유지 | 검증 스크립트 실행 | `FLASK_SECRET_KEY` 항목 FAIL | 명령 출력 |
| TC-SEC-003 | Account | 관리자 기본 비밀번호 차단 | `IOT_ADMIN_PASSWORD=admin1234` 설정 | 검증 스크립트 실행 | `IOT_ADMIN_PASSWORD` 항목 FAIL | 명령 출력 |
| TC-SEC-004 | Account | 일반 사용자 기본 비밀번호 차단 | `IOT_USER_PASSWORD=user1234` 설정 | 검증 스크립트 실행 | `IOT_USER_PASSWORD` 항목 FAIL | 명령 출력 |
| TC-SEC-005 | APR Key | APR 기본 AES key 차단 | `APR_AES_KEY_HEX=01010101010101010101010101010101` 설정 | 검증 스크립트 실행 | `APR_AES_KEY_HEX` 항목 FAIL | 명령 출력 |
| TC-SEC-006 | APR Key | APR AES key 형식 확인 | 32/48/64자리 hex key 설정 | 검증 스크립트 실행 | `APR_AES_KEY_HEX` 항목 OK | 명령 출력 |
| TC-SEC-007 | Compose | 인증용 compose 필수 환경변수 확인 | `.env.cert` 준비 | `docker compose -f docker-compose.cert.yml --env-file .env.cert config` 실행 | compose 설정 출력 성공 | compose 출력 |
| TC-SEC-008 | Client Package | client package key 반영 확인 | 인증용 서버 실행, 장비 등록 | client package 다운로드 후 `client.config` 확인 | `apr_aes_key_hex`가 `.env.cert` 값과 일치 | package 파일 캡처 |