import argparse
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runtime" / "gs_submission_package"
PACKAGE_NAME = "apr-edgeinsight-gs-submission"

PRODUCT_FILES = [
    "Dockerfile",
    "docker-compose.cert.yml",
    "config.example.json",
    ".env.example",
    "requirements.txt",
    "server.py",
    "distributed_broker.py",
    "sensor_registry.py",
    "system_monitor.py",
]

PRODUCT_DIRS = [
    "device",
    "policy",
    "database",
    "monitor",
    "templates",
    "static",
    "tools",
    "mosquitto/config",
]

DOCUMENTS = [
    "docs/GS_CERTIFICATION_SCOPE_V1.md",
    "docs/GS_PRODUCT_DESCRIPTION_KO.md",
    "docs/USER_MANUAL_KO.md",
    "docs/GS_INTEGRATED_TEST_CASES.md",
    "docs/GS_SUBMISSION_PACKAGE_CHECKLIST.md",
    "docs/GS_DOCKER_INSTALLATION_GUIDE.md",
    "docs/GS_RELEASE_PACKAGE_STRUCTURE.md",
    "docs/GS_SECURITY_CONFIGURATION_GUIDE.md",
    "docs/GS_SECURITY_TEST_CASES.md",
    "docs/GS_APR_MODEL_TRAINING_AUTOMATION.md",
    "docs/GS_APR_MODEL_TEST_CASES.md",
    "docs/GS_INTEGRATED_EVIDENCE_REPORT_GUIDE.md",
    "docs/GS_SUBMISSION_PACKAGE_BUILD_GUIDE.md",
]

EVIDENCE_FILES = [
    "runtime/gs_certification_evidence/gs_evidence_report.md",
    "runtime/gs_certification_evidence/gs_evidence_report.json",
    "runtime/gs_certification_evidence/apr_model_automation_report.json",
]

EXCLUDE_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".agents",
    ".codex",
    "Lib",
    "Scripts",
    "runtime",
    "logs",
    "experiment_results",
}

EXCLUDE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".log",
    ".err.log",
    ".out.log",
    ".db",
    ".db-shm",
    ".db-wal",
    ".bak",
    ".zip",
)

EXCLUDE_CONTAINS = (
    ".malformed",
    ".recovered",
    "env.cert",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def rel(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def should_exclude(path):
    name = path.name
    text = str(path).replace("\\", "/")
    if name in EXCLUDE_NAMES:
        return True
    if name.startswith(".") and name not in {".env.example"}:
        return True
    if any(name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return True
    if any(token in text for token in EXCLUDE_CONTAINS):
        return True
    return False


def copy_file(src_rel, dst_root, target_rel=None, optional=False):
    src = PROJECT_ROOT / src_rel
    if target_rel is None:
        target_rel = src_rel
    dst = dst_root / target_rel
    if not src.exists():
        if optional:
            return {"path": src_rel, "copied": False, "optional": True, "reason": "missing"}
        raise FileNotFoundError(f"required file missing: {src_rel}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {"path": src_rel, "target": rel(dst), "copied": True, "size_bytes": dst.stat().st_size}


def copy_tree(src_rel, dst_root):
    src = PROJECT_ROOT / src_rel
    dst = dst_root / src_rel
    if not src.exists():
        raise FileNotFoundError(f"required directory missing: {src_rel}")
    copied = []
    for path in src.rglob("*"):
        if any(should_exclude(parent) for parent in path.parents if parent != src.parent):
            continue
        if should_exclude(path):
            continue
        if path.is_file():
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(rel(target))
    return {"path": src_rel, "target": rel(dst), "copied": True, "file_count": len(copied)}


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(package_dir, copied_items, zip_path=None):
    files = []
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            files.append({
                "path": rel(path.relative_to(package_dir)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return {
        "generated_at": now_iso(),
        "package_name": PACKAGE_NAME,
        "package_dir": str(package_dir),
        "zip_path": str(zip_path) if zip_path else None,
        "product": "APR EdgeInsight Industrial IoT Platform v1.0",
        "scope_note": "Voice streaming code/process is preserved in the repository but excluded from the GS certification submission scope.",
        "secret_note": ".env.cert and real secrets are intentionally excluded. Use .env.example as a template only.",
        "copied_items": copied_items,
        "files": files,
    }


def write_zip(package_dir, zip_path):
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(package_dir.parent))


def main():
    parser = argparse.ArgumentParser(description="Build a GS certification submission package.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root directory.")
    parser.add_argument("--clean", action="store_true", help="Delete existing package directory before building.")
    parser.add_argument("--include-evidence", action="store_true", help="Copy generated evidence reports if present.")
    parser.add_argument("--zip", action="store_true", help="Create a zip archive next to the package directory.")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    package_dir = output_root / PACKAGE_NAME

    if args.clean and package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    copied_items = []

    product_root = package_dir / "product"
    documents_root = package_dir / "documents"
    evidence_root = package_dir / "evidence"

    for item in PRODUCT_FILES:
        copied_items.append(copy_file(item, product_root))
    for item in PRODUCT_DIRS:
        copied_items.append(copy_tree(item, product_root))
    for item in DOCUMENTS:
        copied_items.append(copy_file(item, documents_root, Path(item).name))
    if args.include_evidence:
        for item in EVIDENCE_FILES:
            copied_items.append(copy_file(item, evidence_root, Path(item).name, optional=True))

    manifest_path = package_dir / "PACKAGE_MANIFEST.json"
    manifest = build_manifest(package_dir, copied_items)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    zip_path = None
    if args.zip:
        zip_path = output_root / f"{PACKAGE_NAME}.zip"
        write_zip(package_dir, zip_path)
        manifest = build_manifest(package_dir, copied_items, zip_path=zip_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "package_dir": str(package_dir),
        "manifest": str(manifest_path),
        "zip_path": str(zip_path) if zip_path else None,
        "file_count": len(manifest["files"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())