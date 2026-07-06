import ast
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_e2e_preflight_report.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_e2e_preflight_report.md"

REQUIRED_ROUTES = {
    "TC-INST-003": ["/login", "/"],
    "TC-USER-001": ["/login", "/api/auth/me"],
    "TC-DEV-001": ["/api/fleets"],
    "TC-DEV-002": ["/api/devices"],
    "TC-DEV-003": ["/api/devices/<int:row_id>/client-package"],
    "TC-MON-001": ["/api/system/status"],
    "TC-MON-002": ["/api/broker/status"],
    "TC-MON-003": ["/api/queue-stats", "/api/topic-rate", "/api/backlog-estimation"],
    "TC-APR-001": ["/api/apr/recommend"],
    "TC-APR-002": ["/api/devices/<int:row_id>/policy/apply", "/api/fleets/<int:fleet_id>/policy/apply"],
    "TC-APR-003": ["/api/devices/<int:row_id>/policy/apply"],
    "TC-APR-004": ["/api/devices/<int:row_id>/policy/apply"],
    "TC-EVID-001": [],
    "TC-ERR-001": ["/api/broker/status"],
    "TC-ERR-003": ["/api/db/status", "/api/system/status"],
}

REQUIRED_CLIENT_FILES = {
    "windows_pc": [
        "client.config",
        "pc_test_publisher.py",
        "run_pc_test_publisher.bat",
        "START_HERE.txt",
    ],
    "raspberry_pi": [
        "client.config",
        "system_metrics.config",
        "raspi_iot_publisher.py",
        "raspi_system_metrics_publisher.py",
        "run_raspi_client.sh",
        "run_raspi_system_metrics.sh",
        "START_HERE.txt",
    ],
    "ubuntu_linux": [
        "client.config",
        "pc_test_publisher.py",
        "run_pc_test_publisher.sh",
        "START_HERE.txt",
    ],
}

STATIC_REQUIRED_FILES = [
    "Dockerfile",
    "docker-compose.cert.yml",
    "config.example.json",
    ".env.example",
    "server.py",
    "tools/check_certification_config.py",
    "tools/generate_gs_evidence_report.py",
    "tools/build_gs_submission_package.py",
]

DOC_REQUIRED_FILES = [
    "docs/GS_PRODUCT_DESCRIPTION_KO.md",
    "docs/GS_INTEGRATED_TEST_CASES.md",
    "docs/GS_SUBMISSION_PACKAGE_CHECKLIST.md",
    "docs/GS_SUBMISSION_PACKAGE_BUILD_GUIDE.md",
    "docs/GS_USER_OPERATION_MANUAL_KO.md",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def file_status(path):
    p = PROJECT_ROOT / path
    return {
        "path": path,
        "exists": p.exists(),
        "size_bytes": p.stat().st_size if p.exists() else 0,
    }


def extract_routes():
    server_path = PROJECT_ROOT / "server.py"
    tree = ast.parse(server_path.read_text(encoding="utf-8"))
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            is_route = False
            if isinstance(func, ast.Attribute) and func.attr == "route":
                is_route = True
            if not is_route or not decorator.args:
                continue
            route_arg = decorator.args[0]
            if isinstance(route_arg, ast.Constant) and isinstance(route_arg.value, str):
                methods = ["GET"]
                for keyword in decorator.keywords:
                    if keyword.arg == "methods" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                        methods = [item.value for item in keyword.value.elts if isinstance(item, ast.Constant)]
                routes.append({"route": route_arg.value, "methods": methods, "function": node.name})
    return routes


def route_exists(routes, route):
    return any(item["route"] == route for item in routes)


def check_routes(routes):
    checks = []
    for tc_id, required in REQUIRED_ROUTES.items():
        missing = [route for route in required if not route_exists(routes, route)]
        checks.append({
            "tc_id": tc_id,
            "ok": not missing,
            "required_routes": required,
            "missing_routes": missing,
        })
    return checks


def extract_literal_tuple(source, name):
    pattern = rf"{re.escape(name)}\s*=\s*\((.*?)\)"
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        return []
    return re.findall(r'[\"\']([^\"\']+)[\"\']', match.group(1))


def extract_client_file_mappings():
    source = (PROJECT_ROOT / "server.py").read_text(encoding="utf-8")
    common = extract_literal_tuple(source, "COMMON_CLIENT_PACKAGE_FILES")
    tree = ast.parse(source)
    mapping = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OS_CLIENT_PACKAGE_FILES":
                    if isinstance(node.value, ast.Dict):
                        for key_node, value_node in zip(node.value.keys, node.value.values):
                            if isinstance(key_node, ast.Constant) and isinstance(value_node, (ast.List, ast.Tuple)):
                                mapping[key_node.value] = [
                                    item.value for item in value_node.elts if isinstance(item, ast.Constant)
                                ]
    return common, mapping


def check_client_packages():
    common, mapping = extract_client_file_mappings()
    checks = []
    device_dir = PROJECT_ROOT / "device"
    for os_name, required_files in REQUIRED_CLIENT_FILES.items():
        configured = list(common) + list(mapping.get(os_name, []))
        configured_with_generated = configured + ["client.config", "START_HERE.txt"]
        if os_name == "raspberry_pi":
            configured_with_generated.append("system_metrics.config")
        missing_from_mapping = [name for name in required_files if name not in configured_with_generated]
        missing_on_disk = [
            name for name in configured
            if not (device_dir / name).exists()
        ]
        checks.append({
            "device_os": os_name,
            "ok": not missing_from_mapping and not missing_on_disk,
            "configured_files": configured,
            "required_files": required_files,
            "missing_from_mapping": missing_from_mapping,
            "missing_on_disk": missing_on_disk,
        })
    return checks


def check_config_templates():
    env_text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    compose_text = (PROJECT_ROOT / "docker-compose.cert.yml").read_text(encoding="utf-8")
    config_text = (PROJECT_ROOT / "config.example.json").read_text(encoding="utf-8")
    config_json = json.loads(config_text)
    checks = [
        {
            "name": ".env.example placeholders",
            "ok": all(token in env_text for token in ["CHANGE_ME_ADMIN_PASSWORD", "CHANGE_ME_USER_PASSWORD", "CHANGE_ME_32_CHAR_FLASK_SECRET_FOR_CERT", "CHANGE_ME_32_HEX_CHAR_AES_KEY_NO_QUOTES"]),
        },
        {
            "name": "compose requires secrets",
            "ok": all(token in compose_text for token in ["IOT_ADMIN_PASSWORD:?", "IOT_USER_PASSWORD:?", "FLASK_SECRET_KEY:?", "APR_AES_KEY_HEX:?"]),
        },
        {
            "name": "cert config mqtt broker",
            "ok": config_json.get("mqtt", {}).get("broker") == "mqtt-broker",
        },
        {
            "name": "cert config APR enabled",
            "ok": bool(config_json.get("platform", {}).get("enable_apr")),
        },
    ]
    return checks


def build_markdown(report):
    lines = [
        "# GS E2E Preflight Report",
        "",
        f"Generated at: {report['generated_at']}",
        f"Overall status: **{report['overall_status']}**",
        "",
        "## Route Coverage",
        "",
        "| TC ID | OK | Missing Routes |",
        "|---|---:|---|",
    ]
    for item in report["route_checks"]:
        lines.append(f"| {item['tc_id']} | {item['ok']} | {', '.join(item['missing_routes'])} |")
    lines.extend(["", "## Client Package Readiness", "", "| Device OS | OK | Missing Mapping | Missing Files |", "|---|---:|---|---|"])
    for item in report["client_package_checks"]:
        lines.append(f"| {item['device_os']} | {item['ok']} | {', '.join(item['missing_from_mapping'])} | {', '.join(item['missing_on_disk'])} |")
    lines.extend(["", "## Config Template Checks", "", "| Check | OK |", "|---|---:|"])
    for item in report["config_template_checks"]:
        lines.append(f"| {item['name']} | {item['ok']} |")
    lines.extend(["", "## Required Files", "", "| Path | Exists | Size |", "|---|---:|---:|"])
    for item in report["required_files"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.extend(["", "## Required Documents", "", "| Path | Exists | Size |", "|---|---:|---:|"])
    for item in report["required_documents"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.append("")
    return "\n".join(lines)


def main():
    routes = extract_routes()
    route_checks = check_routes(routes)
    client_checks = check_client_packages()
    config_checks = check_config_templates()
    required_files = [file_status(path) for path in STATIC_REQUIRED_FILES]
    required_documents = [file_status(path) for path in DOC_REQUIRED_FILES]

    all_ok = all(item["ok"] for item in route_checks)
    all_ok = all_ok and all(item["ok"] for item in client_checks)
    all_ok = all_ok and all(item["ok"] for item in config_checks)
    all_ok = all_ok and all(item["exists"] and item["size_bytes"] > 0 for item in required_files)
    all_ok = all_ok and all(item["exists"] and item["size_bytes"] > 0 for item in required_documents)

    report = {
        "generated_at": now_iso(),
        "overall_status": "ok" if all_ok else "attention_required",
        "route_count": len(routes),
        "route_checks": route_checks,
        "client_package_checks": client_checks,
        "config_template_checks": config_checks,
        "required_files": required_files,
        "required_documents": required_documents,
        "notes": [
            "This is a static E2E preflight report. It does not start Docker containers or send network traffic.",
            "Use the generated checks before running live Docker E2E evidence collection.",
        ],
    }

    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    DEFAULT_MARKDOWN.write_text(build_markdown(report), encoding="utf-8")

    print(json.dumps({
        "status": report["overall_status"],
        "json_report": str(DEFAULT_OUTPUT),
        "markdown_report": str(DEFAULT_MARKDOWN),
        "route_count": len(routes),
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())