import argparse
import json
import os
import re
from pathlib import Path


INSECURE_FLASK_SECRET_KEYS = {
    "",
    "change-this-secret-before-production",
    "change-this-secret-before-certification",
    "CHANGE_ME_32_CHAR_FLASK_SECRET_FOR_CERT",
}
INSECURE_PASSWORDS = {
    "",
    "admin",
    "password",
    "admin1234",
    "user1234",
    "CHANGE_ME_ADMIN_PASSWORD",
    "CHANGE_ME_USER_PASSWORD",
}
INSECURE_APR_AES_KEYS = {
    "",
    "01010101010101010101010101010101",
    "CHANGE_ME_32_HEX_CHAR_AES_KEY_NO_QUOTES",
}


def parse_env_file(path):
    values = {}
    if not path:
        return values
    env_path = Path(path)
    if not env_path.exists():
        raise FileNotFoundError(f"env file not found: {env_path}")
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_value(values, key):
    return values.get(key, os.environ.get(key, ""))


def is_valid_aes_key(value):
    return bool(re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{48}|[0-9a-fA-F]{64}", value or ""))


def build_check(name, ok, message):
    return {"name": name, "ok": bool(ok), "message": message}


def main():
    parser = argparse.ArgumentParser(description="Validate GS certification runtime security settings.")
    parser.add_argument("--env-file", help="Optional .env.cert file to validate.")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    values = parse_env_file(args.env_file)
    checks = []

    cert_mode = get_value(values, "CERTIFICATION_MODE").lower() in {"1", "true", "yes", "on"}
    flask_secret = get_value(values, "FLASK_SECRET_KEY")
    admin_password = get_value(values, "IOT_ADMIN_PASSWORD")
    user_password = get_value(values, "IOT_USER_PASSWORD")
    apr_key = get_value(values, "APR_AES_KEY_HEX")

    checks.append(build_check(
        "CERTIFICATION_MODE",
        cert_mode,
        "CERTIFICATION_MODE must be true for GS certification execution evidence.",
    ))
    checks.append(build_check(
        "FLASK_SECRET_KEY",
        flask_secret not in INSECURE_FLASK_SECRET_KEYS and len(flask_secret) >= 24,
        "FLASK_SECRET_KEY must be changed from the template and have at least 24 characters.",
    ))
    checks.append(build_check(
        "IOT_ADMIN_PASSWORD",
        admin_password not in INSECURE_PASSWORDS and len(admin_password) >= 8,
        "IOT_ADMIN_PASSWORD must be changed from the template and have at least 8 characters.",
    ))
    checks.append(build_check(
        "IOT_USER_PASSWORD",
        user_password not in INSECURE_PASSWORDS and len(user_password) >= 8,
        "IOT_USER_PASSWORD must be changed from the template and have at least 8 characters.",
    ))
    checks.append(build_check(
        "APR_AES_KEY_HEX",
        apr_key not in INSECURE_APR_AES_KEYS and is_valid_aes_key(apr_key),
        "APR_AES_KEY_HEX must be a non-default 128/192/256-bit hex key.",
    ))

    result = {
        "status": "ok" if all(item["ok"] for item in checks) else "failed",
        "env_file": str(Path(args.env_file).resolve()) if args.env_file else None,
        "checks": checks,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"status={result['status']}")
        for item in checks:
            marker = "OK" if item["ok"] else "FAIL"
            print(f"[{marker}] {item['name']}: {item['message']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())