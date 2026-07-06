# GS Certification Security Configuration Guide

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: 보안·설치·오류 처리 안정화

## 1. 목적

이 문서는 GS 인증 실행 환경에서 기본 계정, 기본 secret, 기본 APR AES key 사용을 방지하기 위한 설정 기준과 검증 절차를 정의한다. 기존 실험 기능과 voice stream 관련 code/process는 유지하되, 인증용 Docker 실행 환경에서는 운영 가능한 보안 설정을 적용한다.

## 2. 적용 범위

| 항목 | 인증 적용 | 설명 |
|---|---:|---|
| `CERTIFICATION_MODE` | 포함 | 인증 실행 환경을 명시하는 환경변수 |
| `FLASK_SECRET_KEY` | 포함 | Flask session 보호용 secret. 기본값 또는 placeholder 사용 금지 |
| `IOT_ADMIN_PASSWORD` | 포함 | 초기 관리자 계정 비밀번호. `admin1234` 사용 금지 |
| `IOT_USER_PASSWORD` | 포함 | 초기 일반 사용자 계정 비밀번호. `user1234` 사용 금지 |
| `APR_AES_KEY_HEX` | 포함 | APR AES-GCM envelope/client package 공통 key. 실험용 `0101...` key 사용 금지 |
| Voice stream process | 인증 제외 | 기존 code/process는 유지하되 GS 인증 범위에는 포함하지 않음 |

## 3. 인증용 설정 절차

1. `.env.example`을 `.env.cert`로 복사한다.
2. `.env.cert`의 모든 `CHANGE_ME` 값을 실제 운영 값으로 교체한다.
3. `APR_AES_KEY_HEX`는 32, 48, 64자리 hex 문자열 중 하나로 설정한다.
4. 설정 검증 명령을 실행한다.
5. 검증 통과 후 Docker compose를 실행한다.

예시:

```powershell
copy .env.example .env.cert
python tools/check_certification_config.py --env-file .env.cert
```

Docker 실행:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

## 4. 코드 반영 사항

| 파일 | 반영 내용 |
|---|---|
| `server.py` | `CERTIFICATION_MODE=true`일 때 기본 secret/password/AES key 차단 |
| `server.py` | client package 생성 시 `APR_AES_KEY_HEX` 환경변수 값을 `client.config`, `system_metrics.config`에 반영 |
| `docker-compose.cert.yml` | 인증용 필수 보안 환경변수에 compose 기본값 제거 |
| `.env.example` | 기본 비밀번호/key 대신 교체 필요 placeholder 제공 |
| `tools/check_certification_config.py` | 인증 실행 전 보안 설정 검증 증적 생성 |

## 5. 오류 처리 기준

인증 모드에서 필수 보안 설정이 미흡하면 서버는 시작 단계에서 `RuntimeError`를 발생시키고, 어떤 설정 항목을 보완해야 하는지 메시지로 표시한다. 비밀값 자체는 로그에 출력하지 않는다.

대표 오류 예:

```text
Certification runtime configuration is invalid: FLASK_SECRET_KEY must be set to a non-default value with at least 24 characters.
```

## 6. 검증 증적

인증 제출 시 다음 자료를 증적으로 보관한다.

| 증적 | 생성 방법 |
|---|---|
| 보안 설정 검증 출력 | `python tools/check_certification_config.py --env-file .env.cert --json` |
| Docker compose 설정 확인 | `docker compose -f docker-compose.cert.yml --env-file .env.cert config` |
| 서버 시작 로그 | 인증용 Docker container log |
| client package 설정 확인 | 다운로드된 `client.config`, `system_metrics.config`에서 `apr_aes_key_hex`가 환경변수 값과 일치하는지 확인 |

## 7. 주의 사항

`.env.cert`에는 실제 secret이 포함되므로 Git에 커밋하지 않는다. 제출용 문서에는 secret 원문을 표시하지 않고, 검증 결과와 설정 항목 충족 여부만 포함한다.