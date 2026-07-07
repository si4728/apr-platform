import argparse
import json
import secrets
import http.cookiejar
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_live_e2e_report.json"
OUTPUT_MD = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_live_e2e_report.md"
TEMP_ENV_FILE = PROJECT_ROOT / "runtime" / "gs_live_e2e.env"
COMPOSE_FILE = "docker-compose.cert.yml"
DEFAULT_PORT = 4728
SECRET_KEYS = {"IOT_ADMIN_PASSWORD", "IOT_USER_PASSWORD", "FLASK_SECRET_KEY", "APR_AES_KEY_HEX"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def run_command(args, timeout=120):
    started_at = now_iso()
    try:
        completed = subprocess.run(
            args,
            cwd=str(PROJECT_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        return {
            "command": args,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": completed.returncode,
            "ok": completed.returncode == 0,
            "stdout": (completed.stdout or "").strip()[-4000:],
            "stderr": (completed.stderr or "").strip()[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": args,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": None,
            "ok": False,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
        }


def write_temp_env(path, port):
    values = {
        "TZ": "Asia/Seoul",
        "PORT": str(port),
        "CERTIFICATION_MODE": "true",
        "DB_NAME": "/app/data/iot_data.db",
        "DB_JOURNAL_MODE": "WAL",
        "DB_LOCK_RETRIES": "10",
        "DB_BUSY_TIMEOUT_MS": "30000",
        "SYSTEM_MODE": "docker-cert-live-e2e",
        "SYSTEM_LOCK_FILE": "/app/runtime/iot_dashboard.lock",
        "SYSTEM_LOCK_STALE_SECONDS": "30",
        "IOT_ADMIN_EMAIL": "admin@example.com",
        "IOT_ADMIN_PASSWORD": "LiveAdmin-" + secrets.token_urlsafe(12),
        "IOT_USER_EMAIL": "user@example.com",
        "IOT_USER_PASSWORD": "LiveUser-" + secrets.token_urlsafe(12),
        "FLASK_SECRET_KEY": "live-e2e-" + secrets.token_urlsafe(32),
        "APR_AES_KEY_HEX": secrets.token_hex(16),
        "MQTT_BROKER": "mqtt-broker",
        "MQTT_PORT": "1883",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    return values


def mask_env(values):
    masked = {}
    for key, value in values.items():
        if key in SECRET_KEYS:
            masked[key] = {"configured": bool(value), "length": len(value), "masked": "***"}
        else:
            masked[key] = value
    return masked


def read_env(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def make_session_opener():
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def login_session(opener, base_url, email, password):
    data = urllib.parse.urlencode({"email": email, "password": password, "next": "/"}).encode("utf-8")
    request = urllib.request.Request(base_url + "/login", data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    started_at = now_iso()
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": response.status in (200, 302), "status_code": response.status, "started_at": started_at, "finished_at": now_iso(), "body_preview": body[:300]}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return {"ok": False, "status_code": exc.code, "started_at": started_at, "finished_at": now_iso(), "error": body[:500]}
    except Exception as exc:
        return {"ok": False, "status_code": None, "started_at": started_at, "finished_at": now_iso(), "error": str(exc)}


def http_get_json(url, timeout=5, opener=None):
    started_at = now_iso()
    try:
        open_fn = opener.open if opener else urllib.request.urlopen
        with open_fn(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = None
            return {
                "url": url,
                "started_at": started_at,
                "finished_at": now_iso(),
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "json": parsed,
                "body_preview": body[:1000] if parsed is None else None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return {
            "url": url,
            "started_at": started_at,
            "finished_at": now_iso(),
            "ok": False,
            "status_code": exc.code,
            "error": body[:1000],
        }
    except Exception as exc:
        return {
            "url": url,
            "started_at": started_at,
            "finished_at": now_iso(),
            "ok": False,
            "status_code": None,
            "error": str(exc),
        }


def wait_http(url, seconds):
    deadline = time.time() + seconds
    attempts = []
    while time.time() < deadline:
        result = http_get_json(url, timeout=5)
        attempts.append(result)
        if result.get("ok"):
            return {"ok": True, "attempts": attempts, "last": result}
        time.sleep(3)
    return {"ok": False, "attempts": attempts, "last": attempts[-1] if attempts else None}


def docker_compose_args(env_file):
    return ["docker", "compose", "-f", COMPOSE_FILE, "--env-file", str(env_file)]


def build_markdown(report):
    lines = [
        "# GS Docker Live E2E Report",
        "",
        f"Generated at: {report['generated_at']}",
        f"Overall status: **{report['overall_status']}**",
        f"Env file: `{report['env_file']}`",
        "",
        "## Steps",
        "",
        "| Step | OK | Return Code |",
        "|---|---:|---:|",
    ]
    for name, step in report["steps"].items():
        lines.append(f"| {name} | {step.get('ok')} | {step.get('returncode')} |")
    lines.extend(["", "## HTTP Checks", "", "| Endpoint | OK | Status |", "|---|---:|---:|"])
    for name, item in report["http_checks"].items():
        lines.append(f"| {name} | {item.get('ok')} | {item.get('status_code')} |")
    lines.extend(["", "## Container Checks", "", "| Check | OK |", "|---|---:|"])
    for name, item in report["container_checks"].items():
        lines.append(f"| {name} | {item.get('ok')} |")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run Docker-based GS Live E2E evidence collection.")
    parser.add_argument("--env-file", help="Existing .env.cert-compatible file. If omitted, a temp runtime env is generated.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--keep-running", action="store_true", help="Do not run docker compose down after checks.")
    parser.add_argument("--no-build", action="store_true", help="Use docker compose up -d without --build.")
    args = parser.parse_args()

    generated_env = False
    if args.env_file:
        env_file = Path(args.env_file)
        if not env_file.is_absolute():
            env_file = PROJECT_ROOT / env_file
        env_values = read_env(env_file)
    else:
        env_file = TEMP_ENV_FILE
        env_values = write_temp_env(env_file, args.port)
        generated_env = True

    base_url = f"http://127.0.0.1:{args.port}"
    steps = {}
    container_checks = {}
    http_checks = {}

    compose = docker_compose_args(env_file)
    steps["security_config"] = run_command([
        "python", "tools/check_certification_config.py", "--env-file", rel(env_file)
    ], timeout=60)
    steps["compose_config"] = run_command(compose + ["config", "--quiet"], timeout=60)
    up_args = compose + ["up", "-d"]
    if not args.no_build:
        up_args.append("--build")
    steps["compose_up"] = run_command(up_args, timeout=args.timeout)

    if steps["compose_up"].get("ok"):
        web_wait = wait_http(base_url + "/", args.timeout)
        http_checks["web_root"] = web_wait.get("last") or {"ok": False}
        container_checks["web_root_wait"] = {"ok": web_wait.get("ok"), "attempt_count": len(web_wait.get("attempts", []))}
        opener = make_session_opener()
        http_checks["login"] = login_session(opener, base_url, env_values.get("IOT_ADMIN_EMAIL", ""), env_values.get("IOT_ADMIN_PASSWORD", ""))
        steps["compose_ps"] = run_command(compose + ["ps"], timeout=60)
        steps["dashboard_logs_tail"] = run_command(compose + ["logs", "--tail", "80", "iot-dashboard"], timeout=60)
        for name, path in {
            "system_status": "/api/system/status",
            "broker_status": "/api/broker/status",
            "db_status": "/api/db/status",
        }.items():
            http_checks[name] = http_get_json(base_url + path, timeout=10, opener=opener)
    else:
        steps["compose_ps"] = run_command(compose + ["ps"], timeout=60)

    if not args.keep_running:
        steps["compose_down"] = run_command(compose + ["down"], timeout=120)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": now_iso(),
        "overall_status": "unknown",
        "env_file": rel(env_file),
        "generated_env": generated_env,
        "env_summary": mask_env(env_values),
        "steps": steps,
        "container_checks": container_checks,
        "http_checks": http_checks,
        "notes": [
            "This report is generated from a live Docker compose execution.",
            "Secret values are masked and are not written to the report.",
        ],
    }

    required_steps = ["security_config", "compose_config", "compose_up"]
    if not args.keep_running:
        required_steps.append("compose_down")
    steps_ok = all(steps.get(name, {}).get("ok") for name in required_steps)
    http_ok = all(item.get("ok") for item in http_checks.values()) and bool(http_checks)
    wait_ok = container_checks.get("web_root_wait", {}).get("ok", False)
    report["overall_status"] = "ok" if steps_ok and http_ok and wait_ok else "failed"

    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(report), encoding="utf-8")

    print(json.dumps({
        "status": report["overall_status"],
        "json_report": str(OUTPUT_JSON),
        "markdown_report": str(OUTPUT_MD),
        "env_file": str(env_file),
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())