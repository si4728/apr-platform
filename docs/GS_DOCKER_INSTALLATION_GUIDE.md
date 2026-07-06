# GS Certification Docker Installation Guide

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0

## 1. 설치 전 준비

필수 도구:

| 도구 | 권장 |
|---|---|
| Docker Desktop 또는 Docker Engine | 최신 안정 버전 |
| Docker Compose | Docker에 포함된 compose v2 |
| Browser | Chrome 또는 Edge |

## 2. 인증용 실행 절차

PowerShell 기준:

```powershell
cd C:\access\iot
copy .env.example .env.cert
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

상태 확인:

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert ps
docker compose -f docker-compose.cert.yml --env-file .env.cert logs -f iot-dashboard
```

접속:

```text
http://localhost:4728
```

## 3. 기본 계정

초기 DB에 사용자가 없으면 다음 계정이 생성된다.

| 구분 | 기본값 |
|---|---|
| 관리자 | `admin@example.com` |
| 관리자 비밀번호 | `admin1234` |
| 일반 사용자 | `user@example.com` |
| 일반 사용자 비밀번호 | `user1234` |

실제 운영 전에는 `.env.cert`에서 반드시 변경한다.

## 4. 인증용 MQTT broker

인증용 compose는 `mqtt-broker` 서비스를 함께 실행한다.

| 항목 | 값 |
|---|---|
| 컨테이너명 | `apr-cert-mqtt` |
| 내부 주소 | `mqtt-broker:1883` |
| Host port | `${MQTT_PORT:-1883}` |

서버 설정은 `config.example.json`을 컨테이너 내부 `/app/config.json`으로 mount하여 로컬 broker를 사용한다.

## 5. 정상 동작 확인

1. `http://localhost:4728` 접속
2. 관리자 계정으로 로그인
3. `/api/system/status` 확인
4. `/api/broker/status` 확인
5. `/api/db/status` 확인
6. Device Management에서 client package 다운로드
7. PC client 실행
8. Dashboard에서 센서 데이터 수신 확인
9. APR Dashboard에서 정책 추천 확인
10. Dynamic Client Policy Control 확인

## 6. 종료

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down
```

볼륨까지 제거하려면 아래 명령을 사용한다. 시험 데이터가 삭제되므로 주의한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert down -v
```

