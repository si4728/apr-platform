# GS APR Model Automation Test Cases

작성일: 2026-07-06  
대상 기능: F-021 APR 모델 학습 자동화

| TC ID | 분류 | 테스트 항목 | 사전 조건 | 실행 절차 | 기대 결과 | 증적 |
|---|---|---|---|---|---|---|
| TC-ML-001 | Export | Runtime artifact export | `apr/xgb_model.joblib`, `apr/xgb_model_meta.json` 존재 | `python tools/export_apr_xgb_runtime.py` 실행 | `apr/xgb_preprocessor.joblib`, `apr/xgb_model.json`, `apr/xgb_runtime_meta.json` 생성 | 명령 출력, 파일 목록 |
| TC-ML-002 | Runtime | APR model loading check | requirements 설치 완료 | `python tools/check_apr_ml_runtime.py` 실행 | `loaded_runtime_model=true` 또는 fallback 상태와 추천 JSON 확인 | JSON 출력 |
| TC-ML-003 | Evidence | 자동화 report 생성 | TC-ML-001, TC-ML-002 실행 가능 | `python tools/run_apr_model_automation.py` 실행 | `runtime/apr_model_automation_report.json` 생성, `overall_status=ok` | report JSON |
| TC-ML-004 | Metrics | 단일 평가 지표 확인 | `apr/xgb_metrics.csv` 존재 | CSV 파일 확인 | R2, MAE, RMSE, MAPE 값 존재 | CSV 캡처 |
| TC-ML-005 | CV Metrics | Cross validation 지표 확인 | `apr/xgb_cv_metrics.csv` 존재 | CSV 파일 확인 | 5-fold CV 및 평균/표준편차 지표 존재 | CSV 캡처 |
| TC-ML-006 | Docker | Docker 내부 모델 자동화 실행 | 인증용 compose 실행 중 | `docker compose -f docker-compose.cert.yml --env-file .env.cert exec iot-dashboard python tools/run_apr_model_automation.py` 실행 | 컨테이너 내부에서 report 생성 | compose log, report JSON |
| TC-ML-007 | Fallback | 모델 실패 fallback 확인 | 모델 파일 임시 비활성화 가능한 시험환경 | 모델 파일을 시험용 경로에서 제외하고 `check_apr_ml_runtime.py` 실행 | 서버/APR engine이 rule-based fallback 사용 | JSON 출력 |

