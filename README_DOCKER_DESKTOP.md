# Windows Docker Desktop 운영

이 폴더는 Windows Docker Desktop의 Linux 컨테이너에서 바로 실행할 수 있습니다.

## 실행

PowerShell을 관리자 권한으로 열고:

```powershell
cd C:\access\iot
.\run_dashboard_docker_desktop.ps1
```

또는 직접 실행:

```powershell
cd C:\access\iot
docker compose up -d --build
```

## 접속

```text
http://localhost:5000
```

## 상태 확인

```powershell
docker ps
docker logs -f iot-dashboard
docker inspect --format='{{json .State.Health}}' iot-dashboard
```

## 종료

```powershell
docker stop iot-dashboard
```

완전히 compose 기준으로 내리려면:

```powershell
docker compose down
```

## 현재 설정

- 대시보드 포트: `5000`
- MQTT 서버: `config.json`의 `218.146.225.166:1883`
- DB 파일: `C:\access\iot\iot_data.db`를 컨테이너 `/app/iot_data.db`로 연결
- 설정 파일: `C:\access\iot\config.json`를 컨테이너 `/app/config.json`로 읽기 전용 연결
- 결과 폴더: `C:\access\iot\experiment_results`를 컨테이너 `/app/experiment_results`로 연결
