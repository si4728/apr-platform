# User Permission Management Implementation

작성일: 2026-06-03

## 1. 적용 범위

`USER_PERMISSION_DB.md`의 MVP 방향에 맞춰 `users.role`과 `users.status` 기반 권한 관리를 추가했다.

적용된 기능:

- 로그인/로그아웃
- 관리자/일반 사용자 역할 분리
- 계정 상태 `ACTIVE` / `SUSPENDED`
- 역할별 메뉴 표시
- 관리자 전용 사용자 관리 화면
- 관리자 전용 접속 로그 / 감사 로그 화면
- 주요 관리 화면/API 접근 차단

## 2. 추가 DB 테이블

### users

사용자 계정 테이블.

| 컬럼 | 설명 |
|---|---|
| `id` | 사용자 ID |
| `name` | 이름 |
| `email` | 로그인 이메일, UNIQUE |
| `password_hash` | 비밀번호 hash |
| `company` | 회사 |
| `phone` | 연락처 |
| `role` | `ADMIN`, `USER` |
| `status` | `ACTIVE`, `SUSPENDED` |
| `created_at` | 생성 시각 |

### access_logs

로그인/로그아웃 이력.

| 컬럼 | 설명 |
|---|---|
| `event_type` | `LOGIN_SUCCESS`, `LOGIN_FAIL`, `LOGOUT` |
| `failure_reason` | 실패 사유 |
| `ip_address` | 접속 IP |
| `user_agent` | client user agent |

### audit_logs

관리자 주요 행위 기록.

현재 기록 action:

- `USER_CREATED`
- `USER_ACTIVATED`
- `USER_SUSPENDED`

## 3. 기본 계정

DB에 사용자가 하나도 없으면 최초 실행 시 기본 계정 2개를 생성한다.

| 역할 | 이메일 | 비밀번호 |
|---|---|---|
| ADMIN | `admin@example.com` | `admin1234` |
| USER | `user@example.com` | `user1234` |

환경변수로 변경 가능:

```text
IOT_ADMIN_EMAIL
IOT_ADMIN_PASSWORD
IOT_USER_EMAIL
IOT_USER_PASSWORD
```

운영 전에는 반드시 기본 비밀번호를 변경하거나 환경변수로 지정해야 한다.

## 4. 추가 화면

| URL | 권한 | 설명 |
|---|---|---|
| `/login` | Public | 로그인 |
| `/logout` | 로그인 사용자 | 로그아웃 |
| `/admin/users` | ADMIN | 사용자 생성/활성/정지 |
| `/admin/access-logs` | ADMIN | 접속 로그 |
| `/admin/audit-logs` | ADMIN | 감사 로그 |

## 5. 추가 API

| API | 권한 | 설명 |
|---|---|---|
| `GET /api/auth/me` | 로그인 사용자 | 현재 로그인 사용자 |
| `POST /api/admin/users` | ADMIN | 사용자 생성 |
| `POST /api/admin/users/<id>/status` | ADMIN | 사용자 활성/정지 |

## 6. 메뉴 권한

공통 메뉴는 `/api/auth/me`로 현재 사용자의 role을 확인한 뒤 표시된다.

일반 사용자 메뉴:

- Telemetry Dashboard
- All Sensors
- Latency Analysis
- Device Edge README

관리자 추가 메뉴:

- Sensor Config
- Queue Monitor
- Experiment Runner
- Schema Intelligence
- APR Dashboard
- Voice Streaming
- Server Operation Manual
- User Management
- Access Logs
- Audit Logs

## 7. 접근 제어 정책

관리자 전용 화면:

```text
/admin/*
/sensor_config
/queue_dashboard
/experiment_dashboard
/schema_dashboard
/apr_dashboard
/voice_dashboard
/server_operation_manual
```

관리자 전용 API:

```text
/api/admin/*
/api/system/shutdown
/api/sensors POST/PUT/DELETE
/api/apr/*
/api/experiment/run
```

일반 사용자는 조회 중심 dashboard와 센서 조회 API를 사용할 수 있다.

## 8. 검증 결과

임시 DB 기반 테스트 결과:

```text
anonymous /              -> 302 /login
admin login              -> 302 /
GET /api/auth/me         -> ADMIN
POST /api/admin/users    -> 200
GET /admin/users         -> 200
USER GET /admin/users    -> 403
USER POST /api/sensors   -> 403
USER GET /api/sensors    -> 200
```

Docker Desktop이 실행 중이 아니어서 컨테이너 재빌드 검증은 수행하지 못했다.

## 9. 향후 개선

운영 적용 전 권장 사항:

1. 기본 계정 비밀번호 변경
2. `FLASK_SECRET_KEY` 환경변수 설정
3. 관리자 비밀번호 변경 UI 추가
4. 사용자 role 변경 UI 추가
5. login lockout 정책 추가
6. API token 또는 CSRF 보호 추가
7. HTTPS/TLS 적용
