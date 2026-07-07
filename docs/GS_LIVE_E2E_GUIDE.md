# GS Docker Live E2E 증적 생성 가이드

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: 실제 Docker 기동 기반 Live E2E 증적 생성

## 1. 목적

이 문서는 실제 Docker compose 환경에서 서버와 MQTT broker를 기동하고, Web/API 응답을 확인하여 GS 제출용 Live E2E 증적을 생성하는 절차를 정의한다.

## 2. 생성 도구

| 파일 | 용도 |
|---|---|
| `tools/generate_gs_live_e2e_report.py` | Docker compose up/down, Web/API 확인, JSON/Markdown Live E2E report 생성 |

## 3. 기본 실행

임시 인증용 env를 자동 생성하여 Live E2E를 실행한다. 생성된 env는 `runtime/` 아래에 위치하며 Git에 포함하지 않는다.

```powershell
python tools/generate_gs_live_e2e_report.py
```

실제 `.env.cert`를 사용하려면 다음과 같이 실행한다.

```powershell
python tools/generate_gs_live_e2e_report.py --env-file .env.cert
```

컨테이너를 종료하지 않고 유지하려면 다음 옵션을 사용한다.

```powershell
python tools/generate_gs_live_e2e_report.py --keep-running
```

## 4. 산출물

```text
runtime/gs_certification_evidence/
  gs_live_e2e_report.json
  gs_live_e2e_report.md
```

## 5. 확인 항목

| 구분 | 확인 내용 |
|---|---|
| 보안 설정 | `tools/check_certification_config.py` 통과 여부 |
| Compose config | `docker compose config --quiet` 통과 여부 |
| Docker 기동 | `docker compose up -d --build` 성공 여부 |
| Web 응답 | `http://127.0.0.1:4728/` 응답 여부 |
| System API | `/api/system/status` 응답 여부 |
| Broker API | `/api/broker/status` 응답 여부 |
| DB API | `/api/db/status` 응답 여부 |
| 종료 | 기본 실행 시 `docker compose down` 성공 여부 |

## 6. 보안 주의 사항

Live E2E 도구는 secret 원문을 report에 기록하지 않고 설정 여부와 길이만 기록한다. `runtime/gs_live_e2e.env` 또는 실제 `.env.cert`는 Git과 공개 제출본에 포함하지 않는다.

## 7. 문제 발생 시

| 상황 | 조치 |
|---|---|
| Docker API permission denied | Docker Desktop 실행 상태와 권한 확인 |
| Docker daemon 미기동 | Docker Desktop 또는 Docker service 시작 |
| compose up 실패 | build log와 `docker compose ps` 확인 |
| Web 응답 실패 | dashboard container log 확인 |
| API 응답 실패 | Flask route, 인증 정책, server log 확인 |