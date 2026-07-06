# GS 인증 제출 패키지 자동 구성 가이드

작성일: 2026-07-06  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
대상 단계: GS 제출 패키지 자동 구성

## 1. 목적

이 문서는 GS 인증 제출용 제품 폴더를 자동으로 구성하는 절차를 정의한다. 자동 구성 도구는 제품 실행 파일, 인증 문서, 선택된 증적 파일을 지정된 제출 폴더로 복사하고, DB·로그·secret·venv·cache 등 제출하면 안 되는 파일을 제외한다.

## 2. 생성 도구

| 파일 | 용도 |
|---|---|
| `tools/build_gs_submission_package.py` | GS 제출 패키지 폴더 및 manifest 생성 |
| `tools/generate_gs_evidence_report.py` | 제출 전 통합 검증 리포트 생성 |

## 3. 기본 실행

제출 패키지 폴더를 새로 생성한다.

```powershell
python tools/build_gs_submission_package.py --clean
```

통합 증적 리포트까지 포함하려면 먼저 리포트를 생성한 뒤 `--include-evidence`를 사용한다.

```powershell
python tools/generate_gs_evidence_report.py --env-file .env.cert --skip-apr-export
python tools/build_gs_submission_package.py --clean --include-evidence
```

zip 파일까지 생성하려면 다음과 같이 실행한다.

```powershell
python tools/build_gs_submission_package.py --clean --include-evidence --zip
```

## 4. 산출물 위치

기본 산출물 위치는 다음과 같다.

```text
runtime/gs_submission_package/
  apr-edgeinsight-gs-submission/
    product/
    documents/
    evidence/
    PACKAGE_MANIFEST.json
  apr-edgeinsight-gs-submission.zip
```

## 5. 포함 파일

| 구분 | 포함 예시 |
|---|---|
| 제품 실행 파일 | `Dockerfile`, `docker-compose.cert.yml`, `server.py`, `requirements.txt` |
| 설정 템플릿 | `config.example.json`, `.env.example`, `mosquitto/config/mosquitto.conf` |
| 제품 코드 | `device/`, `policy/`, `database/`, `monitor/`, `templates/`, `static/`, `tools/` |
| 제출 문서 | GS 범위 문서, 제품설명서, 사용자취급설명서, 통합 테스트 케이스, 체크리스트 |
| 증적 파일 | `gs_evidence_report.*`, `apr_model_automation_report.json` |

## 6. 제외 파일

| 제외 대상 | 이유 |
|---|---|
| `.env.cert` | 실제 secret 포함 가능 |
| `*.db`, `*.db-wal`, `*.db-shm` | 운영/개발 DB 및 개인정보 가능성 |
| `*.log`, `*.err.log`, `*.out.log` | 개발/운영 로그 |
| `Lib/`, `Scripts/`, `pyvenv.cfg` | 로컬 Python venv |
| `__pycache__/` | Python cache |
| `runtime/` 전체 | 실행 중 생성물. 필요한 증적만 `evidence/`에 선별 복사 |
| `*.bak`, `*.malformed*`, `*.recovered*` | DB 백업/복구 산출물 |

## 7. Manifest 확인

`PACKAGE_MANIFEST.json`에는 패키지에 포함된 파일의 경로, 크기, SHA-256 hash가 기록된다. 제출 전 다음 항목을 확인한다.

- `.env.cert`가 포함되지 않았는가
- 운영 DB와 로그가 포함되지 않았는가
- `product/`, `documents/`, `evidence/` 폴더가 의도대로 구성되었는가
- manifest의 `scope_note`에 voice streaming 인증 제외 방침이 명시되어 있는가

## 8. 주의 사항

자동 구성 도구는 제출 폴더를 만드는 도구이며, 실제 인증 환경 secret을 생성하지 않는다. 시험기관 제출 전에는 `.env.example`을 기준으로 현장용 `.env.cert`를 별도로 작성하고, secret 원문은 제출본에 포함하지 않는다.