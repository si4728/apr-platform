# GS 인증 사전 상담용 1페이지 요약

작성일: 2026-07-07  
제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 인증 시험기관 사전 상담 시 제품 개요, 인증 범위, 준비 상태, 주요 확인 요청사항을 1페이지로 설명

## 1. 제품 개요

APR EdgeInsight Industrial IoT Platform v1.0은 산업 IoT 환경에서 PC, Raspberry Pi, Ubuntu/Linux edge client가 MQTT로 전송하는 센서 및 시스템 데이터를 수집하고, Dashboard와 REST API를 통해 장비 상태, 통신 지연, queue, payload schema, APR 정책 상태를 통합 관제하는 소프트웨어이다.

제품의 핵심 차별점은 APR(Adaptive Policy Recommendation) 기능이다. 수집 데이터와 모델 기반 판단을 활용하여 QoS, 압축, 암호화, 무결성 정책을 추천하고, Device 또는 Fleet 단위로 MQTT policy topic에 배포하여 client runtime 동작을 동적으로 변경한다.

## 2. GS 인증 대상 범위

| 구분 | 인증 포함 여부 | 설명 |
|---|---:|---|
| Docker 기반 서버 실행 | 포함 | `docker-compose.cert.yml` 기준 Dashboard 서버와 MQTT broker 실행 |
| 사용자 인증/권한 관리 | 포함 | 관리자/일반 사용자 로그인, 권한 제한, 접근 로그 |
| Dashboard 관제 | 포함 | 센서, latency, queue, schema, APR 상태 확인 |
| Device/Fleet 관리 | 포함 | 장비 등록, topic 생성, client package 다운로드 |
| PC/Raspberry Pi/Ubuntu Linux client | 포함 | OS별 client package 생성 및 실행 절차 제공 |
| Dynamic Client Policy Control | 포함 | policy topic 기반 QoS/압축/암호화/무결성 변경 |
| Client Runtime Configuration Update | 포함 | system metrics client 수집 주기, metric, pause/resume 변경 |
| APR 모델 학습 자동화 | 포함 | 모델 artifact, metric, runtime export/loading 증적 생성 |
| 보안 설정 검증 | 포함 | 기본 secret/password/AES key 사용 차단 |
| 통합 증적/제출 패키지 자동화 | 포함 | evidence report, live E2E, readiness review, package builder |
| Voice streaming | 제외 | 기존 code/process는 유지하되 GS 인증 평가 범위에서는 제외 |
| 연구/논문용 산출물 | 제외 | 제품 실행·평가 범위에서 제외 |

## 3. 현재 준비 상태

| 항목 | 준비 상태 |
|---|---|
| 제품설명서 | 작성 완료: `docs/GS_PRODUCT_DESCRIPTION_KO.md` |
| 사용자취급설명서 | 작성 완료: `docs/GS_USER_OPERATION_MANUAL_KO.md` |
| 통합 테스트 케이스 | 작성 완료: `docs/GS_INTEGRATED_TEST_CASES.md` |
| Docker 설치/운영 문서 | 작성 완료 |
| 보안 설정 검증 | `tools/check_certification_config.py` 구현 완료 |
| APR 모델 자동화 증적 | `tools/run_apr_model_automation.py` 구현 및 검증 완료 |
| E2E 사전 점검 | `status=ok` |
| Docker Live E2E | Web/Login/System/Broker/DB API `200 OK` 확인 |
| Readiness review | `status=ok` |
| 제출 패키지 자동 구성 | zip 및 `PACKAGE_MANIFEST.json` 생성 가능 |
| secret/DB/log 제외 | 제출 패키지 builder에서 자동 제외 |

## 4. 시험기관에 확인하고 싶은 사항

| 확인 요청사항 | 이유 |
|---|---|
| Docker compose 기반 제출 가능 여부 | 제품 실행 기준을 Docker로 고정했기 때문 |
| `.env.cert`를 현장 작성 방식으로 제출 가능한지 | secret 원문을 공개 제출본에 포함하지 않기 위함 |
| APR 모델 학습 자동화 기능의 시험 범위 인정 방식 | 모델 artifact/export/loading 증적을 제품 기능으로 포함하기 위함 |
| client package 시험 방식 | PC/Raspberry Pi/Ubuntu Linux client를 OS별로 검증하기 위함 |
| voice streaming 제외 표기 방식 | code/process는 있으나 인증 범위에서 제외하기 위함 |
| Live E2E 증적의 인정 범위 | Docker 기동 및 기본 API 응답 증적을 사전 제출 자료로 활용하기 위함 |

## 5. 상담 시 제시할 핵심 문구

본 제품은 산업 IoT 현장의 MQTT 데이터 수집·관제·통신 정책 최적화 플랫폼이며, GS 인증 범위는 상용 운영 기능으로 한정하였다. Docker 기반 실행 환경, 제품설명서, 사용자취급설명서, 통합 테스트 케이스, 보안 설정 검증, APR 모델 자동화 증적, Live E2E 증적, 제출 패키지 자동 구성까지 준비되어 있다. 사전 상담에서는 Docker 기반 제출 방식, client package 시험 방식, APR 모델 자동화 기능의 평가 범위, voice streaming 제외 표기 방식에 대해 시험기관과 기준을 맞추고자 한다.