Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$DockerConfig = Join-Path $ProjectRoot ".docker-cli-config"
if (!(Test-Path $DockerConfig)) {
    New-Item -ItemType Directory -Path $DockerConfig | Out-Null
}

$DockerConfigFile = Join-Path $DockerConfig "config.json"
if (!(Test-Path $DockerConfigFile)) {
    Set-Content -Path $DockerConfigFile -Value "{}" -Encoding UTF8
}

$env:DOCKER_CONFIG = $DockerConfig

docker compose up -d --build
docker ps --filter "name=iot-dashboard"

Write-Host ""
Write-Host "Dashboard: http://localhost:5000"
Write-Host "Logs:      docker logs -f iot-dashboard"
