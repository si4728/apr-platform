# GS Certification Integrated Evidence Report Guide

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: 문서·테스트 증적 통합 자동화

## 1. 목적

이 문서는 GS 인증 제출 준비 과정에서 보안 설정, Docker 실행 조건, APR 모델 학습 자동화, 필수 문서/파일 존재 여부를 한 번에 검증하고 증적 리포트를 생성하는 절차를 정의한다.

통합 리포트는 시험기관 제출 전 내부 점검 자료로 사용하며, 실제 secret 값은 리포트에 원문으로 기록하지 않는다.

## 2. 생성 도구

| 파일 | 용도 |
|---|---|
| `tools/generate_gs_evidence_report.py` | GS 인증 통합 증적 JSON/Markdown 생성 |
| `tools/check_certification_config.py` | 인증용 환경변수 보안 설정 검증 |
| `tools/run_apr_model_automation.py` | APR 모델 자동화 증적 생성 |

## 3. 사전 준비

1. `.env.example`을 `.env.cert`로 복사한다.
2. `.env.cert`의 `CHANGE_ME` 값을 실제 인증 환경 값으로 변경한다.
3. Docker Desktop 또는 Docker Engine이 설치되어 있어야 한다.
4. Python dependency는 `requirements.txt` 기준으로 설치되어 있어야 한다.

예시:

```powershell
copy .env.example .env.cert
python tools/check_certification_config.py --env-file .env.cert
```

## 4. 통합 리포트 생성

기본 실행:

```powershell
python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export
```

APR runtime artifact export까지 포함하려면 `--skip-apr-export`를 제거한다.

```powershell
python tools/generate_gs_evidence_report.py --env-file .env.cert
```

## 5. 산출물

기본 산출물 위치:

```text
runtime/gs_certification_evidence/
  gs_evidence_report.json
  gs_evidence_report.md
  apr_model_automation_report.json
```

| 산출물 | 설명 |
|---|---|
| `gs_evidence_report.json` | 자동 검증 전체 결과 원본 |
| `gs_evidence_report.md` | 사람이 읽는 제출/검토용 요약 리포트 |
| `apr_model_automation_report.json` | APR 모델 파일, metric, runtime check 상세 증적 |

## 6. 판정 기준

| 상태 | 의미 |
|---|---|
| `ok` | 필수 파일/문서 존재, 보안 설정, Docker compose config, APR 자동화 검증 통과 |
| `attention_required` | 필수 파일/문서는 있으나 일부 실행 전 검증 보완 필요 |
| `failed` | 필수 파일 또는 문서 누락, 또는 핵심 검증 실패 |

`.env.example`은 템플릿이므로 통합 리포트 실행 시 보안 검증이 실패하는 것이 정상이다. 실제 인증 증적은 `.env.cert`처럼 기본값을 교체한 파일로 생성한다.

## 7. 리포트에 포함되는 검증 항목

| 구분 | 검증 내용 |
|---|---|
| Python compile | `server.py`, 보안 검증 도구, APR 자동화 도구 문법 확인 |
| Security configuration | 인증 모드, secret, 초기 계정 비밀번호, APR AES key 기본값 차단 확인 |
| Docker compose config | `docker-compose.cert.yml`과 env 파일 조합의 compose 설정 유효성 확인 |
| APR model automation | APR runtime model artifact, metric CSV, runtime loading/recommendation check 확인 |
| Required files | 서버, Docker, 설정, 검증 도구 파일 존재 확인 |
| Required documents | 인증 범위, 설치, 보안, APR, 사용자 설명서 문서 존재 확인 |

## 8. 보안 주의 사항

`.env.cert`에는 실제 secret이 포함되므로 Git에 커밋하지 않는다. 통합 리포트는 secret 원문 대신 설정 여부와 길이만 기록한다. Docker compose 상세 출력은 secret이 표시될 수 있으므로 제출 증적으로 사용할 때는 `config --quiet` 결과 또는 마스킹한 출력만 사용한다.