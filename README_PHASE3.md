# Phase 3: Unknown Payload Processing Enhancement

## 목적
2단계의 `mqtt_experiment_log` 기반 실험 로그 구조 위에, 미정의 payload를 단순 원문 저장에서 한 단계 확장하여 반복 출현하는 비정형 schema를 추적한다.

## 주요 변경

- `unknown_payload_data.schema_hash` 추가
- `unknown_schema_profile` 테이블 추가
- JSON payload의 field path를 기반으로 schema fingerprint 생성
- non-JSON/raw payload는 payload hash 기반 fingerprint 생성
- 미정의 payload 수신 시 schema profile 자동 upsert
- `/api/schema-stats` 추가
- `/api/schema-samples?schema_hash=...` 추가
- Dashboard에 `Unknown Schema Fingerprint` 패널 추가

## 실행

```bash
python server.py
python sensor_simulator.py
python random_pub.py test 2
```

## 논문 활용 포인트

본 단계는 실제 산업 IoT 환경에서 사전에 정의되지 않은 vendor-specific payload 또는 irregular JSON payload가 유입될 때, 이를 손실 없이 저장하면서 반복되는 schema 구조를 식별할 수 있음을 검증하기 위한 기능이다.
