# GS 인증 신청서·추진계획서 작성용 최종 요약

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
작성 목적: GS 인증 신청서 및 추진계획서에 활용할 평가 필요성, 활용 계획, 기대효과, 준비도, 리스크 및 보완계획 정리

## 1. 제품 개요 요약

APR EdgeInsight Industrial IoT Platform v1.0은 산업 IoT 환경에서 PC, Raspberry Pi, Ubuntu/Linux edge client가 MQTT로 전송하는 센서 및 시스템 데이터를 수집하고, Dashboard와 REST API를 통해 장비 상태, 통신 지연, queue, payload schema, APR 정책 상태를 통합 관리하는 소프트웨어 제품이다.

본 제품은 APR(Adaptive Policy Recommendation) 기능을 통해 QoS, 압축, 암호화, 무결성 정책을 추천하고, Device 또는 Fleet 단위로 MQTT policy topic에 정책을 배포하여 client runtime 동작을 동적으로 변경할 수 있다. 또한 APR 모델 학습 자동화와 통합 증적 리포트 생성 도구를 포함하여 제품 품질과 운영 안정성을 반복 검증할 수 있도록 구성하였다.

## 2. 평가·인증 취득 필요성

### 2.1 기업 관점 필요성

당사는 산업 IoT 데이터 수집·관제 및 통신 정책 최적화 제품을 공공·제조 현장에 적용하기 위해 제품 품질, 보안성, 설치성, 사용자 문서 체계를 객관적으로 입증할 필요가 있다. GS 인증은 제품의 기능 적합성, 신뢰성, 사용성, 보안성, 호환성 등을 공인 기준으로 검증받는 절차이므로, 본 제품의 상용화 신뢰도를 높이고 공공·민간 고객의 도입 장벽을 낮추는 데 필요하다.

### 2.2 제품·서비스 전략과의 연계성

본 제품은 산업 현장의 edge device, MQTT broker, Dashboard, APR 정책 추천·배포 기능을 하나의 운영 플랫폼으로 제공한다. GS 인증을 통해 제품설명서, 사용자취급설명서, 설치 절차, 테스트 케이스, 보안 설정, Docker 운영 조건을 표준화하면 향후 지자체·공공기관 IoT 관제 사업, 제조기업 PoC, 스마트팩토리 통신 최적화 사업에 제출 가능한 상용SW 형태로 제품을 정리할 수 있다.

### 2.3 인증 추진 필요성

현재 제품은 Docker 인증 실행 환경, 보안 설정 검증, APR 모델 자동화, E2E 사전 점검, Live E2E 증적, 제출 패키지 자동 구성 체계를 갖추고 있다. 이 기반을 GS 인증 시험 기준에 맞춰 정리하면 시험기관 평가 대응, 결함 보완, 공공조달 진입 준비를 체계적으로 추진할 수 있다.

## 3. 인증 대상 범위

GS 인증 대상은 상용 운영 기능으로 고정한다.

| 구분 | 인증 포함 여부 | 설명 |
|---|---:|---|
| Docker 기반 서버 실행 | 포함 | `docker-compose.cert.yml` 기준 서버와 MQTT broker 실행 |
| 사용자 인증 및 권한 관리 | 포함 | 관리자/일반 사용자 로그인, 권한 제한, 접근 로그 |
| Dashboard 관제 | 포함 | 센서, latency, queue, schema, APR 상태 확인 |
| MQTT 데이터 수집 | 포함 | client telemetry 수신 및 DB 저장 |
| Site/Group/Fleet/Device 관리 | 포함 | 조직·장비·topic 경로 관리 |
| PC client | 포함 | Windows/Linux PC telemetry publisher |
| Raspberry Pi client | 포함 | 센서 및 system metrics publisher |
| Ubuntu/Linux client | 포함 | Linux edge/test publisher |
| Dynamic Client Policy Control | 포함 | policy topic 기반 QoS/압축/암호화/무결성 정책 변경 |
| Client Runtime Configuration Update | 포함 | system metrics client의 수집 주기, metric 목록, pause/resume 변경 |
| APR 모델 학습 자동화 | 포함 | 모델 artifact, metric, runtime export/loading 증적 생성 |
| 통합 증적 및 제출 패키지 자동화 | 포함 | GS evidence report, E2E preflight, Live E2E, readiness review, package builder |
| Voice streaming | 제외 | code/process는 유지하되 GS 인증 평가 범위에서는 제외 |
| 논문·연구용 실험 산출물 | 제외 | 상용SW 제출 패키지에서 제외 |

## 4. 인증 활용 계획

| 시기 | 활용 계획 | 목표 지표 |
|---|---|---|
| 2026년 하반기 | GS 인증 취득 및 제품설명서, 사용자취급설명서, 설치 매뉴얼, 테스트 케이스 정비 | 인증 제출 문서 1식 완성 |
| 2026년 하반기 | 울산 및 지역 제조기업 대상 PoC 추진 | PoC 2건 추진 |
| 2027년 상반기 | 공공기관 및 지자체 IoT 관제 사업 제안 | 제안 3건 이상 |
| 2027년 상반기 | 나라장터 등록 또는 공공조달 진입 준비 | 조달 등록 준비 자료 1식 |
| 2027년 내 | 신규 거래처 확보 | 신규 거래처 3개 이상 |
| 2027년 내 | GS 인증 기반 매출 창출 | 관련 매출 1억 원 이상 목표 |

## 5. 기업 역량 및 준비도

### 5.1 사전 준비 상태

본 제품은 인증 범위 정의, Docker 인증 실행 환경, 보안 설정 검증, 제품설명서, 사용자취급설명서, 통합 테스트 케이스, 제출 패키지 자동 구성 도구를 갖추고 있다. 또한 실제 Docker Live E2E를 통해 Web root, 로그인, system status, broker status, DB status API가 정상 응답함을 확인하였다.

### 5.2 추진 역량

| 역량 구분 | 준비 내용 |
|---|---|
| 제품 범위 관리 | GS 인증 범위와 제외 기능을 문서화하고 voice streaming을 인증 제외로 분리 |
| 설치·운영 표준화 | Docker compose 인증 실행 조건과 `.env.cert` 작성 절차 정리 |
| 보안 설정 | 기본 secret, 기본 계정 비밀번호, 기본 APR AES key 사용 차단 |
| 테스트 증적 | E2E preflight, Live E2E, APR 모델 자동화, readiness review 리포트 생성 |
| 제출 패키지 | DB, 로그, secret, venv를 제외하는 제출 패키지 자동 구성 도구 제공 |
| 문서화 | 제품설명서, 사용자취급설명서, 테스트 케이스, 보안/설치/APR 문서 작성 |

## 6. 인증 취득 가능성

본 제품은 GS 인증에서 요구되는 실행 소프트웨어, 제품설명서, 사용자취급설명서, 테스트 증적의 기본 구조를 갖추고 있다. 특히 Docker 기반 인증 실행 조건을 마련하여 시험기관 환경에서 동일한 실행 조건을 재현할 수 있도록 하였고, 보안 설정 검증과 통합 증적 리포트 생성으로 제출 전 품질 확인을 자동화하였다.

| 평가 요소 | 준비 상태 |
|---|---|
| 기능 적합성 | 인증 범위 기능 ID 정리, 통합 테스트 케이스 작성 |
| 성능 효율성 | 비동기 DB writer, queue/backlog 모니터링, latency 통계 제공 |
| 호환성 | Docker 서버, PC/Raspberry Pi/Ubuntu Linux client 지원 |
| 사용성 | Dashboard, client package 자동 생성, 사용자취급설명서 작성 |
| 신뢰성 | DB health, system lock, MQTT startup error 처리, APR fallback 제공 |
| 보안성 | 인증 모드 보안 설정 검증, password hash, AES-GCM envelope 지원 |
| 유지보수성 | 제출 패키지 자동 구성, readiness review, manifest hash 제공 |

## 7. 기대효과

### 7.1 기업 내부 효과

GS 인증 추진을 통해 제품 범위, 설치 절차, 보안 설정, 테스트 케이스, 사용자 문서가 표준화되어 내부 품질관리 체계가 고도화된다. 또한 기본 secret 제거, 설정 파일 분리, Docker 실행 조건 정리, 오류 조치 문서화가 이루어져 제품 운영 안정성과 보안 관리 수준이 향상된다.

### 7.2 시장·고객 신뢰 효과

GS 인증은 공인 품질인증으로 공공기관 및 민간 제조기업에 제품 신뢰성을 제시하는 근거가 된다. 인증 취득 후 제품 제안서, PoC, 공공조달 등록 준비 과정에서 객관적인 품질 검증 자료로 활용할 수 있다.

### 7.3 지역 산업 파급효과

울산 및 지역 제조기업의 산업 IoT 현장에 적용할 경우, MQTT 기반 데이터 수집과 APR 정책 최적화를 통해 현장 네트워크 운영 효율을 높일 수 있다. 또한 지역 협력기업과의 PoC, 공동 실증, 제조 현장 적용 사례를 확보하여 지역 내 인증 SW 도입과 산업 경쟁력 강화에 기여할 수 있다.

## 8. 남은 리스크 및 보완계획

| 리스크 | 영향 | 보완계획 |
|---|---|---|
| Docker build 시간이 길다 | 시험기관 환경에서 최초 build 시간이 길어질 수 있음 | 사전 build image 제공 방안 검토, dependency cache 또는 slim runtime image 최적화 추진 |
| 실제 시험기관 `.env.cert` 작성 필요 | secret 누락 시 서버 시작 실패 | 사용자취급설명서와 보안 설정 가이드에 필수 항목 명시, 검증 스크립트 제공 |
| Live E2E는 기본 API 중심 | 실제 장비 송수신 증적은 제한적 | 후속 단계에서 PC/Raspberry Pi/Ubuntu client 실제 publish 증적 추가 생성 |
| Voice streaming 코드 존재 | 인증 범위 혼선 가능성 | 모든 제출 문서에서 기존 기능 유지·인증 범위 제외로 일관 표시 |
| 운영 DB/로그 제출 위험 | 개인정보 또는 개발 로그 포함 가능성 | 제출 패키지 builder에서 DB, log, secret, venv, cache 자동 제외 |
| Docker volume stale lock | 반복 시험 시 이전 runtime lock 영향 가능 | Live E2E 전 `docker compose down -v` 또는 runtime volume 초기화 절차 문서화 |

## 9. 신청서 기재용 핵심 문구

본 제품은 산업 IoT 환경에서 MQTT 기반 데이터 수집, Dashboard 관제, APR 기반 통신 정책 추천·배포, PC/Raspberry Pi/Ubuntu Linux client package 생성 기능을 제공하는 상용SW이다. GS 인증을 통해 제품의 기능 적합성, 설치성, 보안성, 신뢰성, 사용성을 객관적으로 검증받고, 공공기관 및 제조기업 대상 IoT 관제·통신 최적화 사업 진입 기반을 마련하고자 한다.

인증 취득 후에는 2026년 하반기 지역 제조기업 PoC 2건, 2027년 상반기 공공기관·지자체 IoT 관제 사업 제안 3건 이상, 2027년 내 신규 거래처 3개 이상 확보 및 관련 매출 1억 원 이상 달성을 목표로 한다. 이를 통해 기업 내부 품질·보안 관리체계를 고도화하고, 지역 제조 산업의 IoT 데이터 활용 및 통신 운영 효율 향상에 기여하고자 한다.

## 10. 제출 전 최종 확인

- 제품설명서, 사용자취급설명서, 테스트 케이스의 인증 범위가 동일해야 한다.
- APR 모델 학습 자동화, Dynamic Client Policy Control, Client Runtime Configuration Update는 인증 포함으로 표시한다.
- Voice streaming은 기존 code/process 유지, 인증 범위 제외로 표시한다.
- `.env.cert`, 운영 DB, 로그, venv, cache는 제출본에서 제외한다.
- `gs_evidence_report`, `gs_e2e_preflight_report`, `gs_live_e2e_report`, `gs_readiness_review`의 상태가 `ok`인지 확인한다.
- 제출 패키지 manifest에서 제외 대상 파일이 포함되지 않았는지 확인한다.