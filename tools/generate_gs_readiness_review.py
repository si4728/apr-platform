import json
import re
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_readiness_review.json"
OUTPUT_MD = PROJECT_ROOT / "runtime" / "gs_certification_evidence" / "gs_readiness_review.md"

CORE_DOCUMENTS = [
    "docs/GS_CERTIFICATION_SCOPE_V1.md",
    "docs/GS_PRODUCT_DESCRIPTION_KO.md",
    "docs/GS_APPLICATION_SUMMARY_KO.md",
    "docs/GS_PRECONSULTATION_ONE_PAGER_KO.md",
    "docs/GS_DEMO_SCENARIO_KO.md",
    "docs/GS_USER_OPERATION_MANUAL_KO.md",
    "docs/GS_INTEGRATED_TEST_CASES.md",
    "docs/GS_SUBMISSION_PACKAGE_CHECKLIST.md",
]

SUPPORT_DOCUMENTS = [
    "docs/GS_DOCKER_INSTALLATION_GUIDE.md",
    "docs/GS_RELEASE_PACKAGE_STRUCTURE.md",
    "docs/GS_SECURITY_CONFIGURATION_GUIDE.md",
    "docs/GS_SECURITY_TEST_CASES.md",
    "docs/GS_APR_MODEL_TRAINING_AUTOMATION.md",
    "docs/GS_APR_MODEL_TEST_CASES.md",
    "docs/GS_INTEGRATED_EVIDENCE_REPORT_GUIDE.md",
    "docs/GS_SUBMISSION_PACKAGE_BUILD_GUIDE.md",
    "docs/GS_E2E_PREFLIGHT_GUIDE.md",
]

REQUIRED_TOOLS = [
    "tools/check_certification_config.py",
    "tools/run_apr_model_automation.py",
    "tools/generate_gs_evidence_report.py",
    "tools/generate_gs_e2e_preflight_report.py",
    "tools/build_gs_submission_package.py",
    "tools/generate_gs_readiness_review.py",
]

EVIDENCE_FILES = [
    "runtime/gs_certification_evidence/gs_evidence_report.json",
    "runtime/gs_certification_evidence/gs_evidence_report.md",
    "runtime/gs_certification_evidence/apr_model_automation_report.json",
    "runtime/gs_certification_evidence/gs_e2e_preflight_report.json",
    "runtime/gs_certification_evidence/gs_e2e_preflight_report.md",
]

PACKAGE_MANIFEST = PROJECT_ROOT / "runtime" / "gs_submission_package" / "apr-edgeinsight-gs-submission" / "PACKAGE_MANIFEST.json"

KEY_TERMS = {
    "APR model training automation": [
        "APR 모델 학습 자동화",
        "APR 모델 자동화",
        "run_apr_model_automation.py",
    ],
    "Dynamic Client Policy Control": [
        "Dynamic Client Policy Control",
        "동적 client 정책",
        "policy topic",
    ],
    "Client Runtime Configuration Update": [
        "Client Runtime Configuration Update",
        "runtime option",
        "pause/resume",
    ],
    "PC client": ["PC client", "windows_pc", "pc_test_publisher.py"],
    "Raspberry Pi client": ["Raspberry Pi", "raspberry_pi", "raspi_system_metrics_publisher.py"],
    "Ubuntu/Linux client": ["Ubuntu", "ubuntu_linux", "Linux client"],
    "Voice streaming excluded": ["Voice streaming", "voice streaming", "인증 범위 제외"],
    "Docker certification runtime": ["Docker", "docker-compose.cert.yml", ".env.cert"],
    "Integrated evidence report": ["통합 증적", "generate_gs_evidence_report.py", "gs_evidence_report"],
    "Submission package builder": ["제출 패키지", "build_gs_submission_package.py", "PACKAGE_MANIFEST"],
}

BLOCKED_PACKAGE_TOKENS = [
    ".env.cert",
    ".db",
    ".db-wal",
    ".db-shm",
    ".log",
    "__pycache__",
    "Lib/",
    "Scripts/",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_text(path):
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def file_status(path):
    p = PROJECT_ROOT / path
    return {
        "path": path,
        "exists": p.exists(),
        "size_bytes": p.stat().st_size if p.exists() else 0,
    }


def term_present(text, variants):
    lowered = text.lower()
    return any(item.lower() in lowered for item in variants)


def check_term_coverage():
    docs = CORE_DOCUMENTS + SUPPORT_DOCUMENTS
    checks = []
    for term, variants in KEY_TERMS.items():
        doc_results = []
        for doc in docs:
            p = PROJECT_ROOT / doc
            present = p.exists() and term_present(p.read_text(encoding="utf-8"), variants)
            doc_results.append({"document": doc, "present": present})
        core_present = any(item["present"] for item in doc_results if item["document"] in CORE_DOCUMENTS)
        any_present = any(item["present"] for item in doc_results)
        checks.append({
            "term": term,
            "ok": bool(core_present and any_present),
            "core_present": bool(core_present),
            "documents": doc_results,
        })
    return checks


def check_test_case_ids():
    path = PROJECT_ROOT / "docs" / "GS_INTEGRATED_TEST_CASES.md"
    if not path.exists():
        return {"ok": False, "reason": "missing integrated test cases", "count": 0, "duplicates": []}
    text = path.read_text(encoding="utf-8")
    ids = re.findall(r"\bTC-[A-Z]+-\d{3}\b", text)
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    return {
        "ok": len(ids) >= 20 and not duplicates,
        "count": len(ids),
        "duplicates": duplicates,
    }


def check_evidence_status():
    results = []
    for item in EVIDENCE_FILES:
        status = file_status(item)
        if item.endswith(".json") and status["exists"]:
            try:
                data = json.loads((PROJECT_ROOT / item).read_text(encoding="utf-8"))
                status["reported_status"] = data.get("overall_status") or data.get("status")
            except json.JSONDecodeError:
                status["reported_status"] = "invalid_json"
        results.append(status)
    return results


def check_package_manifest():
    if not PACKAGE_MANIFEST.exists():
        return {
            "ok": False,
            "exists": False,
            "file_count": 0,
            "blocked_files": [],
            "required_present": {},
        }
    data = json.loads(PACKAGE_MANIFEST.read_text(encoding="utf-8"))
    paths = [item["path"] for item in data.get("files", [])]
    blocked = [path for path in paths if any(token in path for token in BLOCKED_PACKAGE_TOKENS)]
    required = {
        "product/server.py": "product/server.py" in paths,
        "documents/GS_PRODUCT_DESCRIPTION_KO.md": "documents/GS_PRODUCT_DESCRIPTION_KO.md" in paths,
        "documents/GS_USER_OPERATION_MANUAL_KO.md": "documents/GS_USER_OPERATION_MANUAL_KO.md" in paths,
        "documents/GS_INTEGRATED_TEST_CASES.md": "documents/GS_INTEGRATED_TEST_CASES.md" in paths,
        "evidence/gs_evidence_report.json": "evidence/gs_evidence_report.json" in paths,
        "evidence/gs_e2e_preflight_report.json": "evidence/gs_e2e_preflight_report.json" in paths,
    }
    return {
        "ok": not blocked and all(required.values()) and len(paths) > 0,
        "exists": True,
        "file_count": len(paths),
        "blocked_files": blocked,
        "required_present": required,
    }


def build_markdown(report):
    lines = [
        "# GS Readiness Review",
        "",
        f"Generated at: {report['generated_at']}",
        f"Overall status: **{report['overall_status']}**",
        "",
        "## Documents",
        "",
        "| Path | Exists | Size |",
        "|---|---:|---:|",
    ]
    for item in report["documents"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.extend(["", "## Tool Files", "", "| Path | Exists | Size |", "|---|---:|---:|"])
    for item in report["tools"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item['size_bytes']} |")
    lines.extend(["", "## Term Coverage", "", "| Term | OK | Core Present |", "|---|---:|---:|"])
    for item in report["term_coverage"]:
        lines.append(f"| {item['term']} | {item['ok']} | {item['core_present']} |")
    lines.extend(["", "## Evidence", "", "| Path | Exists | Status |", "|---|---:|---|"])
    for item in report["evidence"]:
        lines.append(f"| `{item['path']}` | {item['exists']} | {item.get('reported_status', '')} |")
    manifest = report["package_manifest"]
    lines.extend([
        "",
        "## Package Manifest",
        "",
        f"- Exists: {manifest['exists']}",
        f"- File count: {manifest['file_count']}",
        f"- Blocked files: {len(manifest['blocked_files'])}",
        "",
        "## Test Cases",
        "",
        f"- Count: {report['test_cases']['count']}",
        f"- Duplicates: {', '.join(report['test_cases']['duplicates'])}",
        "",
    ])
    return "\n".join(lines)


def main():
    documents = [file_status(path) for path in CORE_DOCUMENTS + SUPPORT_DOCUMENTS]
    tools = [file_status(path) for path in REQUIRED_TOOLS]
    term_coverage = check_term_coverage()
    test_cases = check_test_case_ids()
    evidence = check_evidence_status()
    package_manifest = check_package_manifest()

    docs_ok = all(item["exists"] and item["size_bytes"] > 0 for item in documents)
    tools_ok = all(item["exists"] and item["size_bytes"] > 0 for item in tools)
    terms_ok = all(item["ok"] for item in term_coverage)
    evidence_ok = all(item["exists"] and item["size_bytes"] > 0 for item in evidence)
    evidence_status_ok = all(
        item.get("reported_status") in (None, "ok")
        for item in evidence
    )

    overall_ok = all([
        docs_ok,
        tools_ok,
        terms_ok,
        test_cases["ok"],
        evidence_ok,
        evidence_status_ok,
        package_manifest["ok"],
    ])

    report = {
        "generated_at": now_iso(),
        "overall_status": "ok" if overall_ok else "attention_required",
        "documents": documents,
        "tools": tools,
        "term_coverage": term_coverage,
        "test_cases": test_cases,
        "evidence": evidence,
        "package_manifest": package_manifest,
        "notes": [
            "This review checks GS submission readiness across documents, tools, evidence, and package manifest.",
            "It does not replace live Docker E2E testing.",
        ],
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(build_markdown(report), encoding="utf-8")

    print(json.dumps({
        "status": report["overall_status"],
        "json_report": str(OUTPUT_JSON),
        "markdown_report": str(OUTPUT_MD),
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())