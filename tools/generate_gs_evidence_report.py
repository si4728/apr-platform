import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "gs_certification_evidence"
DEFAULT_REPORT_JSON = "gs_evidence_report.json"
DEFAULT_REPORT_MD = "gs_evidence_report.md"

REQUIRED_DOCUMENTS = [
    "docs/GS_CERTIFICATION_SCOPE_V1.md",
    "docs/GS_PRODUCT_DESCRIPTION_KO.md",
    "docs/GS_APPLICATION_SUMMARY_KO.md",
    "docs/GS_INTEGRATED_TEST_CASES.md",
    "docs/GS_SUBMISSION_PACKAGE_CHECKLIST.md",
    "docs/GS_DOCKER_INSTALLATION_GUIDE.md",
    "docs/GS_RELEASE_PACKAGE_STRUCTURE.md",
    "docs/GS_APR_MODEL_TRAINING_AUTOMATION.md",
    "docs/GS_APR_MODEL_TEST_CASES.md",
    "docs/GS_SECURITY_CONFIGURATION_GUIDE.md",
    "docs/GS_SECURITY_TEST_CASES.md",
    "docs/USER_MANUAL_KO.md",
    "docs/GS_USER_OPERATION_MANUAL_KO.md",
]

REQUIRED_RUNTIME_FILES = [
    "Dockerfile",
    "docker-compose.cert.yml",
    "config.example.json",
    ".env.example",
    "requirements.txt",
    "server.py",
    "tools/check_certification_config.py",
    "tools/run_apr_model_automation.py",
    "tools/build_gs_submission_package.py",
    "tools/generate_gs_e2e_preflight_report.py",
    "tools/generate_gs_readiness_review.py",
    "tools/generate_gs_live_e2e_report.py",
]

SECRET_KEYS = {
    "FLASK_SECRET_KEY",
    "IOT_ADMIN_PASSWORD",
    "IOT_USER_PASSWORD",
    "APR_AES_KEY_HEX",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def run_command(args, timeout=120, env=None):
    started_at = now_iso()
    try:
        completed = subprocess.run(
            args,
            cwd=str(PROJECT_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )
        return {
            "command": args,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": completed.returncode,
            "ok": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {
            "command": args,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": None,
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": args,
            "started_at": started_at,
            "finished_at": now_iso(),
            "returncode": None,
            "ok": False,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
        }


def parse_json_stdout(step):
    if not step.get("stdout"):
        return None
    try:
        return json.loads(step["stdout"])
    except json.JSONDecodeError:
        return None


def file_status(paths):
    result = []
    for item in paths:
        path = PROJECT_ROOT / item
        result.append({
            "path": item,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None,
        })
    return result


def parse_env_file(path):
    values = {}
    if not path:
        return values
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = PROJECT_ROOT / env_path
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def sanitized_env_summary(env_file):
    values = parse_env_file(env_file)
    summary = {}
    for key in sorted(values):
        value = values[key]
        if key in SECRET_KEYS:
            summary[key] = {
                "configured": bool(value),
                "masked": "***" if value else "",
                "length": len(value),
            }
        else:
            summary[key] = value
    return summary


def build_markdown(report):
    lines = []
    lines.append("# GS Certification Integrated Evidence Report")
    lines.append("")
    lines.append(f"Generated at: {report['generated_at']}")
    lines.append(f"Product: {report['product']['name']}")
    lines.append(f"Version: {report['product']['version']}")
    lines.append(f"Overall status: **{report['overall_status']}**")
    lines.append("")

    lines.append("## 1. Execution Environment")
    lines.append("")
    env_info = report["environment"]
    lines.append(f"- Python: `{env_info['python']}`")
    lines.append(f"- Platform: `{env_info['platform']}`")
    lines.append(f"- Project root: `{env_info['project_root']}`")
    lines.append("")

    lines.append("## 2. Required Files")
    lines.append("")
    lines.append("| Path | Exists | Size |")
    lines.append("|---|---:|---:|")
    for item in report["required_files"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.append("")

    lines.append("## 3. Required Documents")
    lines.append("")
    lines.append("| Path | Exists | Size |")
    lines.append("|---|---:|---:|")
    for item in report["required_documents"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.append("")

    lines.append("## 4. Validation Steps")
    lines.append("")
    lines.append("| Step | Status | Return Code | Notes |")
    lines.append("|---|---:|---:|---|")
    for name, step in report["validation_steps"].items():
        note = step.get("summary") or step.get("stderr") or ""
        note = note.replace("\n", " ")[:180]
        lines.append(f"| {name} | {step.get('status', 'unknown')} | {step.get('returncode')} | {note} |")
    lines.append("")

    lines.append("## 5. Security Configuration")
    lines.append("")
    security = report["security_configuration"]
    lines.append(f"Security status: **{security.get('status')}**")
    if security.get("checks"):
        lines.append("")
        lines.append("| Check | OK | Message |")
        lines.append("|---|---:|---|")
        for item in security["checks"]:
            lines.append(f"| {item['name']} | {item['ok']} | {item['message']} |")
    lines.append("")

    lines.append("## 6. APR Model Automation")
    lines.append("")
    apr = report["apr_model_automation"]
    lines.append(f"APR automation status: **{apr.get('status')}**")
    lines.append(f"Report file: `{apr.get('report_file')}`")
    lines.append("")

    lines.append("## 7. Output Files")
    lines.append("")
    for item in report["output_files"]:
        lines.append(f"- `{item}`")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate integrated GS certification evidence report.")
    parser.add_argument("--env-file", default=".env.example", help="Certification env file to validate.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for report outputs.")
    parser.add_argument("--compose-file", default="docker-compose.cert.yml", help="Certification Docker compose file.")
    parser.add_argument("--skip-apr-export", action="store_true", help="Skip APR runtime export during APR evidence generation.")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds for subprocess checks.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = PROJECT_ROOT / env_file

    validation_steps = {}

    py_compile = run_command([
        sys.executable,
        "-m",
        "py_compile",
        "server.py",
        "tools/check_certification_config.py",
        "tools/run_apr_model_automation.py",
    ], timeout=args.timeout)
    py_compile["status"] = "ok" if py_compile["ok"] else "failed"
    validation_steps["python_compile"] = py_compile

    security_step = run_command([
        sys.executable,
        "tools/check_certification_config.py",
        "--env-file",
        rel(env_file),
        "--json",
    ], timeout=args.timeout)
    security_json = parse_json_stdout(security_step) or {"status": "failed", "checks": []}
    security_step["status"] = security_json.get("status", "failed")
    security_step["summary"] = f"security checks: {security_step['status']}"
    validation_steps["security_configuration"] = security_step

    compose_step = run_command([
        "docker",
        "compose",
        "-f",
        args.compose_file,
        "--env-file",
        rel(env_file),
        "config",
        "--quiet",
    ], timeout=args.timeout)
    compose_step["status"] = "ok" if compose_step["ok"] else "failed"
    if "Error loading config file" in compose_step.get("stderr", "") and compose_step["ok"]:
        compose_step["summary"] = "compose config valid; Docker config access warning observed"
    validation_steps["docker_compose_config"] = compose_step

    apr_report_path = output_dir / "apr_model_automation_report.json"
    apr_args = [
        sys.executable,
        "tools/run_apr_model_automation.py",
        "--report",
        str(apr_report_path),
        "--timeout",
        str(args.timeout),
    ]
    if args.skip_apr_export:
        apr_args.insert(2, "--skip-export")
    apr_step = run_command(apr_args, timeout=args.timeout + 30)
    apr_json = parse_json_stdout(apr_step) or {"status": "failed"}
    apr_step["status"] = apr_json.get("status", "failed")
    apr_step["summary"] = f"APR model automation: {apr_step['status']}"
    validation_steps["apr_model_automation"] = apr_step

    required_files = file_status(REQUIRED_RUNTIME_FILES)
    required_documents = file_status(REQUIRED_DOCUMENTS)
    files_ok = all(item["exists"] and item["size_bytes"] > 0 for item in required_files)
    docs_ok = all(item["exists"] and item["size_bytes"] > 0 for item in required_documents)
    steps_ok = all(step.get("status") == "ok" for step in validation_steps.values())

    if files_ok and docs_ok and steps_ok:
        overall_status = "ok"
    elif files_ok and docs_ok:
        overall_status = "attention_required"
    else:
        overall_status = "failed"

    report = {
        "generated_at": now_iso(),
        "product": {
            "name": "APR EdgeInsight Industrial IoT Platform",
            "version": "v1.0",
            "certification_scope": "GS certification operational scope",
        },
        "overall_status": overall_status,
        "environment": {
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "project_root": str(PROJECT_ROOT),
        },
        "env_file": rel(env_file),
        "env_summary": sanitized_env_summary(env_file),
        "required_files": required_files,
        "required_documents": required_documents,
        "validation_steps": validation_steps,
        "security_configuration": security_json,
        "apr_model_automation": {
            "status": apr_json.get("status", "failed"),
            "report_file": rel(apr_report_path),
            "summary": apr_json,
        },
        "output_files": [],
    }

    json_path = output_dir / DEFAULT_REPORT_JSON
    md_path = output_dir / DEFAULT_REPORT_MD
    report["output_files"] = [rel(json_path), rel(md_path), rel(apr_report_path)]
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(report), encoding="utf-8")

    print(json.dumps({
        "status": overall_status,
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "apr_report": str(apr_report_path),
    }, ensure_ascii=False, indent=2))
    return 0 if overall_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())