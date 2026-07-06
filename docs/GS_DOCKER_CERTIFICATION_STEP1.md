# GS Certification Docker Baseline - Step 1

작성일: 2026-07-06  
대상 제품명: APR EdgeInsight Industrial IoT Platform v1.0  
단계 목표: GS 인증 기준 실행환경을 Docker 기반으로 확정하고, 현재 Docker 구성과 보완 필요 항목을 정의한다.

## 1. 결론

GS 인증 준비 기준 실행환경은 Docker 기반으로 확정한다.

```text
Primary certification runtime: Docker
Secondary runtime: Windows/Python venv
Edge client runtime: PC, Raspberry Pi, Ubuntu/Linux
```

Docker 기준 실행환경을 채택하는 이유는 다음과 같다.

| 항목 | 기대 효과 |
|---|---|
| 설치 재현성 | 시험기관이 동일한 절차로 서버를 실행 가능 |
| 의존성 고정 | Python, package, OS dependency 차이 최소화 |
| 시험 편의성 | `docker compose up -d --build` 중심의 단순 실행 절차 제공 |
| 환경 격리 | DB, runtime lock, 설정 파일, 로그 경로를 명확히 분리 |
| 문서화 용이성 | 설치 매뉴얼과 테스트 케이스를 Docker 기준으로 표준화 |
| 장애 감소 | 로컬 Python 환경 차이로 인한 실행 실패 가능성 감소 |

단, Docker만 유일한 실행 방식으로 제한하지 않는다. Windows/Python 직접 실행은 보조 실행환경으로 유지한다.

## 2. 현재 Docker 구성 진단

현재 저장소에는 다음 Docker 파일이 존재한다.

| 파일 | 현재 역할 |
|---|---|
| `Dockerfile` | Python 3.11 slim 기반 서버 이미지 생성 |
| `docker-compose.yml` | `iot-dashboard` 단일 서비스 실행 |
| `README_DOCKER_DESKTOP.md` | Docker Desktop 실행 안내 |

현재 `Dockerfile` 주요 내용:

```text
FROM python:3.11-slim
WORKDIR /app
pip install -r requirements.txt
COPY . .
EXPOSE 4728
CMD ["python", "server.py"]
```

현재 `docker-compose.yml` 주요 내용:

| 항목 | 현재 값 |
|---|---|
| 서비스명 | `iot-dashboard` |
| 포트 | `4728:4728` |
| DB 경로 | `./iot_data.db:/app/iot_data.db` |
| 설정 파일 | `./config.json:/app/config.json:ro` |
| Runtime lock | `./runtime:/app/runtime` |
| 결과 폴더 | `./experiment_results:/app/experiment_results` |
| Healthcheck | `http://127.0.0.1:4728/` 접속 확인 |

## 3. GS 인증 관점의 현재 위험 요소

| 위험 요소 | 설명 | 개선 방향 |
|---|---|---|
| 외부 MQTT broker 의존 | 현재 `config.json`은 `218.146.225.166:1883`에 의존 | 인증용 로컬 Mosquitto broker 구성 검토 |
| 운영 DB bind mount | 현재 운영 `iot_data.db`를 직접 container에 mount | 인증용 sample DB 또는 Docker volume 분리 |
| 실제 설정 파일 사용 | `config.json`에 운영 broker 정보가 포함 | `config.example.json`과 `.env.example` 분리 |
| 실험 결과 폴더 mount | `experiment_results`는 인증 핵심 범위가 아님 | 인증용 compose에서는 제외 또는 별도 optional 처리 |
| 인증 모드 부재 | 인증 제외 메뉴와 기능 노출 제어가 아직 없음 | `CERTIFICATION_MODE=true` 도입 |
| 초기 관리자 절차 불명확 | 시험기관이 로그인할 계정 생성 절차 필요 | 초기 관리자 생성/샘플 계정 절차 문서화 |
| secret 관리 미흡 | AES key, MQTT credential 기본값 관리 필요 | 환경변수와 보안 가이드로 분리 |

## 4. 인증 기준 Docker 실행 방침

GS 인증 제출 기준 실행은 다음과 같이 정의한다.

| 구분 | 기준 |
|---|---|
| 권장 실행 방식 | Docker compose |
| 기준 compose 파일 | `docker-compose.cert.yml` 신규 작성 예정 |
| 기준 설정 파일 | `config.example.json` 신규 작성 예정 |
| 기준 환경변수 | `.env.example` 신규 작성 예정 |
| MQTT broker | 인증용 로컬 broker 포함 검토 |
| DB | 인증용 Docker volume 또는 sample DB 사용 |
| 인증 모드 | `CERTIFICATION_MODE=true` |
| 접속 URL | `http://localhost:4728` |

권장 인증 실행 명령은 다음 형태로 고정한다.

```powershell
docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
```

단계 2에서 실제 파일을 추가할 때 `.env.cert`는 제출 패키지에 포함하지 않고, `.env.example`을 복사해 생성하는 방식으로 안내한다.

## 5. Docker 기준 인증 테스트 흐름

Docker 기준 시험 흐름은 다음으로 고정한다.

```text
1. 인증용 package 압축 해제
2. .env.example을 .env.cert로 복사
3. config.example.json을 config.json 또는 config.cert.json으로 복사
4. docker compose -f docker-compose.cert.yml --env-file .env.cert up -d --build
5. http://localhost:4728 접속
6. 로그인 또는 초기 관리자 생성
7. PC client package 생성
8. PC client publish 실행
9. Dashboard에서 수신 데이터 확인
10. APR 정책 추천 실행
11. Dynamic Client Policy Control 실행
12. Client Runtime Configuration Update 실행
13. APR 모델 학습 자동화 절차 실행 또는 점검
14. Queue/Latency/Schema/Broker/DB 상태 확인
```

## 6. 1단계 산출 기준

1단계 완료 기준은 다음과 같다.

```text
□ Docker를 GS 인증 기준 실행환경으로 확정
□ Windows/Python 직접 실행은 보조 방식으로 유지
□ 현재 Docker 구성의 위험 요소 식별
□ 인증용 Docker compose 신규 작성 필요성 확정
□ 로컬 MQTT broker 포함 필요성 검토 항목으로 확정
□ 설정 파일과 secret 분리 필요성 확정
□ 인증 모드 도입 필요성 확정
```

## 7. 2단계 이관 작업

다음 단계에서는 실제 인증용 Docker 실행 파일을 만든다.

| 작업 | 산출물 |
|---|---|
| 인증용 compose 작성 | `docker-compose.cert.yml` |
| 인증용 설정 예시 작성 | `config.example.json` |
| 환경변수 예시 작성 | `.env.example` |
| Mosquitto 설정 검토 | `mosquitto/config/mosquitto.conf` 또는 compose inline 설정 |
| 인증 모드 환경변수 반영 | `CERTIFICATION_MODE=true` |
| 운영 DB와 sample DB 분리 | Docker volume 또는 `sample_data/` |
| 설치 절차 문서화 | `docs/GS_DOCKER_INSTALLATION_GUIDE.md` |

## 8. 운영 원칙

Docker 인증 기준을 도입해도 기존 기능과 프로세스는 삭제하지 않는다.

| 기능 | 처리 방침 |
|---|---|
| Voice streaming | code/process 유지, 인증 범위 제외 |
| 범용 experiment | code/process 유지, 인증 모드에서는 노출 제한 |
| APR 모델 학습 자동화 | 인증 범위 포함 |
| Dynamic client policy 변경 | 인증 범위 포함 |
| Client runtime option 변경 | 인증 범위 포함 |

