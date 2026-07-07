# GS 제출 전 최종 적합성 점검 가이드

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: GS 제출 전 문서·증적·패키지 일치성 최종 점검

## 1. 목적

이 문서는 GS 인증 제출 직전에 제품설명서, 사용자취급설명서, 테스트 케이스, 증적 리포트, 제출 패키지 manifest가 서로 일관된 범위와 산출물을 갖추었는지 자동 점검하는 절차를 정의한다.

## 2. 생성 도구

| 파일 | 용도 |
|---|---|
| `tools/generate_gs_readiness_review.py` | 문서, 도구, 증적, 제출 패키지 manifest를 종합 점검하고 JSON/Markdown 리포트 생성 |

## 3. 실행 전 준비

최종 적합성 점검 전에 다음 증적을 먼저 생성하는 것을 권장한다.

```powershell
python tools/generate_gs_e2e_preflight_report.py
python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export
python tools/build_gs_submission_package.py --clean --include-evidence --zip
```

## 4. 실행 방법

```powershell
python tools/generate_gs_readiness_review.py
```

## 5. 산출물

```text
runtime/gs_certification_evidence/
  gs_readiness_review.json
  gs_readiness_review.md
```

## 6. 점검 항목

| 구분 | 점검 내용 |
|---|---|
| 문서 존재 | 인증 범위, 제품설명서, 사용자취급설명서, 테스트 케이스, 보안, Docker, APR, E2E 관련 문서 존재 확인 |
| 도구 존재 | 보안 검증, APR 자동화, 통합 증적, E2E 사전 점검, 제출 패키지, readiness review 도구 존재 확인 |
| 핵심 용어 일관성 | APR 모델 학습 자동화, Dynamic Client Policy Control, Client Runtime Configuration Update, client OS, voice streaming 제외 방침 확인 |
| 테스트 케이스 | 통합 테스트 케이스 ID 개수와 중복 여부 확인 |
| 증적 파일 | 통합 증적, APR 자동화, E2E preflight report 존재와 상태 확인 |
| 제출 패키지 manifest | 필수 제출 파일 포함 여부와 `.env.cert`, DB, 로그, venv, cache 등 제외 대상 미포함 확인 |

## 7. 판정 기준

| 상태 | 의미 |
|---|---|
| `ok` | 문서, 도구, 증적, 제출 패키지 manifest의 정적 제출 준비 상태 충족 |
| `attention_required` | 제출 전 보완이 필요한 문서, 증적, 패키지 또는 일관성 항목 존재 |

## 8. 한계

본 점검은 제출 준비 상태를 정적으로 검토한다. 실제 Docker 기동, MQTT 송수신, 브라우저 접속, client 실행 증적은 별도 Live E2E 테스트 단계에서 생성해야 한다.