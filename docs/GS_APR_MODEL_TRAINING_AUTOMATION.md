# GS Certification APR Model Training Automation

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0  
기능 ID: F-021 APR 모델 학습 자동화

## 1. 목적

APR 모델 학습 자동화는 수집된 통신 성능 데이터를 기반으로 XGBoost 모델을 학습/검증하고, 운영 서버가 사용할 수 있는 runtime model artifact로 변환하는 제품 기능이다.

본 기능은 GS 인증 범위에 포함한다.

## 2. 기능 범위

| 단계 | 인증 포함 여부 | 설명 |
|---|---:|---|
| 성능 데이터 수집 | 포함 | compression, encryption, integrity 조합별 통신 metric 수집 |
| 학습/검증 지표 관리 | 포함 | R2, MAE, RMSE, MAPE 및 cross validation 지표 관리 |
| runtime export | 포함 | sklearn pipeline을 preprocessor와 XGBoost native model로 분리 저장 |
| runtime loading check | 포함 | 서버 APR engine에서 모델 로딩 및 추천 결과 확인 |
| fallback 확인 | 포함 | 모델 로딩 실패 시 rule-based engine 사용 |

## 3. 관련 파일

| 파일 | 역할 |
|---|---|
| `apr/cccmp_20.py` | MQTT publish 측 성능 데이터 수집 |
| `apr/cccms_20.py` | MQTT subscribe 측 성능 데이터 수집 |
| `apr/cccm_sinario.py` | 통신 정책 조합 정의 |
| `apr/ccms.ini` | 데이터 수집 MQTT/log 설정 |
| `apr/xgb_model.joblib` | legacy sklearn pipeline model |
| `apr/xgb_model_meta.json` | 모델 feature, metric, candidate metadata |
| `apr/xgb_metrics.csv` | 모델 평가 지표 |
| `apr/xgb_cv_metrics.csv` | cross validation 지표 |
| `apr/xgb_preprocessor.joblib` | runtime preprocessor |
| `apr/xgb_model.json` | XGBoost native runtime model |
| `apr/xgb_runtime_meta.json` | runtime artifact metadata |
| `tools/export_apr_xgb_runtime.py` | runtime artifact export |
| `tools/check_apr_ml_runtime.py` | runtime model loading/recommendation check |
| `tools/run_apr_model_automation.py` | GS 인증용 자동화 증적 생성 helper |

## 4. 현재 모델 기준 지표

현재 포함된 모델 지표는 다음과 같다.

| 지표 | 값 |
|---|---:|
| R2 | 0.9180693792929736 |
| MAE | 0.1359913492841535 |
| RMSE | 0.32141898701584976 |
| MAPE | 16.85385821202389 |
| Cross validation | 5-fold |
| CV R2 mean | 0.9194361517906486 |

## 5. 표준 인증 실행 절차

인증 시험에서 모델 자동화 증적을 생성할 때는 다음 명령을 사용한다.

```powershell
python tools/run_apr_model_automation.py
```

이미 export된 runtime artifact만 검증하려면 다음 명령을 사용한다.

```powershell
python tools/run_apr_model_automation.py --skip-export
```

인증 시험에서는 `requirements.txt`가 설치된 프로젝트 venv 또는 Docker container 내부에서 실행한다. bundled Python처럼 ML dependency가 없는 환경에서는 `joblib`, `sklearn`, `xgboost` 누락으로 runtime check가 실패할 수 있다.

실제 검증 결과, 프로젝트 venv의 `Scripts\python.exe`로 `--skip-export` 점검을 실행했을 때 `overall_status=ok` 보고서가 생성되었다.

실행 결과는 기본적으로 다음 파일에 저장된다.

```text
runtime/apr_model_automation_report.json
```

## 6. Runtime Export 절차

개별 export 명령:

```powershell
python tools/export_apr_xgb_runtime.py
```

생성 또는 갱신되는 파일:

```text
apr/xgb_preprocessor.joblib
apr/xgb_model.json
apr/xgb_runtime_meta.json
```

## 7. Runtime Check 절차

개별 점검 명령:

```powershell
python tools/check_apr_ml_runtime.py
```

확인 항목:

| 항목 | 기대 결과 |
|---|---|
| `joblib` | available |
| `pandas` | available |
| `sklearn` | available |
| `xgboost` | available |
| runtime model file | exists |
| APR engine recommendation | policy JSON 반환 |

## 8. Docker 인증 환경에서의 실행

Docker 인증 환경에서는 dashboard container 내부에서 다음과 같이 실행한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert exec iot-dashboard python tools/run_apr_model_automation.py
```

보고서 확인:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert exec iot-dashboard cat runtime/apr_model_automation_report.json
```

## 9. 의존성 및 주의사항

`tools/export_apr_xgb_runtime.py`와 `tools/check_apr_ml_runtime.py`는 현재 `requirements.txt` 범위의 dependency로 동작한다.

반면, 원시 성능 데이터 수집 스크립트인 `apr/cccmp_20.py`, `apr/cccms_20.py`는 다음 추가 dependency를 사용할 수 있다.

```text
lz4
python-snappy
ascon
speck
pping
matplotlib
```

따라서 GS 인증 제출본에서는 다음 원칙을 적용한다.

| 구분 | 처리 |
|---|---|
| runtime export/check | 인증 표준 절차로 사용 |
| 원시 데이터 수집 | 별도 dependency 명시 후 선택 실행 |
| 모델 학습 결과 | metrics CSV와 runtime artifact로 증적 제출 |
| dependency 부족 | 명확한 오류 메시지와 설치 안내 제공 |

## 10. 테스트 케이스

| TC ID | 테스트 항목 | 실행 명령 | 기대 결과 |
|---|---|---|---|
| TC-ML-001 | runtime artifact export | `python tools/export_apr_xgb_runtime.py` | preprocessor, model JSON, runtime metadata 생성 |
| TC-ML-002 | APR runtime check | `python tools/check_apr_ml_runtime.py` | APR engine 추천 결과 반환 |
| TC-ML-003 | 자동화 증적 생성 | `python tools/run_apr_model_automation.py` | JSON report 생성 및 status `ok` |
| TC-ML-004 | metrics 확인 | `apr/xgb_metrics.csv` 확인 | R2, MAE, RMSE, MAPE 값 존재 |
| TC-ML-005 | CV metrics 확인 | `apr/xgb_cv_metrics.csv` 확인 | 5-fold CV 지표 존재 |

## 11. 개선 이관 사항

다음 단계에서 개선할 항목은 다음과 같다.

| 항목 | 개선 방향 |
|---|---|
| 단일 학습 CLI | 데이터 수집, 학습, export, check를 하나의 command로 통합 |
| 추가 dependency 정리 | `requirements-training.txt` 또는 optional extra 구성 |
| 학습 데이터 경로 표준화 | 입력 CSV/DB 경로를 환경변수 또는 CLI option으로 지정 |
| UI 연동 | APR Dashboard에서 모델 상태와 학습 결과 표시 |

