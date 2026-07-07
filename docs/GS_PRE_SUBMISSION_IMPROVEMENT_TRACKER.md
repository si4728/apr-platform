# GS 신청 전 보완 항목 추적표

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 신청 전 보완 필요성이 높은 5개 항목의 필요성, 현재 상태, 보완 계획, 증적 위치를 관리

## 1. 보완 항목 요약

| 보완 항목 | 필요성 | 현재 상태 | 우선순위 |
|---|---|---|---|
| 기능 ID 체계 확정 | 제품설명서·사용자취급설명서·테스트케이스 기능명이 1:1로 맞아야 함 | `GS_CERTIFICATION_SCOPE_V1.md`에는 F-001~F-024 상세 ID가 있고, 제품설명서는 F-001~F-016 요약 ID 체계 사용 중 | 높음 |
| 시험용 샘플 데이터 제공 | MQTT 수집, APR 추천, Dashboard 표시를 시험기관이 재현하기 위함 | Live E2E는 Web/API 중심으로 완료. client publish용 샘플 payload는 별도 정리 필요 | 높음 |
| APR 추천 결과 기준표 작성 | “정상 추천”의 판단 기준을 시험자가 확인할 수 있어야 함 | APR 모델 자동화 metric과 runtime check 증적은 있음. 추천 입력/출력 기준표 추가 필요 | 높음 |
| client별 실행 증적 추가 | PC/Raspberry Pi/Ubuntu client publish 증적 확보 필요 | client package 구성과 E2E preflight는 OK. 실제 client publish log 증적은 후속 보완 필요 | 중간 |
| Voice streaming 제외 문구 통일 | 시험 범위 혼선 방지 | 주요 문서에 제외 방침 반영. 최종 문서 전체 문구 일관성 계속 점검 필요 | 높음 |

## 2. 기능 ID 체계 확정

### 필요성

GS 시험에서는 제품설명서, 사용자취급설명서, 테스트 케이스의 기능명이 서로 맞아야 한다. 기능 ID가 문서마다 다르면 시험 범위 해석과 결함 관리가 어려워질 수 있다.

### 현재 상태

| 문서 | 현재 기능 ID 상태 |
|---|---|
| `docs/GS_CERTIFICATION_SCOPE_V1.md` | F-001~F-024 상세 기능 ID 정의 |
| `docs/GS_PRODUCT_DESCRIPTION_KO.md` | F-001~F-016 요약 기능 ID 정의 |
| `docs/GS_INTEGRATED_TEST_CASES.md` | TC ID 중심이며 기능 ID 직접 매핑은 제한적 |
| `docs/GS_USER_OPERATION_MANUAL_KO.md` | 절차 중심 설명이며 기능 ID 직접 매핑은 제한적 |

### 보완 계획

1. `GS_FUNCTION_ID_TRACEABILITY_MATRIX.md`를 작성한다.
2. F-001~F-024를 기준 기능 ID로 확정한다.
3. 제품설명서의 요약 기능은 F-001~F-024 상세 기능과 매핑한다.
4. 각 테스트 케이스에 대응 기능 ID를 연결한다.
5. readiness review에서 traceability matrix 존재 여부를 점검한다.

### 완료 기준

- F-001~F-024 기준 기능명 확정
- 기능 ID와 TC ID 1:1 또는 1:N 매핑표 작성
- 제품설명서·사용자취급설명서·테스트케이스 간 용어 차이 해소

## 3. 시험용 샘플 데이터 제공

### 필요성

시험기관이 MQTT 데이터 수집, Dashboard 표시, APR 추천 기능을 재현하려면 표준 payload 예시와 publish 절차가 필요하다.

### 보완 계획

1. 정상 센서 payload JSON 예시 작성
2. system metrics payload JSON 예시 작성
3. APR envelope 적용 payload 예시 작성
4. MQTT topic 예시 작성
5. PC/Raspberry Pi/Ubuntu client 실행 또는 publish 명령 예시 작성
6. Dashboard/API에서 확인할 결과 정의

### 권장 산출물

| 산출물 | 설명 |
|---|---|
| `docs/GS_SAMPLE_DATA_GUIDE.md` | 샘플 데이터와 publish 절차 설명 |
| `sample_data/gs/telemetry_normal.json` | 정상 센서 payload |
| `sample_data/gs/system_metrics.json` | system metrics payload |
| `sample_data/gs/apr_policy_input.json` | APR 추천 입력 예시 |

## 4. APR 추천 결과 기준표 작성

### 필요성

APR 추천 API가 응답하더라도 시험자는 추천 결과가 정상인지 판단할 기준이 필요하다. 입력 조건별 기대 정책 범위를 표로 제시해야 한다.

### 보완 계획

1. payload size, latency, queue depth, schema type 기준 입력 조합 정의
2. QoS, compression, encryption, integrity 기대 결과 또는 허용 범위 정의
3. model 기반 추천과 rule-based fallback의 차이를 설명
4. APR 모델 자동화 report와 연결

### 권장 산출물

| 산출물 | 설명 |
|---|---|
| `docs/GS_APR_RECOMMENDATION_CRITERIA.md` | APR 추천 정상 판단 기준표 |
| `sample_data/gs/apr_recommendation_cases.json` | APR 추천 테스트 입력 케이스 |

## 5. client별 실행 증적 추가

### 필요성

현재 Live E2E는 서버 Web/API 중심으로 통과했다. GS 시험에서 client package 기능을 확인하려면 PC, Raspberry Pi, Ubuntu/Linux client가 실제 telemetry를 publish하거나 최소한 실행 가능한 상태임을 보여주는 증적이 유리하다.

### 보완 계획

1. PC client package 다운로드 후 실행 log 확보
2. Raspberry Pi client package 구성 및 실행 절차 증적 확보
3. Ubuntu/Linux client package 실행 log 확보
4. 각 client의 telemetry topic, policy topic, client.config 확인
5. Dashboard/API에서 수신 결과 확인

### 권장 산출물

| 산출물 | 설명 |
|---|---|
| `docs/GS_CLIENT_EXECUTION_EVIDENCE_PLAN.md` | OS별 client 실행 증적 수집 계획 |
| `runtime/gs_certification_evidence/gs_client_execution_report.json` | 후속 자동/수동 증적 report |
| `runtime/gs_certification_evidence/gs_client_execution_report.md` | 후속 요약 report |

## 6. Voice streaming 제외 문구 통일

### 필요성

voice streaming 관련 code/process가 저장소에 남아 있으므로 시험자가 제품 범위를 혼동할 수 있다. 모든 제출 문서에서 “기존 기능 유지, GS 인증 평가 범위 제외”로 동일하게 표현해야 한다.

### 표준 문구

> Voice streaming 관련 code와 process는 향후 실증 및 확장 기능으로 보존하되, 본 GS 인증의 제품 기능 평가 범위와 테스트 케이스에서는 제외한다.

### 적용 대상 문서

| 문서 | 적용 상태 |
|---|---|
| `docs/GS_CERTIFICATION_SCOPE_V1.md` | 반영됨 |
| `docs/GS_PRODUCT_DESCRIPTION_KO.md` | 반영됨 |
| `docs/GS_USER_OPERATION_MANUAL_KO.md` | 반영됨 |
| `docs/GS_INTEGRATED_TEST_CASES.md` | 반영됨 |
| `docs/GS_APPLICATION_SUMMARY_KO.md` | 반영됨 |
| `docs/GS_PRECONSULTATION_ONE_PAGER_KO.md` | 반영됨 |
| `docs/GS_DEMO_SCENARIO_KO.md` | 반영됨 |

## 7. 추진 순서 제안

| 순서 | 작업 | 기대 산출물 |
|---:|---|---|
| 1 | 기능 ID traceability matrix 작성 | `GS_FUNCTION_ID_TRACEABILITY_MATRIX.md` |
| 2 | 샘플 데이터 및 publish 절차 작성 | `GS_SAMPLE_DATA_GUIDE.md`, `sample_data/gs/*.json` |
| 3 | APR 추천 기준표 작성 | `GS_APR_RECOMMENDATION_CRITERIA.md` |
| 4 | client별 실행 증적 계획 및 report 구조 작성 | `GS_CLIENT_EXECUTION_EVIDENCE_PLAN.md` |
| 5 | readiness review에 5개 보완 항목 점검 추가 | 자동 점검 강화 |

## 8. 신청 전 판단

현재 상태는 GS 신청 및 사전 상담 추진이 가능한 수준이다. 다만 본 문서의 5개 항목을 보완하면 시험기관의 기능 범위 확인, 재현 테스트, APR 추천 결과 판단, client 실행 확인, 제외 기능 범위 해석에 대한 리스크를 더 낮출 수 있다.