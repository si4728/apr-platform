# IoT 시스템 코드 분석 보고서

분석 기준 폴더: `C:\access\iot`  
작성일: 2026-05-18

## 1. 시스템 개요

현재 폴더는 MQTT 기반 Industrial IoT 수집/분석 플랫폼입니다. 센서 시뮬레이터가 MQTT 브로커로 데이터를 발행하고, Flask 서버가 `iot/sensor/#` 토픽을 구독하여 수신 데이터를 SQLite에 저장합니다. 여기에 APR(Adaptive Policy Recommendation) 정책 추천, 압축/암호화/무결성 패킷 처리, 비정형 JSON 스키마 분석, 큐/지연시간 모니터링, 실험 실행 대시보드, G.711 음성 스트리밍 실험 기능이 결합되어 있습니다.

핵심 실행 흐름은 다음과 같습니다.

1. `sensor_simulator.py` 또는 `random_pub.py`가 센서 데이터를 MQTT로 발행합니다.
2. `server.py`가 MQTT 메시지를 수신합니다.
3. 일반 JSON, APR 인코딩 envelope, 비정형 JSON, non-JSON payload를 분기 처리합니다.
4. `database/db_manager.py`가 비동기 배치 방식으로 SQLite에 저장합니다.
5. Flask API와 HTML 대시보드가 통계, 지연시간, 스키마, 큐, APR, 음성 실험 결과를 시각화합니다.

## 2. 주요 파일 및 역할

| 경로 | 역할 |
| --- | --- |
| `server.py` | Flask 웹 서버, MQTT subscriber, DB 초기화, API 라우트, APR 수집/평가, 스키마 분석 |
| `sensor_simulator.py` | config 기반 다중 센서 MQTT publisher, 정책 제어 토픽 수신 |
| `random_pub.py` | 랜덤 payload publisher, APR 정책/동적 패킷 발행 실험용 |
| `config.json` | MQTT 브로커, 센서 목록, 플랫폼 기본 정책 설정 |
| `database/db_manager.py` | `queue.Queue` 기반 비동기 SQLite batch writer |
| `policy/apr_policy.py` | XGBoost 모델 기반 APR 추천 엔진, 실패 시 rule-based fallback |
| `policy/codec.py` | APR envelope 압축, AES-GCM 암호화, SHA-256 무결성, Base64 인코딩/디코딩 |
| `monitor/queue_monitor.py` | 수신/처리량, backlog, 처리 지연 추정 |
| `analysis/latency_analysis.py` | latency 통계, percentile, histogram, moving average 계산 |
| `experiment/*.py` | QoS, payload size, queue, schema, APR, voice 실험 스크립트 |
| `templates/*.html` | Flask 대시보드 화면 |
| `static/js/*.js`, `static/css/*.css` | 대시보드 차트/센서 설정 UI 로직과 스타일 |
| `phase1_schema.sql`, `phase2_schema.sql`, `phase3_schema.sql` | 단계별 DB 스키마 정의 |
| `apr/xgb_model.joblib`, `apr/xgb_model_meta.json` | APR 추천용 XGBoost 모델과 메타데이터 |
| `20260513/`, `20260515/` | 이전 버전 또는 백업성 코드 스냅샷 |
| `Lib/`, `Scripts/`, `Include/` | Python 가상환경 파일, 애플리케이션 코드 분석 대상에서는 보조로 취급 |

## 3. 아키텍처 분석

### 3.1 수집 계층

`server.py`는 MQTT broker `218.146.225.166:1883`에 연결하고 `iot/sensor/#`를 구독합니다. 수신 콜백 `on_message`는 다음 케이스를 처리합니다.

- JSON 파싱 실패: `unknown_payload_data`에 `non_json`으로 저장
- APR envelope: `metadata`와 `data` 필드 확인 후 `policy.codec.decode_payload`로 복원
- 정의된 센서 payload: `sensor_data`에 저장
- 정의되지 않은 JSON: `unknown_payload_data` 및 `unknown_schema_profile`에 저장

정의된 센서 payload로 인정되는 최소 필드는 `sensor_id`, `sensor_type`, `value`, `unit`입니다.

### 3.2 저장 계층

SQLite DB 파일은 `iot_data.db`입니다. 서버 시작 시 `init_db()`가 다음 주요 테이블을 생성하거나 마이그레이션합니다.

- `sensor_data`: 정상 센서 측정값
- `unknown_payload_data`: 비정형/오류/복호화 실패 payload
- `mqtt_experiment_log`: 실험 및 전체 MQTT 처리 로그
- `unknown_schema_profile`: schema hash 기반 비정형 payload 프로파일
- `voice_experiment_results`: G.711 voice over MQTT 실험 결과
- `apr_policy_log`: APR 정책 결정 및 피드백 추적

`database/db_manager.py`는 MQTT 콜백에서 직접 DB 쓰기를 하지 않고 큐에 넣은 뒤, 별도 daemon thread가 최대 50건 또는 0.1초 간격으로 transaction commit을 수행합니다. SQLite write lock과 콜백 지연을 줄이려는 설계입니다.

### 3.3 정책 추천 계층

`policy/apr_policy.py`는 `apr/xgb_model.joblib`와 `apr/xgb_model_meta.json`을 로드해 payload size, network latency, queue depth, topic, schema type을 기반으로 QoS, compression, encryption, integrity 조합을 추천합니다.

모델 메타데이터 기준 성능은 다음과 같습니다.

- 모델: XGBoost
- R2: 0.9051
- MAE: 0.1528
- RMSE: 0.3459
- 후보 feature: `environment`, `encryption_type`, `compress_method`, `hash_mode`

단, 현재 런타임 추천 후보는 실제 codec 지원 범위에 맞춰 `none`, `gzip`, `zlib`, `AES-GCM`, `sha256` 위주로 제한되어 있습니다.

### 3.4 APR 패킷 계층

`policy/codec.py`는 다음 envelope 형식을 사용합니다.

```json
{
  "metadata": {
    "publish_timestamp": "...",
    "experiment_id": "...",
    "seq": 1,
    "qos": 0,
    "compression": "zlib",
    "encryption": "AES-GCM",
    "integrity": "sha256",
    "hash": "..."
  },
  "data": "base64..."
}
```

처리 순서는 발행 시 `JSON 직렬화 -> 압축 -> 암호화 -> 무결성 해시 -> Base64`이고, 수신 시 역순으로 처리합니다.

### 3.5 스키마 분석 계층

정의되지 않은 JSON payload는 key path를 평탄화하여 schema hash를 만들고 `unknown_schema_profile`에 누적합니다. `/api/schema-clusters`는 schema key set 간 Jaccard similarity가 0.5 이상이면 같은 cluster로 묶습니다. 이 기능은 현장 IoT 환경에서 사전 정의되지 않은 payload 변화와 신규 장비 schema를 탐지하는 용도입니다.

### 3.6 대시보드/API 계층

`server.py`에는 30개 이상의 API/화면 라우트가 있습니다. 주요 화면은 다음과 같습니다.

- `/`: 단일 센서 dashboard
- `/all_dashboard`: 전체 센서 dashboard
- `/sensor_config`: 센서 설정 CRUD
- `/queue_dashboard`: queue/backlog 모니터링
- `/latency_dashboard`: latency 통계/히스토그램/추세
- `/experiment_dashboard`: 실험 실행
- `/schema_dashboard`: 비정형 schema 분석
- `/apr_dashboard`: APR 추천/발행 실험
- `/voice_dashboard`: voice streaming 실험 결과

### 3.7 실험 계층

`experiment/` 아래에는 다음 실험이 있습니다.

- `qos_test.py`: QoS 0/1/2 비교
- `payload_size_test.py`: payload 크기별 성능 비교
- `queue_test.py`: burst/queue 처리 실험
- `schema_variation_test.py`: schema 변화 실험
- `apr_validation.py`: APR API 추천 검증
- `voice_stream_test.py`: G.711 voice over MQTT 실험
- `research_profile_runner.py`: DB 기반 연구 리포트 생성

이미 생성된 `experiment_results/research_performance_report.md` 기준으로 과거 누적 데이터에는 `sensor_data` 약 418,365건, 비정형 schema 14개 cluster, 비정형 payload 4,358건, voice 실험 1건이 기록되어 있습니다.

## 4. 현재 설정 분석

`config.json` 기준 현재 MQTT broker는 `218.146.225.166:1883`이고, 센서는 5개입니다.

- `temp_001`: temperature, APR 정책 사용
- `humi_001`: humidity
- `vib_001`: vibration
- `vib_002`: number
- `temp_002`: temperature

플랫폼 설정은 다음과 같습니다.

- mode: `hybrid`
- experiment_id: `EXP_001`
- enable_experiment_log: `true`
- enable_apr: `false`
- default_qos: `0`
- default_policy: compression/encryption/integrity 모두 `none`

주의할 점은 platform의 `enable_apr`는 `false`이지만, 개별 센서 `temp_001`에는 `policy: "apr"`가 지정되어 있어 시뮬레이터 측에서는 APR 경로가 활성화될 수 있다는 점입니다.

## 5. 확인된 문제 및 리스크

### 5.1 APR encode_payload 호출 인자 오류

`policy.codec.encode_payload`의 시그니처는 다음과 같습니다.

```python
encode_payload(data_dict, policy, seq=0, experiment_id=None)
```

그러나 다음 위치에서는 `metadata_header`를 첫 번째 인자로, 실제 telemetry를 두 번째 인자로 전달합니다.

- `sensor_simulator.py` 191, 237
- `random_pub.py` 192, 230
- `server.py` 1678

이 경우 실제 센서 데이터가 압축/암호화 대상이 아니라 policy 객체처럼 해석되고, envelope metadata도 의도와 다르게 생성됩니다. 결과적으로 서버가 복호화 후 정의된 센서 payload로 인식하지 못하거나, APR 실험 데이터가 `json_undefined_schema`로 기록될 가능성이 큽니다.

정상 호출 예시는 `experiment/experiment_runner.py` 64처럼 `encode_payload(payload_dict, policy, seq=..., experiment_id=...)` 형태입니다.

### 5.2 APR 모델 의존성 누락 가능성

가상환경 `Lib/site-packages`에는 Flask, paho-mqtt, requests 등은 확인되지만 `joblib`, `pandas`, `scikit-learn`, `xgboost`, `cryptography`의 dist-info가 보이지 않습니다. `policy/apr_policy.py`는 모델 로드 시 `joblib`, 예측 시 `pandas`가 필요합니다. 의존성이 없으면 rule-based fallback으로 동작하거나 codec import가 실패할 수 있습니다.

### 5.3 가상환경 Python 실행 불가

`Scripts/python.exe` 실행 시 프로세스를 생성하지 못했습니다. `pyvenv.cfg`는 `C:\Users\82108\AppData\Local\Programs\Python\Python313\python.exe`를 원본으로 가리키는데, 현재 이 Python이 없거나 접근 불가한 상태로 보입니다. 즉 현재 폴더의 가상환경은 재생성 또는 Python 설치 경로 복구가 필요합니다.

### 5.4 보안 키 관리 미흡

`policy/codec.py`는 AES-GCM 키를 `b'\x01' * 16`으로 고정합니다. 실험용으로는 가능하지만 실제 시스템에서는 위험합니다. 키를 환경변수나 별도 secret 관리로 분리하고, key rotation 전략이 필요합니다.

### 5.5 인증/권한 없음

Flask API가 센서 설정 변경, 실험 실행, MQTT policy push를 수행하지만 인증/권한 체크가 없습니다. `/api/sensors`, `/api/experiment/run`, `/api/apr/*`는 운영 환경에서 보호되어야 합니다.

### 5.6 SQL/운영 안정성

대부분 parameterized query를 사용해 SQL injection 위험은 낮습니다. 다만 `add_column_if_missing`은 table/column/type 문자열을 f-string으로 구성합니다. 현재 내부 호출만 있으므로 즉시 위험은 작지만, 범용 함수로 확장될 경우 검증이 필요합니다.

### 5.7 외부 절대 경로 의존

`experiment/voice_stream_test.py`는 `c:\access\schedule\study\voice_over_mqtt\code\mqtt_voice_experiment_full_stable.py`라는 절대 경로 도구에 의존합니다. 다른 PC나 배포 환경에서는 voice 실험이 바로 실패합니다.

### 5.8 백업/가상환경/DB가 같은 폴더에 혼재

소스 코드, 실행 DB, zip, 가상환경, 과거 버전 스냅샷이 모두 같은 폴더에 있습니다. 유지보수와 배포 관점에서는 source, runtime data, archive, venv를 분리하는 편이 좋습니다.

## 6. 강점

- MQTT 수신 콜백과 DB 쓰기를 분리한 비동기 batch writer 구조가 좋습니다.
- 정의된 센서 데이터와 비정형 payload를 분리 저장해 장애 데이터도 버리지 않습니다.
- schema hash, Jaccard clustering, evolution timeline 등 연구/분석 관점 기능이 풍부합니다.
- latency histogram, trend, policy stats 등 실험 검증 API가 잘 갖춰져 있습니다.
- APR가 ML 모델 실패 시 rule-based fallback을 가지므로 최소 기능 유지가 가능합니다.
- 대시보드가 운영/실험/스키마/APR/voice 영역으로 분리되어 관찰성이 좋습니다.

## 7. 개선 권장 순서

1. `encode_payload` 호출부를 전부 수정해 실제 telemetry와 policy 인자를 올바르게 전달합니다.
2. Python 3.13 가상환경을 재생성하고 `requirements.txt`를 작성합니다.
3. `cryptography`, `joblib`, `pandas`, `scikit-learn/xgboost` 등 APR/codec 필수 의존성을 명시합니다.
4. AES-GCM 고정 키를 환경변수 기반 secret으로 교체합니다.
5. Flask 관리 API에 최소한의 인증 토큰 또는 내부망 접근 제한을 추가합니다.
6. voice 실험 도구의 절대 경로를 config 또는 프로젝트 내부 상대 경로로 전환합니다.
7. `server.py`의 기능을 Flask routes, MQTT handler, schema service, APR service, DB service로 분리해 유지보수성을 높입니다.
8. DB 파일과 experiment 결과물은 `data/`, `experiment_results/`처럼 런타임 산출물 폴더로 분리하고 백업 스냅샷은 `archive/`로 이동합니다.

## 8. 결론

현재 시스템은 단순 센서 모니터링 앱이 아니라, MQTT 기반 IoT gateway에 연구용 성능 계측, 비정형 schema intelligence, ML 기반 adaptive policy recommendation, G.711 voice streaming 실험까지 붙인 복합 실험 플랫폼입니다.

전체 방향성은 좋고 기능 폭도 넓습니다. 다만 현재 상태에서 가장 큰 실질 문제는 APR envelope 생성 호출 오류, 실행 불가능한 가상환경, 누락 가능성이 높은 ML/crypto 의존성입니다. 이 세 가지를 먼저 정리하면 시스템의 핵심 시나리오인 “센서 발행 -> APR 정책 적용 -> 서버 복호화/저장 -> 지연시간 분석” 흐름이 훨씬 안정적으로 검증될 수 있습니다.
