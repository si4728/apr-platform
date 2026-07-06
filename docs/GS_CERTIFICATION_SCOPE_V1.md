# GS Certification Product Scope Definition

작성일: 2026-07-01  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0  
목적: GS 인증 제출 대상 기능과 제외 기능을 고정하여 제품설명서, 사용자취급설명서, 설치 매뉴얼, 테스트 케이스 작성 기준으로 사용한다.

## 1. 제품 범위 확정 결론

GS 인증 대상 제품은 다음 범위로 고정한다.

```text
APR EdgeInsight Industrial IoT Platform v1.0
```

본 제품은 산업 IoT 환경에서 MQTT 기반 센서 및 edge device 데이터를 수집하고, 웹 대시보드에서 장치/센서/통신 상태를 관리하며, APR 정책 추천을 통해 QoS, 압축, 암호화, 무결성 정책을 장치에 배포하는 소프트웨어 플랫폼이다.

인증 제품은 "상용 운영 기능" 중심으로 구성하며, 논문 검증, 실험 자동화, voice streaming 실험, 학습용 스크립트, 대용량 연구자료는 인증 대상에서 제외한다.

## 2. 인증 대상 제품 구성

| 구성 | 인증 포함 여부 | 설명 |
|---|---:|---|
| Flask 웹 서버 | 포함 | 대시보드, REST API, 인증/권한, 시스템 상태 제공 |
| MQTT subscriber | 포함 | 센서 및 edge client의 MQTT payload 수신 |
| SQLite 저장 기능 | 포함 | 센서 데이터, unknown payload, latency, 정책 로그 저장 |
| 비동기 DB writer | 포함 | queue 기반 batch write 및 DB 상태 모니터링 |
| 웹 대시보드 | 포함 | 센서, 장치, latency, queue, schema, APR 상태 확인 |
| 사용자/권한 관리 | 포함 | 사용자, 관리자, 접근 로그, 감사 로그 관리 |
| Site/Group/Fleet/Device 관리 | 포함 | 조직 및 장치 단위 관리, topic 자동 생성 |
| Client package 생성 | 포함 | PC, Raspberry Pi, Ubuntu/Linux 실행 패키지 생성 |
| APR 정책 추천 | 포함 | XGBoost 모델 또는 rule-based fallback 기반 정책 추천 |
| APR 정책 배포 | 포함 | 장치/Fleet policy topic으로 정책 publish |
| APR envelope codec | 포함 | zlib/gzip, AES-GCM, sha256 지원 |
| 모니터링 API | 포함 | broker, DB, queue, latency, schema 상태 확인 |
| PC client | 포함 | Windows/Linux PC 테스트 및 edge publisher |
| Raspberry Pi client | 포함 | 센서 publisher 및 system metrics publisher |
| Ubuntu/Linux client | 포함 | Linux edge 또는 테스트 client 실행 |

## 3. 인증 제외 또는 분리 대상

아래 항목은 GS 인증 범위에서 제외한다. 인증 제출본에서는 메뉴에서 숨기거나, 문서상 "연구/실험 부가 기능"으로 분리한다.

| 구분 | 제외 대상 | 제외 사유 | 처리 방안 |
|---|---|---|---|
| 연구 실험 | `experiment/` 전체 | 논문/성능 검증용 실험 스크립트 | 인증 제출본에서 제외 또는 관리자 개발용으로 분리 |
| Voice 실험 | `/voice_dashboard`, `/api/voice/results`, `experiment/voice_stream_test.py` | G.711 voice streaming은 핵심 상용 IoT 제품 범위와 다름 | 메뉴 숨김, 문서상 제외 |
| 실험 실행 화면 | `/experiment_dashboard`, `/api/experiment/run` | GS 인증 기능 범위 혼란 가능 | 인증 모드에서 숨김 권장 |
| 모델 학습/검증 | `apr/cccmp_20.py`, `apr/cccms_20.py`, `apr/cccm_sinario.py`, 학습 metrics CSV | 학습/연구 산출물이며 운영 기능이 아님 | runtime model 파일만 포함 |
| 논문 자료 | `docs/thesis_*`, `docs/thesis_review_sections/`, 논문 docx/pdf | 연구 문서이며 제품 설명서가 아님 | 인증 패키지 제외 |
| 발표/제안 자료 | 대용량 pptx/docx/pdf 소개자료 | 영업/연구 자료이며 실행 제품 아님 | 인증 패키지 제외 |
| 운영 DB 백업 | `*.bak`, `*.malformed*`, `*.recovered*`, `iot_data.db-wal`, `iot_data.db-shm` | 개인정보/운영 데이터 및 대용량 파일 위험 | 샘플 DB 또는 초기 DB만 제공 |
| 로그 파일 | `*.log` | 개발/운영 임시 산출물 | 인증 제출본 제외 |
| DB 복구 도구 | `tools/recover_iot_db.py` | 운영자 긴급 도구이며 일반 제품 기능 아님 | 관리자 유지보수 도구로 별도 분리 |
| 논문 수정 도구 | `tools/revise_thesis_2026611.py` | 제품 기능과 무관 | 인증 제출본 제외 |

## 4. 인증 포함 웹 화면

| URL | 화면명 | 인증 포함 여부 | 인증 기능 설명 |
|---|---|---:|---|
| `/login` | 로그인 | 포함 | 사용자 인증 |
| `/register` | 사용자 등록 | 포함 검토 | 운영 정책에 따라 관리자 생성/일반 가입 중 하나로 고정 필요 |
| `/` | 메인 대시보드 | 포함 | 센서 데이터 및 시스템 요약 확인 |
| `/all_dashboard` | 전체 센서 대시보드 | 포함 | 다중 센서 데이터 확인 |
| `/sensor_config` | 센서 설정 | 포함 | 센서 정의 등록/수정/삭제 |
| `/device_management` | 장치 관리 | 포함 | 사용자, Fleet, Device, topic, client package 관리 |
| `/queue_dashboard` | Queue 대시보드 | 포함 | DB writer queue 및 backlog 모니터링 |
| `/latency_dashboard` | Latency 대시보드 | 포함 | 지연시간 통계 및 추세 확인 |
| `/schema_dashboard` | Schema 대시보드 | 포함 | unknown payload, schema profile, USI 관리 |
| `/apr_dashboard` | APR 대시보드 | 포함 | 정책 추천, 정책 배포, APR 상태 확인 |
| `/admin/users` | 관리자 사용자 관리 | 포함 | 사용자 상태 및 권한 관리 |
| `/admin/access-logs` | 접근 로그 | 포함 | 접근 이력 확인 |
| `/admin/audit-logs` | 감사 로그 | 포함 | 설정/정책 변경 이력 확인 |
| `/device_edge_doc` | Edge 문서 | 포함 | 장치 client 안내 |
| `/server_operation_manual` | 서버 운영 문서 | 포함 | 서버 운영 안내 |

## 5. 인증 제외 웹 화면

| URL | 화면명 | 처리 방안 |
|---|---|---|
| `/experiment_dashboard` | 실험 대시보드 | 인증 모드에서 메뉴 숨김 권장 |
| `/voice_dashboard` | Voice streaming 대시보드 | 인증 대상 제외, 메뉴 숨김 권장 |

## 6. 인증 포함 API 범위

| API 그룹 | 포함 API 예시 | 인증 기능 |
|---|---|---|
| 인증/사용자 | `/api/auth/me`, `/logout`, `/api/admin/users`, `/api/admin/users/<id>/status` | 사용자 인증 및 관리자 관리 |
| Site/Group | `/api/admin/sites`, `/api/admin/groups`, `/api/admin/site-tree` | 조직 구조 관리 |
| Fleet | `/api/fleets`, `/api/fleets/<id>` | Fleet 등록/수정/삭제 |
| Device | `/api/devices`, `/api/devices/<id>`, `/api/devices/<id>/client-package` | 장치 관리 및 client package 생성 |
| Policy | `/api/devices/<id>/policy`, `/api/devices/<id>/policy/apply`, `/api/fleets/<id>/policy/apply` | 장치/Fleet 정책 적용 |
| Sensor | `/api/sensors`, `/api/sensors/<sensor_id>`, `/api/chart/<sensor_id>` | 센서 정의 및 차트 |
| System status | `/api/system/status`, `/api/broker/status`, `/api/db/status` | 시스템 상태 확인 |
| Queue | `/api/queue-stats`, `/api/topic-rate`, `/api/backlog-estimation` | queue/backlog 모니터링 |
| Latency | `/api/latency-stats`, `/api/latency-histogram`, `/api/latency-trend` | latency 분석 |
| APR | `/api/apr/recommend`, `/api/apr/collection/status`, `/api/apr/collection/start`, `/api/apr/collection/evaluate`, `/api/apr/publish-with-policy` | APR 추천 및 검증 |
| Schema | `/api/schema-stats`, `/api/schema-inference/<schema_hash>`, `/api/schema-samples`, `/api/unknown-payloads`, `/api/schema-clusters`, `/api/schema-evolution` | payload schema 관리 |
| USI | `/api/usi/profiles/<schema_hash>/definition`, `/api/usi/profiles/<schema_hash>/approve`, `/api/usi/profiles/<schema_hash>/reject` | unknown schema 승인/거절 |

## 7. 인증 제외 API 범위

| API | 제외 사유 | 처리 방안 |
|---|---|---|
| `/api/experiment/run` | 연구/실험 자동 실행 API | 인증 모드에서 비활성화 또는 관리자 개발 기능으로 분리 |
| `/api/voice/results` | voice streaming 실험 결과 API | 인증 대상 제외 |

## 8. 인증 포함 파일 범위

| 경로 | 포함 여부 | 설명 |
|---|---:|---|
| `server.py` | 포함 | 메인 서버 |
| `requirements.txt` | 포함 | Python dependency |
| `Dockerfile` | 포함 | Docker 실행 |
| `docker-compose.yml` | 포함 | Docker compose 실행 |
| `config.example.json` | 신규 필요 | 인증용 설정 예시 |
| `.env.example` | 신규 필요 | 인증용 환경변수 예시 |
| `policy/apr_policy.py` | 포함 | APR 추천 엔진 |
| `policy/codec.py` | 포함 | APR envelope codec |
| `database/db_manager.py` | 포함 | DB writer |
| `monitor/queue_monitor.py` | 포함 | queue monitor |
| `publisher/async_publisher.py` | 포함 | async publisher |
| `device/` client runtime 파일 | 포함 | PC/Raspberry Pi/Ubuntu client |
| `templates/` | 포함 | 인증 대상 UI |
| `static/` | 포함 | 인증 대상 UI assets |
| `tools/check_*.py` | 포함 검토 | 설치/상태 점검 도구 |
| `tools/e2e_*.py` | 포함 검토 | 인증 전 자체 테스트 도구 |

## 9. 인증 제외 파일 범위

| 경로/패턴 | 제외 사유 |
|---|---|
| `experiment/` | 논문/성능 실험 기능 |
| `experiment_results/` | 실험 결과물 |
| `docs/thesis_*` | 논문 자료 |
| `docs/*pptx`, `docs/*docx`, `docs/*pdf` 중 제품 문서가 아닌 자료 | 영업/연구/제안 자료 |
| `*.log` | 운영 로그 |
| `*.bak` | 백업 파일 |
| `*.malformed*`, `*.recovered*`, `*.corrupt*` | DB 복구/손상 파일 |
| `iot.zip` | 임시 압축 파일 |
| `iot_data.db` 운영본 | 대용량 운영 데이터. 인증용 샘플 DB와 분리 필요 |
| `__pycache__/` | Python cache |

## 10. 인증 제품 기능 목록

| 기능 ID | 기능명 | 인증 포함 | 기능 설명 |
|---|---|---:|---|
| F-001 | 사용자 로그인 | 포함 | 등록 사용자 인증 및 세션 관리 |
| F-002 | 사용자/권한 관리 | 포함 | 관리자 사용자 관리, 상태 변경, 비밀번호 초기화 |
| F-003 | 접근/감사 로그 | 포함 | 접근 및 주요 관리 작업 이력 조회 |
| F-004 | Site/Group 관리 | 포함 | 조직 단위 및 topic path 관리 |
| F-005 | Fleet 관리 | 포함 | 장치 그룹 및 소유자 관리 |
| F-006 | Device 관리 | 포함 | 장치 등록, 수정, 삭제, OS 설정 |
| F-007 | Topic 자동 생성 | 포함 | 사용자/Fleet/Device 기준 telemetry/policy topic 생성 |
| F-008 | Client package 생성 | 포함 | OS별 client ZIP 다운로드 |
| F-009 | MQTT 데이터 수집 | 포함 | telemetry topic payload 수신 |
| F-010 | 정상 센서 데이터 저장 | 포함 | 표준 sensor payload 저장 및 chart 제공 |
| F-011 | Unknown payload 저장 | 포함 | 비정형 payload 별도 저장 및 분석 |
| F-012 | Schema profile 관리 | 포함 | schema hash, field, sample, 승인/거절 관리 |
| F-013 | Queue 모니터링 | 포함 | DB writer queue, backlog, topic rate 확인 |
| F-014 | Latency 모니터링 | 포함 | latency 통계, histogram, trend 확인 |
| F-015 | Broker/DB/System 상태 | 포함 | 운영 상태 API와 dashboard 확인 |
| F-016 | APR 정책 추천 | 포함 | payload/network/queue/schema 기반 정책 추천 |
| F-017 | APR 정책 배포 | 포함 | device 또는 fleet policy topic으로 정책 publish |
| F-018 | APR envelope 처리 | 포함 | compression, encryption, integrity 적용 payload 처리 |
| F-019 | PC client 실행 | 포함 | Windows/Linux PC publisher 실행 |
| F-020 | Raspberry Pi client 실행 | 포함 | 센서 및 system metrics publisher 실행 |
| F-021 | Ubuntu/Linux client 실행 | 포함 | Linux edge publisher 실행 |

## 11. 인증 제외 기능 목록

| 기능 ID | 기능명 | 제외 사유 |
|---|---|---|
| X-001 | QoS/Payload/Queue 실험 실행 | 연구/성능 실험 기능 |
| X-002 | Voice streaming 실험 | 본 제품의 산업 IoT 관리 핵심 기능과 별도 |
| X-003 | 논문 리포트 생성 | 제품 기능 아님 |
| X-004 | XGBoost 모델 학습 스크립트 | 운영 runtime이 아닌 개발/연구 기능 |
| X-005 | DB 복구 스크립트 | 유지보수 도구이며 일반 사용자 기능 아님 |

## 12. 사용자 유형

| 사용자 유형 | 인증 범위 내 역할 |
|---|---|
| 관리자 | 사용자, Site, Group, Fleet, Device, 정책, 로그, 시스템 상태 관리 |
| 운영자 | 센서/장치 상태 확인, client package 다운로드, APR 정책 적용 |
| 일반 사용자 | 본인 권한 범위 내 dashboard 조회 및 장치 상태 확인 |
| Edge client 운영자 | PC/Raspberry Pi/Ubuntu client 설치 및 실행 |

## 13. 인증 제출용 메뉴 정리 방안

1단계 기준으로 메뉴는 아래처럼 정리한다.

| 메뉴 | 인증 제출본 처리 |
|---|---|
| Dashboard | 유지 |
| All Sensors | 유지 |
| Sensor Config | 유지 |
| Device Management | 유지 |
| Queue Dashboard | 유지 |
| Latency Dashboard | 유지 |
| Schema Dashboard | 유지 |
| APR Dashboard | 유지 |
| Admin Users/Logs | 유지 |
| Experiment Dashboard | 숨김 또는 연구 기능 섹션으로 이동 |
| Voice Dashboard | 숨김 또는 연구 기능 섹션으로 이동 |

## 14. 1단계 완료 기준

아래 항목이 충족되면 1단계 "제품 범위 고정"은 완료로 본다.

```text
□ 제품명 APR EdgeInsight Industrial IoT Platform v1.0 확정
□ 인증 포함 기능 목록 확정
□ 인증 제외 기능 목록 확정
□ 인증 포함/제외 웹 화면 확정
□ 인증 포함/제외 API 범위 확정
□ 인증 포함/제외 파일 범위 확정
□ 사용자 유형 확정
□ 다음 단계에서 분리/숨김 처리할 연구 기능 식별
```

## 15. 다음 단계 이관 사항

2단계 "제품 구조 정리 및 인증용 배포본 구성"에서 처리할 항목은 다음과 같다.

| 항목 | 작업 |
|---|---|
| 인증 모드 | `CERTIFICATION_MODE=true` 같은 환경변수로 experiment/voice 메뉴 숨김 검토 |
| 설정 분리 | `config.example.json`, `.env.example` 신규 작성 |
| 배포 제외 | 대용량 DB, 로그, 백업, 논문, 발표자료 제외 규칙 작성 |
| 인증 문서 | 제품설명서/사용자취급설명서 목차를 본 범위 정의서 기준으로 작성 |
| 테스트 케이스 | F-001~F-021 기준으로 테스트 케이스 작성 |

