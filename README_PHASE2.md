# Phase 2 적용 내용

## 목표
운영 데이터 수집과 논문 실험 검증을 동시에 수행할 수 있도록 `mqtt_experiment_log` 중심의 실험 로그 구조를 강화했다.

## 주요 변경

1. `mqtt_experiment_log` 확장
   - `platform_mode`
   - `policy_key`
   - `latency_ms`
   - `schema_hash`
   - `created_at`

2. 실험 로그 저장 흐름
   - 정의된 센서 payload는 `sensor_data`와 `mqtt_experiment_log`에 동시 저장
   - 미정의 JSON/non-JSON payload는 `unknown_payload_data`와 `mqtt_experiment_log`에 동시 저장
   - `config.json`의 `platform.enable_experiment_log`가 `false`이면 실험 로그 저장을 중단할 수 있음

3. 추가 API
   - `/api/experiment-log`
   - `/api/latency-stats`
   - `/api/experiment-summary`
   - `/api/policy-stats`

4. Publisher 메타데이터
   - `experiment_id`
   - `platform_mode`
   - `seq`
   - `publish_timestamp`
   - `payload_size`
   - `policy`

## 실행 순서

```bash
python server.py
python sensor_simulator.py
python random_pub.py test 2
```

## 확인 API

```text
http://localhost:5000/api/experiment-log
http://localhost:5000/api/latency-stats
http://localhost:5000/api/experiment-summary
http://localhost:5000/api/policy-stats
```
