# GS E2E 사전 점검 가이드

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: 실제 Docker 실행 전 E2E 준비도 검증

## 1. 목적

이 문서는 실제 Docker 컨테이너를 기동하지 않고 GS 인증 E2E 테스트 준비 상태를 사전에 점검하는 절차를 정의한다. 본 단계는 사용자가 선택한 A안에 해당하며, 네트워크 연결이나 컨테이너 실행 없이 코드, route, client package 구성, 설정 템플릿, 필수 문서 존재 여부를 검증한다.

## 2. 생성 도구

| 파일 | 용도 |
|---|---|
| `tools/generate_gs_e2e_preflight_report.py` | E2E 사전 점검 JSON/Markdown 리포트 생성 |

## 3. 실행 방법

```powershell
python tools/generate_gs_e2e_preflight_report.py
```

## 4. 산출물

```text
runtime/gs_certification_evidence/
  gs_e2e_preflight_report.json
  gs_e2e_preflight_report.md
```

## 5. 점검 항목

| 구분 | 점검 내용 |
|---|---|
| Route coverage | 통합 테스트 케이스에 필요한 Flask route 존재 확인 |
| Client package readiness | PC, Raspberry Pi, Ubuntu/Linux client package 구성 파일 존재 확인 |
| Config template checks | `.env.example`, `docker-compose.cert.yml`, `config.example.json`의 인증용 설정 조건 확인 |
| Required files | 서버, Docker, 보안/증적/패키징 도구 존재 확인 |
| Required documents | 제품설명서, 통합 테스트 케이스, 제출 체크리스트, 패키지 가이드 존재 확인 |

## 6. 판정 기준

| 상태 | 의미 |
|---|---|
| `ok` | 실제 Docker E2E 실행 전 필요한 정적 준비 조건 충족 |
| `attention_required` | route, client 파일, 설정 템플릿, 필수 문서 중 보완 필요 항목 존재 |

## 7. 한계

이 리포트는 실제 서버 기동, Docker health check, MQTT publish/subscribe, 브라우저 접속을 수행하지 않는다. 실제 실행 증적은 후속 단계에서 `.env.cert`를 준비한 뒤 Docker 기반 E2E 테스트로 생성한다.