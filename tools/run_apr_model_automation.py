import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APR_DIR = PROJECT_ROOT / "apr"
DEFAULT_REPORT = PROJECT_ROOT / "runtime" / "apr_model_automation_report.json"


REQUIRED_MODEL_FILES = [
    APR_DIR / "xgb_model.joblib",
    APR_DIR / "xgb_model_meta.json",
    APR_DIR / "xgb_model.json",
    APR_DIR / "xgb_preprocessor.joblib",
    APR_DIR / "xgb_runtime_meta.json",
]


METRIC_FILES = [
    APR_DIR / "xgb_metrics.csv",
    APR_DIR / "xgb_cv_metrics.csv",
]


def read_csv_rows(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def run_python_script(script, timeout):
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "script": str(script.relative_to(PROJECT_ROOT)),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ok": completed.returncode == 0,
    }


def build_file_status(paths):
    return {
        str(path.relative_to(PROJECT_ROOT)): {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat() if path.exists() else None,
        }
        for path in paths
    }


def main():
    parser = argparse.ArgumentParser(
        description="GS certification helper for APR model automation evidence."
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip runtime export and only verify current model artifacts.",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT),
        help="Path to write JSON evidence report.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each automation subprocess.",
    )
    args = parser.parse_args()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "steps": {},
        "model_files": {},
        "metric_files": {},
        "metrics": {},
        "overall_status": "unknown",
    }

    if args.skip_export:
        report["steps"]["export_runtime"] = {
            "skipped": True,
            "reason": "--skip-export",
        }
    else:
        report["steps"]["export_runtime"] = run_python_script(
            PROJECT_ROOT / "tools" / "export_apr_xgb_runtime.py",
            timeout=args.timeout,
        )

    report["steps"]["check_runtime"] = run_python_script(
        PROJECT_ROOT / "tools" / "check_apr_ml_runtime.py",
        timeout=args.timeout,
    )

    report["model_files"] = build_file_status(REQUIRED_MODEL_FILES)
    report["metric_files"] = build_file_status(METRIC_FILES)
    report["metrics"] = {
        str(path.relative_to(PROJECT_ROOT)): read_csv_rows(path)
        for path in METRIC_FILES
    }

    required_files_ok = all(item["exists"] and item["size_bytes"] > 0 for item in report["model_files"].values())
    export_ok = args.skip_export or report["steps"]["export_runtime"].get("ok", False)
    check_ok = report["steps"]["check_runtime"].get("ok", False)
    report["overall_status"] = "ok" if required_files_ok and export_ok and check_ok else "failed"

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = PROJECT_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": report["overall_status"],
        "report": str(report_path),
        "required_files_ok": required_files_ok,
        "export_ok": export_ok,
        "check_ok": check_ok,
    }, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())