from flask import Flask, render_template, jsonify, request, session, redirect, url_for, g, send_file
import sqlite3
import json
import hashlib
import time
import threading
import html
import os
import io
import zipfile
import atexit
import socket
import uuid
import re
from datetime import datetime, timezone, timedelta
from functools import wraps
import paho.mqtt.client as mqtt
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from policy.apr_policy import apr_engine
except ImportError:
    apr_engine = None

try:
    from monitor.queue_monitor import queue_monitor
except ImportError:
    queue_monitor = None

try:
    from analysis.latency_analysis import compute_latency_stats, generate_histogram, compute_latency_trend
except ImportError:
    pass

try:
    from database.db_manager import db_manager
except ImportError:
    db_manager = None

try:
    from policy.codec import decode_payload
except ImportError:
    decode_payload = None

try:
    from distributed_broker import connect_client_to_any_broker, normalize_brokers, publish_single_to_any_broker
except ImportError:
    connect_client_to_any_broker = None
    normalize_brokers = None
    publish_single_to_any_broker = None

# APR 관리자 트리거 수집/결정 프로세스용 전역 상태
apr_mqtt_client = None          # MQTT 발행 클라이언트 (C2 push용)
apr_policy_cache = {}           # {sensor_id: dict} - 현재 적용된 정책 캐시
apr_collection_active = {}      # {sensor_id: bool} - 수집 모드 활성 여부
apr_metrics_buffer = {}         # {sensor_id: [metric_dict, ...]} - 수집된 메트릭 버퍼
apr_feedback_buffer = {}        # {sensor_id: [metric_dict, ...]} - 정책 적용 후 피드백 수집 버퍼
apr_feedback_log_id = {}        # {sensor_id: int} - 현재 피드백 추적 중인 apr_policy_log row id
APR_MIN_SAMPLES = 5             # 정책 결정에 필요한 최소 수집 샘플 수
APR_FEEDBACK_SAMPLES = 10       # 피드백 결과 판정에 필요한 최소 샘플 수
APR_AUTO_EVALUATION_INTERVAL_SECONDS = 30
apr_auto_last_evaluation_at = {}
apr_auto_evaluation_inflight = set()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-before-production")

DB_NAME = os.environ.get("DB_NAME", "iot_data.db")
DB_JOURNAL_MODE = os.environ.get("DB_JOURNAL_MODE", "WAL").upper()
DB_BUSY_TIMEOUT_MS = int(os.environ.get("DB_BUSY_TIMEOUT_MS", "30000"))
SYSTEM_MODE = os.environ.get("SYSTEM_MODE", "windows")
SYSTEM_LOCK_FILE = os.environ.get("SYSTEM_LOCK_FILE", os.path.join("runtime", "iot_dashboard.lock"))
SYSTEM_LOCK_STALE_SECONDS = int(os.environ.get("SYSTEM_LOCK_STALE_SECONDS", "30"))
DEFAULT_APP_PORT = int(os.environ.get("PORT", "4728"))
CONFIG_FILE = "config.json"
POLICY_TOPIC_PREFIX = "iot/sensor/policy/"
KST = timezone(timedelta(hours=9))
system_owner_id = str(uuid.uuid4())
system_lock_active = False
system_lock_stop_event = threading.Event()
system_lock_thread = None
mqtt_client = None
mqtt_startup_error = None

ADMIN_PATH_PREFIXES = (
    "/admin",
    "/sensor_config",
    "/queue_dashboard",
    "/experiment_dashboard",
    "/schema_dashboard",
    "/apr_dashboard",
    "/voice_dashboard",
    "/server_operation_manual",
)
ADMIN_API_PREFIXES = (
    "/api/admin",
    "/api/system/shutdown",
    "/api/sensors",
    "/api/apr",
    "/api/experiment/run",
)
PUBLIC_ENDPOINTS = {
    "login",
    "register",
    "static",
}

# 사전에 정의된 센서 데이터로 인정할 최소 필드
DEFINED_SENSOR_REQUIRED_FIELDS = {
    "sensor_id",
    "sensor_type",
    "value",
    "unit",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_api_request():
    return request.path.startswith("/api/")


def client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or ""


def fetch_user_by_id(user_id):
    if not user_id:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.company, u.phone, u.role, u.status, u.created_at,
               u.site_id, s.name, u.group_id, g.name, u.user_topic_name, u.user_topic_path
        FROM users u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN user_groups g ON g.id = u.group_id
        WHERE u.id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "company": row[3],
        "phone": row[4],
        "role": row[5],
        "status": row[6],
        "created_at": row[7],
        "site_id": row[8],
        "site_name": row[9],
        "group_id": row[10],
        "group_name": row[11],
        "user_topic_name": row[12],
        "user_topic_path": row[13],
    }


def fetch_user_by_email(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.password_hash, u.company, u.phone,
               u.role, u.status, u.created_at,
               u.site_id, s.name, u.group_id, g.name, u.user_topic_name, u.user_topic_path
        FROM users u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN user_groups g ON g.id = u.group_id
        WHERE lower(u.email) = lower(?)
    """, (email,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "password_hash": row[3],
        "company": row[4],
        "phone": row[5],
        "role": row[6],
        "status": row[7],
        "created_at": row[8],
        "site_id": row[9],
        "site_name": row[10],
        "group_id": row[11],
        "group_name": row[12],
        "user_topic_name": row[13],
        "user_topic_path": row[14],
    }


def current_user_is_admin():
    user = getattr(g, "current_user", None)
    return bool(user and user.get("role") == "ADMIN")


def current_user_id():
    user = getattr(g, "current_user", None)
    return user.get("id") if user else None


def can_manage_owner(owner_user_id):
    if current_user_is_admin():
        return True
    return int(owner_user_id) == int(current_user_id())


def resolve_owner_user_id(data):
    if current_user_is_admin() and data.get("owner_user_id"):
        return int(data.get("owner_user_id"))
    return int(current_user_id())


def fetch_user_exists(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row)


USER_STATUSES = ("PENDING", "ACTIVE", "SUSPENDED")


def default_user_topic_name(name):
    words = str(name or "").strip().split()
    return normalize_topic_part(words[0] if words else "user", "user")


def build_user_topic_path(group_topic_path, user_topic_name):
    return f"{group_topic_path}/{normalize_topic_part(user_topic_name, 'user')}"


def normalize_topic_part(value, fallback="default"):
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r"\s+", "_", text)
    text = text.replace("/", "_").replace("\\", "_")
    text = re.sub(r"[^\w.-]", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text or fallback


def build_fleet_topic_path(user_topic_path, fleet_name):
    return f"{user_topic_path}/{normalize_topic_part(fleet_name, 'fleet')}"


def build_device_telemetry_topic(topic_prefix, device_type, device_id):
    return f"{topic_prefix}/{normalize_topic_part(device_type, 'device')}/{normalize_topic_part(device_id, 'device')}"


def build_device_policy_topic(topic_prefix, device_id):
    return f"{topic_prefix}/policy/{normalize_topic_part(device_id, 'device')}"


DEVICE_OS_VALUES = ("raspberry_pi", "ubuntu_linux", "windows_pc")


def normalize_device_os(value):
    text = str(value or "").strip().lower()
    aliases = {
        "raspberry": "raspberry_pi",
        "raspi": "raspberry_pi",
        "raspbian": "raspberry_pi",
        "linux": "ubuntu_linux",
        "ubuntu": "ubuntu_linux",
        "windows": "windows_pc",
        "pc": "windows_pc",
    }
    text = aliases.get(text, text)
    return text if text in DEVICE_OS_VALUES else "raspberry_pi"


def clean_mqtt_publish_topic(value):
    topic = str(value or "").strip().strip("/")
    if not topic:
        return ""
    if "#" in topic or "+" in topic:
        raise ValueError("topic_wildcards_not_allowed")
    return re.sub(r"/+", "/", topic)


def fetch_user_topic_context(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.status, u.user_topic_name, u.user_topic_path,
               g.topic_path
        FROM users u
        LEFT JOIN user_groups g ON g.id = u.group_id
        WHERE u.id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    topic_name = row[4] or default_user_topic_name(row[1])
    topic_path = row[5] or build_user_topic_path(row[6] or "default_site/default_group", topic_name)
    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "status": row[3],
        "user_topic_name": topic_name,
        "user_topic_path": topic_path,
    }


def fetch_fleet_topic_context(fleet_id):
    if not fleet_id:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.name, f.owner_user_id, f.topic_name, f.topic_path,
               u.user_topic_path
        FROM fleets f
        LEFT JOIN users u ON u.id = f.owner_user_id
        WHERE f.id = ?
    """, (fleet_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    topic_name = row[3] or normalize_topic_part(row[1], "fleet")
    topic_path = row[4] or build_fleet_topic_path(row[5] or "default_site/default_group/user", row[1])
    return {
        "id": row[0],
        "name": row[1],
        "owner_user_id": row[2],
        "topic_name": topic_name,
        "topic_path": topic_path,
    }


def expected_device_topic_context(owner_user_id, fleet_id, device_type, device_id):
    owner_context = fetch_user_topic_context(owner_user_id)
    if not owner_context:
        return None
    fleet_context = fetch_fleet_topic_context(fleet_id) if fleet_id else None
    topic_prefix = fleet_context["topic_path"] if fleet_context else owner_context["user_topic_path"]
    return {
        "topic_prefix": topic_prefix,
        "telemetry_topic": build_device_telemetry_topic(topic_prefix, device_type, device_id),
        "policy_topic": build_device_policy_topic(topic_prefix, device_id),
        "source": "fleet" if fleet_context else "user",
    }


def fixed_device_topic_fields(owner_user_id, fleet_id, device_type, device_id):
    topic_context = expected_device_topic_context(owner_user_id, fleet_id, device_type, device_id)
    if not topic_context:
        return None
    return (
        topic_context["topic_prefix"],
        topic_context["telemetry_topic"],
        topic_context["policy_topic"],
    )


def resolve_device_topics(owner_user_id, fleet_id, device_type, device_id, data):
    fixed_topics = fixed_device_topic_fields(owner_user_id, fleet_id, device_type, device_id)
    if not fixed_topics:
        return None
    default_prefix, default_telemetry, default_policy = fixed_topics
    topic_prefix = clean_mqtt_publish_topic(data.get("topic_prefix") or default_prefix)
    telemetry_topic = clean_mqtt_publish_topic(data.get("telemetry_topic") or "")
    policy_topic = clean_mqtt_publish_topic(data.get("policy_topic") or "")
    if not telemetry_topic:
        telemetry_topic = build_device_telemetry_topic(topic_prefix, device_type, device_id)
    if not policy_topic:
        policy_topic = build_device_policy_topic(topic_prefix, device_id)
    return topic_prefix, telemetry_topic, policy_topic


def topic_consistency_report(repair_missing=False):
    conn = get_db_connection()
    cur = conn.cursor()
    now = now_iso()
    repaired = {"fleets": 0, "devices": 0}

    cur.execute("""
        SELECT f.id, f.name, f.owner_user_id, f.topic_name, f.topic_path, u.user_topic_path
        FROM fleets f
        LEFT JOIN users u ON u.id = f.owner_user_id
        ORDER BY f.id
    """)
    fleet_issues = []
    for fleet_id, name, owner_user_id, topic_name, topic_path, user_topic_path in cur.fetchall():
        expected_topic_name = normalize_topic_part(topic_name or name, "fleet")
        expected_topic_path = build_fleet_topic_path(user_topic_path or "default_site/default_group/user", expected_topic_name)
        issues = []
        if not user_topic_path:
            issues.append("owner_user_topic_missing")
        if not topic_name:
            issues.append("fleet_topic_name_missing")
        if not topic_path:
            issues.append("fleet_topic_path_missing")
        if topic_path and user_topic_path and not topic_path.startswith(f"{user_topic_path}/"):
            issues.append("fleet_topic_outside_owner")
        if repair_missing and ("fleet_topic_name_missing" in issues or "fleet_topic_path_missing" in issues):
            cur.execute("""
                UPDATE fleets
                SET topic_name = COALESCE(NULLIF(trim(topic_name), ''), ?),
                    topic_path = COALESCE(NULLIF(trim(topic_path), ''), ?),
                    updated_at = ?
                WHERE id = ?
            """, (expected_topic_name, expected_topic_path, now, fleet_id))
            repaired["fleets"] += 1
            topic_name = topic_name or expected_topic_name
            topic_path = topic_path or expected_topic_path
            issues = [issue for issue in issues if issue not in ("fleet_topic_name_missing", "fleet_topic_path_missing")]
        if issues:
            fleet_issues.append({
                "id": fleet_id,
                "name": name,
                "owner_user_id": owner_user_id,
                "topic_name": topic_name,
                "topic_path": topic_path,
                "expected_topic_name": expected_topic_name,
                "expected_topic_path": expected_topic_path,
                "issues": issues,
            })

    cur.execute("""
        SELECT d.id, d.device_id, d.device_name, d.device_type, d.fleet_id, d.owner_user_id,
               d.topic_prefix, d.telemetry_topic, d.policy_topic,
               f.owner_user_id, f.topic_path, u.user_topic_path
        FROM devices d
        LEFT JOIN fleets f ON f.id = d.fleet_id
        LEFT JOIN users u ON u.id = d.owner_user_id
        ORDER BY d.id
    """)
    device_issues = []
    for row in cur.fetchall():
        (
            row_id, device_id, device_name, device_type, fleet_id, owner_user_id,
            topic_prefix, telemetry_topic, policy_topic, fleet_owner_id, fleet_topic_path,
            user_topic_path,
        ) = row
        expected_prefix = fleet_topic_path if fleet_id and fleet_topic_path else user_topic_path
        expected_telemetry = build_device_telemetry_topic(expected_prefix or "", device_type, device_id) if expected_prefix else None
        expected_policy = build_device_policy_topic(expected_prefix or "", device_id) if expected_prefix else None
        issues = []
        if not user_topic_path:
            issues.append("owner_user_topic_missing")
        if fleet_id and not fleet_topic_path:
            issues.append("fleet_topic_missing")
        if fleet_id and fleet_owner_id is not None and int(fleet_owner_id) != int(owner_user_id):
            issues.append("fleet_owner_mismatch")
        if not topic_prefix:
            issues.append("device_topic_prefix_missing")
        if not telemetry_topic:
            issues.append("device_telemetry_topic_missing")
        if not policy_topic:
            issues.append("device_policy_topic_missing")
        if topic_prefix and expected_prefix and topic_prefix != expected_prefix:
            issues.append("custom_or_legacy_topic_prefix")

        missing_topic_issue = any(issue in issues for issue in (
            "device_topic_prefix_missing",
            "device_telemetry_topic_missing",
            "device_policy_topic_missing",
        ))
        if repair_missing and expected_prefix and missing_topic_issue:
            next_prefix = topic_prefix or expected_prefix
            cur.execute("""
                UPDATE devices
                SET topic_prefix = COALESCE(NULLIF(trim(topic_prefix), ''), ?),
                    telemetry_topic = COALESCE(NULLIF(trim(telemetry_topic), ''), ?),
                    policy_topic = COALESCE(NULLIF(trim(policy_topic), ''), ?),
                    updated_at = ?
                WHERE id = ?
            """, (
                next_prefix,
                telemetry_topic or build_device_telemetry_topic(next_prefix, device_type, device_id),
                policy_topic or build_device_policy_topic(next_prefix, device_id),
                now,
                row_id,
            ))
            repaired["devices"] += 1
            topic_prefix = topic_prefix or next_prefix
            telemetry_topic = telemetry_topic or build_device_telemetry_topic(next_prefix, device_type, device_id)
            policy_topic = policy_topic or build_device_policy_topic(next_prefix, device_id)
            issues = [issue for issue in issues if issue not in (
                "device_topic_prefix_missing",
                "device_telemetry_topic_missing",
                "device_policy_topic_missing",
            )]

        if issues:
            device_issues.append({
                "id": row_id,
                "device_id": device_id,
                "device_name": device_name,
                "owner_user_id": owner_user_id,
                "fleet_id": fleet_id,
                "topic_prefix": topic_prefix,
                "telemetry_topic": telemetry_topic,
                "policy_topic": policy_topic,
                "expected_topic_prefix": expected_prefix,
                "expected_telemetry_topic": expected_telemetry,
                "expected_policy_topic": expected_policy,
                "issues": issues,
            })

    if repair_missing:
        conn.commit()
    conn.close()
    return {
        "status": "ok",
        "repair_missing": repair_missing,
        "repaired": repaired,
        "summary": {
            "fleet_issue_count": len(fleet_issues),
            "device_issue_count": len(device_issues),
        },
        "fleets": fleet_issues,
        "devices": device_issues,
    }


def row_to_site(row):
    return {
        "id": row[0],
        "name": row[1],
        "topic_name": row[2],
        "description": row[3],
        "created_at": row[4],
        "updated_at": row[5],
    }


def row_to_group(row):
    return {
        "id": row[0],
        "site_id": row[1],
        "site_name": row[2],
        "site_topic_name": row[3],
        "name": row[4],
        "topic_name": row[5],
        "topic_path": row[6],
        "description": row[7],
        "is_default": bool(row[8]),
        "created_at": row[9],
        "updated_at": row[10],
    }


def get_default_site_group(cur):
    cur.execute("SELECT id, topic_name FROM sites WHERE name = ?", ("Default Site",))
    site = cur.fetchone()
    if not site:
        timestamp = now_iso()
        cur.execute("""
            INSERT INTO sites (name, topic_name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("Default Site", "default_site", "Default site for temporary and migrated users", timestamp, timestamp))
        site_id = cur.lastrowid
        site_topic = "default_site"
    else:
        site_id = site[0]
        site_topic = site[1]

    cur.execute("""
        SELECT id, topic_path
        FROM user_groups
        WHERE site_id = ? AND is_default = 1
        ORDER BY id
        LIMIT 1
    """, (site_id,))
    group = cur.fetchone()
    if not group:
        timestamp = now_iso()
        group_topic = "default_group"
        group_path = f"{site_topic}/{group_topic}"
        cur.execute("""
            INSERT INTO user_groups
            (site_id, name, topic_name, topic_path, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (site_id, "Default Group", group_topic, group_path, "Default group for temporary and migrated users", timestamp, timestamp))
        group_id = cur.lastrowid
    else:
        group_id = group[0]
        group_path = group[1]
    return site_id, group_id, group_path


def fetch_group_for_site(cur, site_id, group_id):
    cur.execute("""
        SELECT g.id, g.topic_path, s.topic_name
        FROM user_groups g
        JOIN sites s ON s.id = g.site_id
        WHERE g.id = ? AND g.site_id = ?
    """, (group_id, site_id))
    return cur.fetchone()


def fetch_fleet_row(fleet_id):
    if not fleet_id:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT f.id, f.name, f.description, f.owner_user_id, u.name, u.email,
               f.topic_name, f.topic_path, f.created_at, f.updated_at,
               fps.policy_json, fps.applied_at
        FROM fleets f
        LEFT JOIN users u ON u.id = f.owner_user_id
        LEFT JOIN fleet_policy_state fps ON fps.fleet_id = f.id
        WHERE f.id = ?
    """, (fleet_id,))
    row = cur.fetchone()
    conn.close()
    return row


def serialize_fleet(row):
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "owner_user_id": row[3],
        "owner_name": row[4],
        "owner_email": row[5],
        "topic_name": row[6],
        "topic_path": row[7],
        "created_at": row[8],
        "updated_at": row[9],
        "current_policy": safe_json_loads(row[10]) if len(row) > 10 else None,
        "policy_applied_at": row[11] if len(row) > 11 else None,
    }


def serialize_device(row):
    return {
        "id": row[0],
        "device_id": row[1],
        "device_name": row[2],
        "device_type": row[3],
        "device_os": row[4] or "raspberry_pi",
        "fleet_id": row[5],
        "fleet_name": row[6],
        "owner_user_id": row[7],
        "owner_name": row[8],
        "owner_email": row[9],
        "status": row[10],
        "topic_prefix": row[11],
        "telemetry_topic": row[12],
        "policy_topic": row[13],
        "description": row[14],
        "created_at": row[15],
        "updated_at": row[16],
        "current_policy": safe_json_loads(row[17]) if len(row) > 17 else None,
        "policy_applied_at": row[18] if len(row) > 18 else None,
    }


def safe_json_loads(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def log_access_event(event_type, email=None, user_id=None, failure_reason=None):
    try:
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO access_logs
            (user_id, email, event_type, failure_reason, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            email,
            event_type,
            failure_reason,
            client_ip(),
            request.headers.get("User-Agent", ""),
            now_iso(),
        ))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[auth] access log failed: {exc}")


def log_audit_event(action, target_type=None, target_id=None, detail=None, actor_user_id=None):
    try:
        actor_id = actor_user_id
        if actor_id is None and getattr(g, "current_user", None):
            actor_id = g.current_user.get("id")
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO audit_logs
            (actor_user_id, action, target_type, target_id, detail_json, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            actor_id,
            action,
            target_type,
            str(target_id) if target_id is not None else None,
            json.dumps(detail or {}, ensure_ascii=False),
            client_ip(),
            now_iso(),
        ))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"[auth] audit log failed: {exc}")


def wants_admin(path):
    if any(path.startswith(prefix) for prefix in ADMIN_PATH_PREFIXES):
        return True
    if any(path.startswith(prefix) for prefix in ADMIN_API_PREFIXES):
        if path == "/api/sensors" and request.method == "GET":
            return False
        return True
    return False


def unauthorized_response():
    if is_api_request():
        return jsonify({"error": "authentication_required"}), 401
    return redirect(url_for("login", next=request.full_path if request.query_string else request.path))


def forbidden_response():
    if is_api_request():
        return jsonify({"error": "admin_required"}), 403
    return render_template("permission_denied.html", user=getattr(g, "current_user", None)), 403


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not getattr(g, "current_user", None):
            return unauthorized_response()
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not user:
            return unauthorized_response()
        if user.get("role") != "ADMIN":
            return forbidden_response()
        return fn(*args, **kwargs)
    return wrapper


@app.before_request
def load_current_user():
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if request.path.startswith("/static/"):
        return None

    g.current_user = fetch_user_by_id(session.get("user_id"))
    if not g.current_user:
        return unauthorized_response()
    if g.current_user.get("status") != "ACTIVE":
        session.clear()
        log_access_event("LOGIN_FAIL", email=g.current_user.get("email"), user_id=g.current_user.get("id"), failure_reason=g.current_user.get("status"))
        return unauthorized_response()
    if wants_admin(request.path) and g.current_user.get("role") != "ADMIN":
        return forbidden_response()
    return None


def get_system_identity():
    return {
        "owner_id": system_owner_id,
        "mode": SYSTEM_MODE,
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "db_name": DB_NAME,
        "started_at": getattr(get_system_identity, "started_at", now_iso()),
        "heartbeat_at": now_iso(),
    }


get_system_identity.started_at = now_iso()


def read_system_lock():
    try:
        with open(SYSTEM_LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return {"raw": "unreadable"}


def lock_is_stale(lock_data):
    heartbeat = lock_data.get("heartbeat_at") if isinstance(lock_data, dict) else None
    dt = parse_iso_datetime(heartbeat)
    if not dt:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() > SYSTEM_LOCK_STALE_SECONDS


def write_system_lock():
    lock_dir = os.path.dirname(SYSTEM_LOCK_FILE)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)
    tmp_path = f"{SYSTEM_LOCK_FILE}.{system_owner_id}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(get_system_identity(), f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, SYSTEM_LOCK_FILE)


def acquire_system_lock():
    global system_lock_active, system_lock_thread
    lock_dir = os.path.dirname(SYSTEM_LOCK_FILE)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)

    existing = read_system_lock()
    if existing and not lock_is_stale(existing):
        raise RuntimeError(
            "Another system instance is already using the shared DB: "
            f"{existing}"
        )

    write_system_lock()
    system_lock_active = True
    system_lock_stop_event.clear()
    system_lock_thread = threading.Thread(target=system_lock_heartbeat, daemon=True)
    system_lock_thread.start()
    atexit.register(release_system_lock)


def system_lock_heartbeat():
    while not system_lock_stop_event.wait(5):
        if system_lock_active:
            write_system_lock()


def release_system_lock():
    global system_lock_active
    if not system_lock_active:
        return
    system_lock_stop_event.set()
    current = read_system_lock()
    if isinstance(current, dict) and current.get("owner_id") == system_owner_id:
        try:
            os.remove(SYSTEM_LOCK_FILE)
        except FileNotFoundError:
            pass
    system_lock_active = False


def graceful_shutdown(exit_process=False):
    global mqtt_client
    try:
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
    finally:
        mqtt_client = None
    if db_manager:
        db_manager.stop()
    release_system_lock()
    if exit_process:
        os._exit(0)


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        # Python accepts +00:00 but not all old payloads use timezone.
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def format_kst_time_label(value):
    dt = parse_iso_datetime(value)
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%H:%M:%S")


def calc_latency_seconds(publish_timestamp, received_timestamp):
    pub_dt = parse_iso_datetime(publish_timestamp)
    recv_dt = parse_iso_datetime(received_timestamp)
    if not pub_dt or not recv_dt:
        return None
    try:
        return round((recv_dt - pub_dt).total_seconds(), 6)
    except TypeError:
        # Fallback for mixed naive/aware datetimes.
        if pub_dt.tzinfo is not None:
            pub_dt = pub_dt.replace(tzinfo=None)
        if recv_dt.tzinfo is not None:
            recv_dt = recv_dt.replace(tzinfo=None)
        return round((recv_dt - pub_dt).total_seconds(), 6)


def seconds_since_iso(value):
    dt = parse_iso_datetime(value)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())


def calculate_collection_timing(cur, sensor_id, sensor_type=None, window=200, late_multiplier=2.0, min_samples=5):
    if sensor_type is None:
        cur.execute("""
            SELECT COALESCE(received_timestamp, timestamp)
            FROM sensor_data
            WHERE sensor_id = ?
              AND COALESCE(received_timestamp, timestamp) IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (sensor_id, window))
    else:
        cur.execute("""
            SELECT COALESCE(received_timestamp, timestamp)
            FROM sensor_data
            WHERE sensor_id = ?
              AND sensor_type = ?
              AND COALESCE(received_timestamp, timestamp) IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (sensor_id, sensor_type, window))

    timestamps = []
    for row in cur.fetchall():
        dt = parse_iso_datetime(row[0])
        if not dt:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        timestamps.append(dt.astimezone(timezone.utc))

    if not timestamps:
        return {
            "collection_status": "NO_DATA",
            "collection_warning": False,
            "last_received_at": None,
            "elapsed_since_last_seconds": None,
            "avg_collection_interval_seconds": None,
            "collection_warning_threshold_seconds": None,
            "collection_sample_count": 0,
        }

    gaps = []
    for newer, older in zip(timestamps, timestamps[1:]):
        gap = (newer - older).total_seconds()
        if gap >= 0:
            gaps.append(gap)

    avg_interval = round(sum(gaps) / len(gaps), 3) if gaps else None
    elapsed = round(seconds_since_iso(timestamps[0].isoformat()), 3)
    threshold = round(avg_interval * late_multiplier, 3) if avg_interval is not None else None
    has_enough_samples = len(gaps) >= max(1, min_samples - 1)
    warning = bool(has_enough_samples and threshold is not None and elapsed > threshold)

    if warning:
        status = "LATE"
    elif not has_enough_samples:
        status = "INSUFFICIENT_SAMPLES"
    else:
        status = "OK"

    return {
        "collection_status": status,
        "collection_warning": warning,
        "last_received_at": timestamps[0].isoformat(),
        "elapsed_since_last_seconds": elapsed,
        "avg_collection_interval_seconds": avg_interval,
        "collection_warning_threshold_seconds": threshold,
        "collection_sample_count": len(timestamps),
    }


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def get_platform_runtime_config():
    config = load_config()
    platform = config.get("platform", {})
    db_writer = platform.get("db_writer", {})
    return {
        "mode": platform.get("mode", "hybrid"),
        "experiment_id": platform.get("experiment_id", "EXP_DEFAULT"),
        "enable_experiment_log": bool(platform.get("enable_experiment_log", True)),
        "enable_apr": bool(platform.get("enable_apr", False)),
        "auto_apr": bool(platform.get("auto_apr", False)),
        "apr_min_samples": int(platform.get("apr_min_samples", APR_MIN_SAMPLES)),
        "apr_evaluation_interval_seconds": int(platform.get(
            "apr_evaluation_interval_seconds",
            APR_AUTO_EVALUATION_INTERVAL_SECONDS
        )),
        "apr_skip_unchanged_policy": bool(platform.get("apr_skip_unchanged_policy", True)),
        "apr_rollback_enabled": bool(platform.get("apr_rollback_enabled", True)),
        "apr_rollback_latency_increase_pct": float(platform.get("apr_rollback_latency_increase_pct", 10.0)),
        "db_writer": {
            "batch_size": int(db_writer.get("batch_size", 100)),
            "flush_interval": float(db_writer.get("flush_interval", 0.1)),
            "max_queue_size": int(db_writer.get("max_queue_size", 20000)),
        },
    }


def get_db_connection():
    db_dir = os.path.dirname(DB_NAME)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_NAME, timeout=DB_BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_db_writer_stats():
    if not db_manager:
        return {
            "queue_depth": 0,
            "running": False,
            "batch_size": None,
            "flush_interval": None,
        }
    return db_manager.get_stats()


def get_combined_queue_depth():
    callback_backlog = 0
    if queue_monitor:
        callback_backlog = int(queue_monitor.get_queue_stats().get("backlog", 0))
    db_writer_depth = int(get_db_writer_stats().get("queue_depth", 0))
    return callback_backlog + db_writer_depth


def get_database_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA page_count")
    page_count = cur.fetchone()[0]
    cur.execute("PRAGMA page_size")
    page_size = cur.fetchone()[0]
    cur.execute("PRAGMA journal_mode")
    journal_mode = cur.fetchone()[0]
    cur.execute("PRAGMA synchronous")
    synchronous = cur.fetchone()[0]

    table_counts = {}
    for table_name in (
        "sensor_data",
        "unknown_payload_data",
        "mqtt_experiment_log",
        "unknown_schema_profile",
        "apr_policy_log",
    ):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            table_counts[table_name] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            table_counts[table_name] = None

    cur.execute("PRAGMA index_list(sensor_data)")
    sensor_data_indexes = [row[1] for row in cur.fetchall()]
    conn.close()

    return {
        "db_name": DB_NAME,
        "page_count": page_count,
        "page_size": page_size,
        "estimated_size_bytes": page_count * page_size,
        "journal_mode": journal_mode,
        "synchronous": synchronous,
        "table_counts": table_counts,
        "sensor_data_indexes": sensor_data_indexes,
        "writer": get_db_writer_stats(),
    }


def assert_port_available(port, host="0.0.0.0"):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, int(port)))
    except OSError as exc:
        raise RuntimeError(
            f"Port {port} is already in use. Stop the conflicting process "
            f"or run with a different PORT value."
        ) from exc


def check_db_file_health():
    if not os.path.exists(DB_NAME):
        return {"status": "missing", "db_name": DB_NAME}
    conn = sqlite3.connect(DB_NAME, timeout=DB_BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Database integrity check failed: {result}")
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        return {
            "status": "ok",
            "db_name": DB_NAME,
            "journal_mode": journal_mode,
            "size_bytes": os.path.getsize(DB_NAME),
        }
    finally:
        conn.close()


def validate_required_tables():
    required = {
        "users",
        "sites",
        "user_groups",
        "fleets",
        "devices",
        "sensor_definitions",
        "sensor_data",
        "unknown_payload_data",
        "unknown_schema_profile",
        "usi_schema_definitions",
        "apr_policy_log",
        "policy_deployment_log",
        "device_policy_state",
        "fleet_policy_state",
    }
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        existing = {row[0] for row in rows}
        missing = sorted(required - existing)
        if missing:
            raise RuntimeError(f"Required DB tables are missing: {missing}")
        return {"status": "ok", "table_count": len(existing)}
    finally:
        conn.close()


def add_column_if_missing(cur, table_name, column_name, column_type):
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cur.fetchall()]
    if column_name not in columns:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def init_db():
    conn = get_db_connection()
    conn.execute(f"PRAGMA journal_mode={DB_JOURNAL_MODE}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT,
            sensor_type TEXT,
            value REAL,
            unit TEXT,
            timestamp TEXT,
            topic TEXT,
            mode TEXT,
            experiment_id TEXT,
            seq INTEGER,
            publish_timestamp TEXT,
            received_timestamp TEXT,
            measured_latency REAL,
            payload_size INTEGER,
            qos INTEGER,
            compression TEXT,
            encryption TEXT,
            integrity TEXT,
            schema_hash TEXT
        )
    """)

    # Existing DB migration support.
    for col, typ in [
        ("topic", "TEXT"),
        ("mode", "TEXT"),
        ("experiment_id", "TEXT"),
        ("seq", "INTEGER"),
        ("publish_timestamp", "TEXT"),
        ("received_timestamp", "TEXT"),
        ("measured_latency", "REAL"),
        ("payload_size", "INTEGER"),
        ("qos", "INTEGER"),
        ("compression", "TEXT"),
        ("encryption", "TEXT"),
        ("integrity", "TEXT"),
        ("schema_hash", "TEXT"),
    ]:
        add_column_if_missing(cur, "sensor_data", col, typ)

    # 정의되지 않은 payload를 원문 그대로 별도 저장
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unknown_payload_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_text TEXT NOT NULL,
            payload_size INTEGER NOT NULL,
            payload_type TEXT NOT NULL,
            error_message TEXT,
            received_at TEXT NOT NULL,
            experiment_id TEXT,
            seq INTEGER,
            publish_timestamp TEXT,
            received_timestamp TEXT,
            measured_latency REAL,
            qos INTEGER,
            compression TEXT,
            encryption TEXT,
            integrity TEXT,
            schema_hash TEXT
        )
    """)

    for col, typ in [
        ("experiment_id", "TEXT"),
        ("seq", "INTEGER"),
        ("publish_timestamp", "TEXT"),
        ("received_timestamp", "TEXT"),
        ("measured_latency", "REAL"),
        ("qos", "INTEGER"),
        ("compression", "TEXT"),
        ("encryption", "TEXT"),
        ("integrity", "TEXT"),
        ("schema_hash", "TEXT"),
    ]:
        add_column_if_missing(cur, "unknown_payload_data", col, typ)

    # 논문 실험 검증용 통합 로그 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mqtt_experiment_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT,
            topic TEXT,
            sensor_id TEXT,
            sensor_type TEXT,
            seq INTEGER,
            publish_timestamp TEXT,
            received_timestamp TEXT,
            measured_latency REAL,
            payload_size INTEGER,
            qos INTEGER,
            compression TEXT,
            encryption TEXT,
            integrity TEXT,
            apr_policy TEXT,
            predicted_latency REAL,
            is_unknown_schema INTEGER,
            payload_type TEXT,
            payload_text TEXT,
            platform_mode TEXT,
            policy_key TEXT,
            latency_ms REAL,
            schema_hash TEXT,
            created_at TEXT
        )
    """)

    for col, typ in [
        ("platform_mode", "TEXT"),
        ("policy_key", "TEXT"),
        ("latency_ms", "REAL"),
        ("schema_hash", "TEXT"),
        ("created_at", "TEXT"),
    ]:
        add_column_if_missing(cur, "mqtt_experiment_log", col, typ)

    # 미정의 payload schema fingerprint/profile 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unknown_schema_profile (
            schema_hash TEXT PRIMARY KEY,
            payload_type TEXT,
            first_topic TEXT,
            last_topic TEXT,
            schema_keys TEXT,
            key_count INTEGER,
            inferred_fields TEXT,
            semantic_summary TEXT,
            recommended_mapping TEXT,
            confidence_score REAL,
            storage_strategy TEXT,
            sample_payload_text TEXT,
            message_count INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        )
    """)
    for col, typ in [
        ("inferred_fields", "TEXT"),
        ("semantic_summary", "TEXT"),
        ("recommended_mapping", "TEXT"),
        ("confidence_score", "REAL"),
        ("storage_strategy", "TEXT"),
    ]:
        add_column_if_missing(cur, "unknown_schema_profile", col, typ)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usi_schema_definitions (
            schema_hash TEXT PRIMARY KEY,
            display_name TEXT,
            target_type TEXT NOT NULL DEFAULT 'sensor_data',
            status TEXT NOT NULL DEFAULT 'DRAFT',
            field_mapping TEXT NOT NULL,
            storage_strategy TEXT,
            scope_type TEXT NOT NULL DEFAULT 'global',
            scope_id TEXT,
            notes TEXT,
            created_by_user_id INTEGER,
            approved_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            approved_at TEXT,
            FOREIGN KEY(schema_hash) REFERENCES unknown_schema_profile(schema_hash)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usi_def_status ON usi_schema_definitions(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usi_def_target ON usi_schema_definitions(target_type)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usi_mapping_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_hash TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_user_id INTEGER,
            detail_json TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usi_audit_schema ON usi_mapping_audit_log(schema_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usi_audit_created ON usi_mapping_audit_log(created_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS voice_experiment_results (
            experiment_id TEXT PRIMARY KEY,
            scenario TEXT,
            topic TEXT,
            qos INTEGER,
            fps REAL,
            prebuffer_ms INTEGER,
            max_queue_ms INTEGER,
            drop_on INTEGER,
            duration_s INTEGER,
            received_frames INTEGER,
            played_ticks INTEGER,
            played_frames INTEGER,
            gap_inserted INTEGER,
            gap_ratio_pct REAL,
            latency_avg_ms REAL,
            latency_p95_ms REAL,
            latency_p99_ms REAL,
            latency_max_ms REAL,
            jitter_ms REAL,
            created_at TEXT
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_topic ON sensor_data(topic)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_id ON sensor_data(sensor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_received ON sensor_data(received_timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_received ON sensor_data(sensor_id, received_timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_data_experiment_seq ON sensor_data(experiment_id, seq)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unknown_payload_topic ON unknown_payload_data(topic)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unknown_payload_received_at ON unknown_payload_data(received_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unknown_payload_topic_received ON unknown_payload_data(topic, received_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_experiment_id ON mqtt_experiment_log(experiment_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_topic ON mqtt_experiment_log(topic)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_received ON mqtt_experiment_log(received_timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_experiment_seq ON mqtt_experiment_log(experiment_id, seq)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_policy_key ON mqtt_experiment_log(policy_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_exp_log_payload_type ON mqtt_experiment_log(payload_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unknown_payload_schema_hash ON unknown_payload_data(schema_hash)")

    # APR 정책 결정 이력 및 피드백 결과 추적 테이블
    cur.execute("""
        CREATE TABLE IF NOT EXISTS apr_policy_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            sample_count INTEGER,
            before_avg_latency_ms REAL,
            before_avg_payload_size REAL,
            before_avg_queue_depth REAL,
            before_policy TEXT,
            new_policy TEXT NOT NULL,
            after_avg_latency_ms REAL,
            after_avg_payload_size REAL,
            after_avg_queue_depth REAL,
            after_sample_count INTEGER,
            feedback_status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_apr_policy_log_sensor ON apr_policy_log(sensor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_apr_policy_log_decided ON apr_policy_log(decided_at)")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_schema_profile_last_seen ON unknown_schema_profile(last_seen)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            topic_name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sites_topic ON sites(topic_name)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            topic_path TEXT NOT NULL,
            description TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(site_id) REFERENCES sites(id)
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_groups_site_name ON user_groups(site_id, name)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_groups_site_topic ON user_groups(site_id, topic_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_groups_site ON user_groups(site_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_groups_topic_path ON user_groups(topic_path)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            role TEXT NOT NULL DEFAULT 'USER',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL
        )
    """)
    for col, typ in [
        ("site_id", "INTEGER"),
        ("group_id", "INTEGER"),
        ("user_topic_name", "TEXT"),
        ("user_topic_path", "TEXT"),
    ]:
        add_column_if_missing(cur, "users", col, typ)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_site ON users(site_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_group ON users(group_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT,
            event_type TEXT NOT NULL,
            failure_reason TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_user ON access_logs(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_access_logs_created ON access_logs(created_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id TEXT,
            detail_json TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor_user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fleets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            owner_user_id INTEGER NOT NULL,
            topic_name TEXT,
            topic_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
    """)
    for col, typ in [
        ("topic_name", "TEXT"),
        ("topic_path", "TEXT"),
    ]:
        add_column_if_missing(cur, "fleets", col, typ)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_fleets_owner_name ON fleets(owner_user_id, name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fleets_owner ON fleets(owner_user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fleets_topic_path ON fleets(topic_path)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            device_type TEXT,
            device_os TEXT,
            fleet_id INTEGER,
            owner_user_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            topic_prefix TEXT,
            telemetry_topic TEXT,
            policy_topic TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(fleet_id) REFERENCES fleets(id),
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
    """)
    add_column_if_missing(cur, "devices", "device_os", "TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_owner ON devices(owner_user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_fleet ON devices(fleet_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_devices_device_id ON devices(device_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sensor_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sensor_id TEXT NOT NULL UNIQUE,
            sensor_type TEXT NOT NULL,
            unit TEXT,
            topic TEXT NOT NULL UNIQUE,
            definition_source TEXT NOT NULL DEFAULT 'SIMULATOR',
            owner_user_id INTEGER,
            payload_schema_mode TEXT NOT NULL DEFAULT 'defined_sensor',
            policy TEXT NOT NULL DEFAULT 'none',
            min_value REAL,
            max_value REAL,
            start_value REAL,
            step_value REAL,
            interval_seconds REAL,
            simulation_mode TEXT,
            color_rule_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(owner_user_id) REFERENCES users(id)
        )
    """)
    add_column_if_missing(cur, "sensor_definitions", "definition_source", "TEXT NOT NULL DEFAULT 'SIMULATOR'")
    add_column_if_missing(cur, "sensor_definitions", "owner_user_id", "INTEGER")
    cur.execute("""
        UPDATE sensor_definitions
        SET definition_source = 'SIMULATOR'
        WHERE definition_source IS NULL OR TRIM(definition_source) = ''
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_definitions_type ON sensor_definitions(sensor_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_definitions_enabled ON sensor_definitions(enabled)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_definitions_topic ON sensor_definitions(topic)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_definitions_source ON sensor_definitions(definition_source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sensor_definitions_owner ON sensor_definitions(owner_user_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS device_policy_state (
            device_row_id INTEGER PRIMARY KEY,
            policy_json TEXT NOT NULL,
            source TEXT NOT NULL,
            applied_by_user_id INTEGER,
            applied_at TEXT NOT NULL,
            published_topic TEXT,
            publish_status TEXT NOT NULL,
            last_error TEXT,
            FOREIGN KEY(device_row_id) REFERENCES devices(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_device_policy_applied ON device_policy_state(applied_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fleet_policy_state (
            fleet_id INTEGER PRIMARY KEY,
            policy_json TEXT NOT NULL,
            source TEXT NOT NULL,
            applied_by_user_id INTEGER,
            applied_at TEXT NOT NULL,
            publish_status TEXT NOT NULL,
            last_error TEXT,
            FOREIGN KEY(fleet_id) REFERENCES fleets(id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_fleet_policy_applied ON fleet_policy_state(applied_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS policy_deployment_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            device_row_id INTEGER,
            device_id TEXT,
            policy_json TEXT NOT NULL,
            source TEXT NOT NULL,
            published_topic TEXT,
            publish_status TEXT NOT NULL,
            last_error TEXT,
            actor_user_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_policy_log_target ON policy_deployment_log(target_type, target_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_policy_log_device ON policy_deployment_log(device_row_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_policy_log_created ON policy_deployment_log(created_at)")

    default_site_id, default_group_id, default_group_path = get_default_site_group(cur)

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        admin_email = os.environ.get("IOT_ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("IOT_ADMIN_PASSWORD", "admin1234")
        user_email = os.environ.get("IOT_USER_EMAIL", "user@example.com")
        user_password = os.environ.get("IOT_USER_PASSWORD", "user1234")
        created_at = now_iso()
        cur.execute("""
            INSERT INTO users
            (name, email, password_hash, company, phone, role, status, site_id, group_id,
             user_topic_name, user_topic_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "Administrator",
            admin_email,
            generate_password_hash(admin_password),
            "APR Platform",
            "",
            "ADMIN",
            "ACTIVE",
            default_site_id,
            default_group_id,
            default_user_topic_name("Administrator"),
            build_user_topic_path(default_group_path, default_user_topic_name("Administrator")),
            created_at,
        ))
        cur.execute("""
            INSERT INTO users
            (name, email, password_hash, company, phone, role, status, site_id, group_id,
             user_topic_name, user_topic_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "General User",
            user_email,
            generate_password_hash(user_password),
            "APR Platform",
            "",
            "USER",
            "ACTIVE",
            default_site_id,
            default_group_id,
            default_user_topic_name("General User"),
            build_user_topic_path(default_group_path, default_user_topic_name("General User")),
            created_at,
        ))

    cur.execute("""
        SELECT u.id, u.name
        FROM users u
        LEFT JOIN user_groups g ON g.id = u.group_id
        WHERE u.site_id IS NULL
           OR u.group_id IS NULL
           OR g.id IS NULL
           OR u.user_topic_name IS NULL
           OR trim(u.user_topic_name) = ''
           OR u.user_topic_path IS NULL
           OR trim(u.user_topic_path) = ''
    """)
    for user_id, user_name in cur.fetchall():
        topic_name = default_user_topic_name(user_name)
        cur.execute("""
            UPDATE users
            SET site_id = COALESCE(site_id, ?),
                group_id = ?,
                user_topic_name = CASE
                    WHEN user_topic_name IS NULL OR trim(user_topic_name) = '' THEN ?
                    ELSE user_topic_name
                END,
                user_topic_path = ?
            WHERE id = ?
        """, (
            default_site_id,
            default_group_id,
            topic_name,
            build_user_topic_path(default_group_path, topic_name),
            user_id,
        ))

    cur.execute("""
        INSERT OR IGNORE INTO fleets (name, description, owner_user_id, created_at, updated_at)
        SELECT 'Default Fleet', 'Default fleet for registered devices', id, ?, ?
        FROM users
    """, (now_iso(), now_iso()))

    cur.execute("""
        SELECT f.id, f.name, u.user_topic_path
        FROM fleets f
        JOIN users u ON u.id = f.owner_user_id
        WHERE f.topic_name IS NULL
           OR trim(f.topic_name) = ''
           OR f.topic_path IS NULL
           OR trim(f.topic_path) = ''
    """)
    for fleet_id, fleet_name, user_topic_path in cur.fetchall():
        topic_name = normalize_topic_part(fleet_name, "fleet")
        topic_path = build_fleet_topic_path(user_topic_path or default_group_path, fleet_name)
        cur.execute("""
            UPDATE fleets
            SET topic_name = ?, topic_path = ?, updated_at = COALESCE(updated_at, ?)
            WHERE id = ?
        """, (topic_name, topic_path, now_iso(), fleet_id))

    config = load_config()
    legacy_sensors = config.get("sensors", [])
    cur.execute("SELECT COUNT(*) FROM sensor_definitions")
    if cur.fetchone()[0] == 0:
        for sensor in legacy_sensors:
            sensor_id = str(sensor.get("id") or "").strip()
            sensor_type = str(sensor.get("type") or "").strip()
            if not sensor_id or not sensor_type:
                continue
            topic = str(sensor.get("topic") or "").strip()
            if not topic:
                topic = f"{config.get('mqtt', {}).get('topic_prefix', 'iot/sensor')}/{sensor_type}/{sensor_id}"
            cur.execute("""
                INSERT OR IGNORE INTO sensor_definitions
                (sensor_id, sensor_type, unit, topic, definition_source, owner_user_id,
                 payload_schema_mode, policy,
                 min_value, max_value, start_value, step_value, interval_seconds,
                 simulation_mode, color_rule_json, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'SIMULATOR', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (
                sensor_id,
                sensor_type,
                sensor.get("unit"),
                topic,
                sensor.get("payload_schema_mode") or "defined_sensor",
                sensor.get("policy") or "none",
                sensor.get("min"),
                sensor.get("max"),
                sensor.get("start"),
                sensor.get("step"),
                sensor.get("interval"),
                sensor.get("mode"),
                json.dumps(sensor.get("color_rule"), ensure_ascii=False) if sensor.get("color_rule") else None,
                now_iso(),
                now_iso(),
            ))

    conn.commit()
    conn.close()
    if "sensors" in config:
        config.pop("sensors", None)
        save_config(config)


def flatten_schema_keys(value, prefix=""):
    keys = []
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(path)
            keys.extend(flatten_schema_keys(value[key], path))
    elif isinstance(value, list):
        keys.append(f"{prefix}[]")
        if value:
            keys.extend(flatten_schema_keys(value[0], f"{prefix}[]"))
    else:
        keys.append(f"{prefix}:{type(value).__name__}")
    return keys


def calc_schema_hash(data):
    if not isinstance(data, dict):
        return None
    schema_text = "|".join(flatten_schema_keys(data))
    return hashlib.sha256(schema_text.encode("utf-8")).hexdigest()[:16]


def calc_payload_fingerprint(payload_text):
    return hashlib.sha256(str(payload_text).encode("utf-8", errors="replace")).hexdigest()[:16]


def get_schema_keys_text(data):
    if not isinstance(data, dict):
        return ""
    keys = flatten_schema_keys(data)
    return json.dumps(keys, ensure_ascii=False)


SEMANTIC_ALIASES = {
    "sensor_id": ("sensor_id", "sensor", "sensorid", "id", "device_id", "deviceid", "client_id"),
    "sensor_type": ("sensor_type", "type", "kind", "metric", "metric_name"),
    "value": ("value", "val", "reading", "measurement", "data", "temperature", "temp", "humidity", "humi", "pressure", "vibration", "cpu", "memory", "mem"),
    "unit": ("unit", "units", "uom"),
    "timestamp": ("timestamp", "time", "ts", "publish_timestamp", "created_at", "datetime"),
    "sequence": ("seq", "sequence", "sequence_id", "counter"),
    "policy": ("policy", "qos", "compression", "encryption", "integrity"),
    "system_cpu": ("cpu", "cpu_percent", "cpu_usage", "load"),
    "system_memory": ("memory", "mem", "ram", "memory_percent", "mem_usage"),
    "system_temperature": ("temperature", "temp", "cpu_temp", "board_temp"),
}


def semantic_role_for_path(path):
    leaf = path.split(".")[-1].replace("[]", "").lower()
    normalized = re.sub(r"[^a-z0-9_]", "_", leaf)
    for role, aliases in SEMANTIC_ALIASES.items():
        if normalized in aliases:
            return role
    for role, aliases in SEMANTIC_ALIASES.items():
        if any(alias and alias in normalized for alias in aliases if len(alias) >= 3):
            return role
    return "unknown"


def infer_value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return "string"
        try:
            float(stripped)
            return "numeric_string"
        except ValueError:
            return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def collect_inferred_fields(value, prefix=""):
    fields = []
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            path = f"{prefix}.{key}" if prefix else str(key)
            child = value[key]
            if isinstance(child, dict):
                fields.append({
                    "path": path,
                    "type": "object",
                    "semantic_role": semantic_role_for_path(path),
                    "sample": None,
                })
                fields.extend(collect_inferred_fields(child, path))
            elif isinstance(child, list):
                sample = child[0] if child else None
                fields.append({
                    "path": f"{path}[]",
                    "type": f"array<{infer_value_type(sample)}>",
                    "semantic_role": semantic_role_for_path(path),
                    "sample": sample if not isinstance(sample, (dict, list)) else None,
                })
                if isinstance(sample, (dict, list)):
                    fields.extend(collect_inferred_fields(sample, f"{path}[]"))
            else:
                fields.append({
                    "path": path,
                    "type": infer_value_type(child),
                    "semantic_role": semantic_role_for_path(path),
                    "sample": child,
                })
    return fields


def build_semantic_summary(fields):
    roles = {}
    for field in fields:
        role = field.get("semantic_role") or "unknown"
        roles.setdefault(role, 0)
        roles[role] += 1
    known_roles = sorted([role for role in roles if role != "unknown"])
    return {
        "known_roles": known_roles,
        "unknown_field_count": roles.get("unknown", 0),
        "field_count": len(fields),
        "role_counts": roles,
    }


def build_recommended_mapping(fields, data):
    by_role = {}
    for field in fields:
        role = field.get("semantic_role")
        if role and role != "unknown":
            by_role.setdefault(role, field)

    mapping = {}
    confidence = 0.15
    if "sensor_id" in by_role:
        mapping["sensor_id"] = by_role["sensor_id"]["path"]
        confidence += 0.2
    if "sensor_type" in by_role:
        mapping["sensor_type"] = by_role["sensor_type"]["path"]
        confidence += 0.15
    if "value" in by_role:
        mapping["value"] = by_role["value"]["path"]
        confidence += 0.25
    if "unit" in by_role:
        mapping["unit"] = by_role["unit"]["path"]
        confidence += 0.1
    if "timestamp" in by_role:
        mapping["timestamp"] = by_role["timestamp"]["path"]
        confidence += 0.1
    if any(role in by_role for role in ("system_cpu", "system_memory", "system_temperature")):
        confidence += 0.1
        mapping["profile"] = "system_metrics"

    storage_strategy = "unknown_payload_data"
    promotion = "none"
    if {"sensor_id", "value"}.issubset(mapping.keys()):
        storage_strategy = "sensor_data_candidate"
        promotion = "defined_sensor_candidate"
    elif mapping.get("profile") == "system_metrics":
        storage_strategy = "system_metrics_candidate"
        promotion = "device_metrics_candidate"
    elif isinstance(data, dict):
        storage_strategy = "flexible_json_profile"

    return {
        "promotion": promotion,
        "storage_strategy": storage_strategy,
        "field_mapping": mapping,
        "confidence": round(min(confidence, 0.98), 3),
        "notes": "Review before promoting unknown payloads to a defined schema.",
    }


def infer_unknown_schema(data, payload_text, payload_type, meta=None):
    fields = collect_inferred_fields(data) if isinstance(data, dict) else []
    summary = build_semantic_summary(fields)
    mapping = build_recommended_mapping(fields, data) if isinstance(data, dict) else {
        "promotion": "none",
        "storage_strategy": "raw_payload",
        "field_mapping": {},
        "confidence": 0.05,
        "notes": "Payload is not JSON; store as raw payload.",
    }
    return {
        "fields": fields,
        "summary": summary,
        "mapping": mapping,
        "confidence": mapping.get("confidence", 0.0),
        "storage_strategy": mapping.get("storage_strategy", "unknown_payload_data"),
    }


USI_ALLOWED_TARGET_TYPES = {
    "sensor_data",
    "device_metrics",
    "adaptive_json",
    "raw_payload",
}


USI_ALLOWED_STATUSES = {
    "DRAFT",
    "APPROVED",
    "REJECTED",
}


def fetch_usi_definition(schema_hash):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_hash, display_name, target_type, status, field_mapping,
               storage_strategy, scope_type, scope_id, notes, created_by_user_id,
               approved_by_user_id, created_at, updated_at, approved_at
        FROM usi_schema_definitions
        WHERE schema_hash = ?
    """, (schema_hash,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "schema_hash": row[0],
        "display_name": row[1],
        "target_type": row[2],
        "status": row[3],
        "field_mapping": safe_json_loads(row[4]) or {},
        "storage_strategy": row[5],
        "scope_type": row[6],
        "scope_id": row[7],
        "notes": row[8],
        "created_by_user_id": row[9],
        "approved_by_user_id": row[10],
        "created_at": row[11],
        "updated_at": row[12],
        "approved_at": row[13],
    }


def validate_usi_definition_payload(data, require_mapping=True):
    target_type = (data.get("target_type") or "sensor_data").strip()
    if target_type not in USI_ALLOWED_TARGET_TYPES:
        raise ValueError("invalid_target_type")
    field_mapping = data.get("field_mapping") or {}
    if not isinstance(field_mapping, dict):
        raise ValueError("invalid_field_mapping")
    if require_mapping and target_type == "sensor_data":
        required = ("sensor_id", "value")
        missing = [key for key in required if not field_mapping.get(key)]
        if missing:
            raise ValueError(f"missing_required_mapping:{','.join(missing)}")
    if require_mapping and target_type == "device_metrics":
        if not any(field_mapping.get(key) for key in ("cpu", "memory", "temperature", "value")):
            raise ValueError("missing_device_metric_mapping")
    scope_type = (data.get("scope_type") or "global").strip()
    if scope_type not in ("global", "site", "group", "user", "fleet", "device"):
        raise ValueError("invalid_scope_type")
    return {
        "display_name": (data.get("display_name") or "").strip(),
        "target_type": target_type,
        "field_mapping": field_mapping,
        "storage_strategy": (data.get("storage_strategy") or target_type).strip(),
        "scope_type": scope_type,
        "scope_id": str(data.get("scope_id") or "").strip() or None,
        "notes": (data.get("notes") or "").strip(),
    }


def log_usi_mapping_action(cur, schema_hash, action, detail=None):
    cur.execute("""
        INSERT INTO usi_mapping_audit_log
        (schema_hash, action, actor_user_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        schema_hash,
        action,
        current_user_id(),
        json.dumps(detail or {}, ensure_ascii=False),
        now_iso(),
    ))


def upsert_unknown_schema_profile(meta, payload_type, payload_text, data=None):
    schema_hash = meta.get("schema_hash") or calc_payload_fingerprint(payload_text)
    received_at = meta.get("received_timestamp") or now_iso()
    schema_keys = get_schema_keys_text(data) if isinstance(data, dict) else ""
    key_count = len(json.loads(schema_keys)) if schema_keys else 0
    payload_size = int(meta.get("payload_size") or len(payload_text.encode("utf-8")))
    inference = infer_unknown_schema(data, payload_text, payload_type, meta)
    inferred_fields = json.dumps(inference["fields"], ensure_ascii=False)
    semantic_summary = json.dumps(inference["summary"], ensure_ascii=False)
    recommended_mapping = json.dumps(inference["mapping"], ensure_ascii=False)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO unknown_schema_profile
        (schema_hash, payload_type, first_topic, last_topic, schema_keys, key_count,
         inferred_fields, semantic_summary, recommended_mapping, confidence_score,
         storage_strategy, sample_payload_text, message_count, total_bytes, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(schema_hash) DO UPDATE SET
            payload_type = excluded.payload_type,
            last_topic = excluded.last_topic,
            schema_keys = CASE
                WHEN excluded.schema_keys != '' THEN excluded.schema_keys
                ELSE unknown_schema_profile.schema_keys
            END,
            key_count = CASE
                WHEN excluded.key_count > 0 THEN excluded.key_count
                ELSE unknown_schema_profile.key_count
            END,
            inferred_fields = excluded.inferred_fields,
            semantic_summary = excluded.semantic_summary,
            recommended_mapping = excluded.recommended_mapping,
            confidence_score = excluded.confidence_score,
            storage_strategy = excluded.storage_strategy,
            sample_payload_text = CASE
                WHEN unknown_schema_profile.sample_payload_text IS NULL OR unknown_schema_profile.sample_payload_text = ''
                THEN excluded.sample_payload_text
                ELSE unknown_schema_profile.sample_payload_text
            END,
            message_count = unknown_schema_profile.message_count + 1,
            total_bytes = unknown_schema_profile.total_bytes + excluded.total_bytes,
            last_seen = excluded.last_seen
    """, (
        schema_hash,
        payload_type,
        meta.get("topic"),
        meta.get("topic"),
        schema_keys,
        key_count,
        inferred_fields,
        semantic_summary,
        recommended_mapping,
        inference["confidence"],
        inference["storage_strategy"],
        payload_text[:2000],
        payload_size,
        received_at,
        received_at,
    ))
    conn.commit()
    conn.close()


def build_policy_key(qos, compression, encryption, integrity):
    return f"qos={qos}|comp={compression or 'none'}|enc={encryption or 'none'}|int={integrity or 'none'}"


def normalize_policy(policy):
    if not isinstance(policy, dict):
        return None
    return {
        "qos": int(policy.get("qos", 0) or 0),
        "compression": policy.get("compression", "none") or "none",
        "encryption": policy.get("encryption", "none") or "none",
        "integrity": policy.get("integrity", "none") or "none",
    }


def policies_equal(left, right):
    return normalize_policy(left) == normalize_policy(right)


def publish_policy_to_topic(policy_topic, policy):
    config = load_config()
    normalized = normalize_policy(policy)
    if normalized is None:
        raise ValueError("invalid_policy")
    if apr_mqtt_client and apr_mqtt_client.is_connected():
        result = apr_mqtt_client.publish(policy_topic, json.dumps(normalized), qos=1)
        result.wait_for_publish(timeout=5)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            return policy_topic, normalized
        raise ConnectionError(f"active MQTT client publish failed: rc={result.rc}")
    if publish_single_to_any_broker:
        publish_single_to_any_broker(policy_topic, json.dumps(normalized), config.get("mqtt", {}), qos=1)
    else:
        import paho.mqtt.publish as mqtt_publish
        mqtt_publish.single(
            policy_topic,
            payload=json.dumps(normalized),
            hostname=config["mqtt"]["broker"],
            port=config["mqtt"]["port"],
            qos=1
        )
    return policy_topic, normalized


def publish_policy_to_device(sensor_id, policy):
    policy_topic = f"iot/sensor/policy/{sensor_id}"
    return publish_policy_to_topic(policy_topic, policy)


def validate_policy_payload(policy):
    normalized = normalize_policy(policy)
    if normalized is None:
        raise ValueError("policy_required")
    if normalized["qos"] not in (0, 1, 2):
        raise ValueError("invalid_qos")
    if normalized["compression"] not in ("none", "gzip", "zlib", "bz2"):
        raise ValueError("invalid_compression")
    if normalized["encryption"] not in ("none", "AES-GCM", "ChaCha20-Poly1305"):
        raise ValueError("invalid_encryption")
    if normalized["integrity"] not in ("none", "sha256", "SHA-256"):
        raise ValueError("invalid_integrity")
    if normalized["integrity"] == "SHA-256":
        normalized["integrity"] = "sha256"
    return normalized


def recommend_policy_from_runtime(data, topic):
    if apr_engine is None:
        raise RuntimeError("apr_engine_not_available")
    payload_size = int(data.get("payload_size") or data.get("data_size_pub") or 0)
    network_latency_ms = float(data.get("network_latency_ms") or data.get("pub_ping") or 0.0)
    queue_depth = int(data.get("queue_depth") or get_combined_queue_depth())
    schema_type = data.get("schema_type") or "standard"
    return validate_policy_payload(apr_engine.recommend(payload_size, network_latency_ms, queue_depth, topic, schema_type))


def fetch_device_policy_target(row_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.device_id, d.device_name, d.fleet_id, d.owner_user_id,
               d.policy_topic, d.topic_prefix, d.telemetry_topic
        FROM devices d
        WHERE d.id = ?
    """, (row_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "device_id": row[1],
        "device_name": row[2],
        "fleet_id": row[3],
        "owner_user_id": row[4],
        "policy_topic": row[5] or f"{POLICY_TOPIC_PREFIX}{row[1]}",
        "topic_prefix": row[6],
        "telemetry_topic": row[7],
    }


def fetch_fleet_policy_target(fleet_id):
    row = fetch_fleet_row(fleet_id)
    if not row:
        return None
    return serialize_fleet(row)


def log_policy_deployment(cur, target_type, target_id, device, policy, source, topic, status, error):
    cur.execute("""
        INSERT INTO policy_deployment_log
        (target_type, target_id, device_row_id, device_id, policy_json, source,
         published_topic, publish_status, last_error, actor_user_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        target_type,
        target_id,
        device.get("id") if device else None,
        device.get("device_id") if device else None,
        json.dumps(policy, ensure_ascii=False),
        source,
        topic,
        status,
        error,
        current_user_id(),
        now_iso(),
    ))


def apply_policy_to_device_target(device, policy, source="manual"):
    topic = device.get("policy_topic") or f"{POLICY_TOPIC_PREFIX}{device['device_id']}"
    status = "success"
    error = None
    published_topic = topic
    normalized = validate_policy_payload(policy)
    try:
        published_topic, normalized = publish_policy_to_topic(topic, normalized)
        apr_policy_cache[device["device_id"]] = normalized
    except Exception as exc:
        status = "failed"
        error = str(exc)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO device_policy_state
        (device_row_id, policy_json, source, applied_by_user_id, applied_at,
         published_topic, publish_status, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(device_row_id) DO UPDATE SET
            policy_json = excluded.policy_json,
            source = excluded.source,
            applied_by_user_id = excluded.applied_by_user_id,
            applied_at = excluded.applied_at,
            published_topic = excluded.published_topic,
            publish_status = excluded.publish_status,
            last_error = excluded.last_error
    """, (
        device["id"],
        json.dumps(normalized, ensure_ascii=False),
        source,
        current_user_id(),
        now_iso(),
        published_topic,
        status,
        error,
    ))
    log_policy_deployment(cur, "device", device["id"], device, normalized, source, published_topic, status, error)
    conn.commit()
    conn.close()
    return {
        "device_id": device["device_id"],
        "device_row_id": device["id"],
        "policy": normalized,
        "published_topic": published_topic,
        "publish_status": status,
        "last_error": error,
    }


def get_policy(data):
    policy = data.get("policy") if isinstance(data, dict) else None
    if not isinstance(policy, dict):
        policy = {}
    return {
        "qos": policy.get("qos"),
        "compression": policy.get("compression", "none"),
        "encryption": policy.get("encryption", "none"),
        "integrity": policy.get("integrity", "none"),
    }


def extract_common_metadata(data, topic, payload_text, received_timestamp, metadata_header=None):
    if not isinstance(data, dict):
        data = {}
        
    if metadata_header:
        policy = {
            "qos": metadata_header.get("qos"),
            "compression": metadata_header.get("compression", "none"),
            "encryption": metadata_header.get("encryption", "none"),
            "integrity": metadata_header.get("integrity", "none"),
        }
        publish_timestamp = metadata_header.get("publish_timestamp")
        experiment_id = metadata_header.get("experiment_id")
        seq = metadata_header.get("seq")
        hash_val = metadata_header.get("hash")
    else:
        policy = get_policy(data)
        publish_timestamp = data.get("publish_timestamp") or data.get("timestamp")
        experiment_id = data.get("experiment_id")
        seq = data.get("seq")
        hash_val = None
        
    return {
        "experiment_id": experiment_id,
        "topic": data.get("topic") or topic,
        "sensor_id": data.get("sensor_id"),
        "sensor_type": data.get("sensor_type"),
        "seq": seq,
        "publish_timestamp": publish_timestamp,
        "received_timestamp": received_timestamp,
        "measured_latency": calc_latency_seconds(publish_timestamp, received_timestamp),
        "payload_size": len(payload_text.encode("utf-8")),
        "qos": policy.get("qos"),
        "compression": policy.get("compression"),
        "encryption": policy.get("encryption"),
        "integrity": policy.get("integrity"),
        "apr_policy": json.dumps(data.get("apr_policy"), ensure_ascii=False) if data.get("apr_policy") is not None else None,
        "predicted_latency": data.get("predicted_latency"),
        "platform_mode": data.get("platform_mode") or data.get("mode"),
        "schema_hash": hash_val or calc_schema_hash(data),
    }


def is_defined_sensor_payload(data):
    """현재 시스템에서 정의된 센서 payload 형식인지 검사한다."""
    if not isinstance(data, dict):
        return False

    if not DEFINED_SENSOR_REQUIRED_FIELDS.issubset(data.keys()):
        return False

    try:
        float(data.get("value"))
    except (TypeError, ValueError):
        return False

    return True


def insert_experiment_log(meta, payload_type, is_unknown_schema, payload_text=None):
    runtime = get_platform_runtime_config()
    if db_manager:
        db_manager.insert_experiment_log(
            meta, payload_type, is_unknown_schema, payload_text,
            runtime_mode=runtime.get("mode"),
            enable_log=runtime["enable_experiment_log"]
        )
        return

    if not runtime["enable_experiment_log"]:
        return

    latency = meta.get("measured_latency")
    latency_ms = round(float(latency) * 1000, 3) if latency is not None else None
    platform_mode = meta.get("platform_mode") or runtime.get("mode")
    experiment_id = meta.get("experiment_id") or runtime.get("experiment_id")
    policy_key = build_policy_key(
        meta.get("qos"),
        meta.get("compression"),
        meta.get("encryption"),
        meta.get("integrity"),
    )

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO mqtt_experiment_log
        (experiment_id, topic, sensor_id, sensor_type, seq,
         publish_timestamp, received_timestamp, measured_latency,
         payload_size, qos, compression, encryption, integrity,
         apr_policy, predicted_latency, is_unknown_schema,
         payload_type, payload_text, platform_mode, policy_key,
         latency_ms, schema_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        experiment_id,
        meta.get("topic"),
        meta.get("sensor_id"),
        meta.get("sensor_type"),
        meta.get("seq"),
        meta.get("publish_timestamp"),
        meta.get("received_timestamp"),
        meta.get("measured_latency"),
        meta.get("payload_size"),
        meta.get("qos"),
        meta.get("compression"),
        meta.get("encryption"),
        meta.get("integrity"),
        meta.get("apr_policy"),
        meta.get("predicted_latency"),
        1 if is_unknown_schema else 0,
        payload_type,
        payload_text,
        platform_mode,
        policy_key,
        latency_ms,
        meta.get("schema_hash"),
        now_iso(),
    ))
    conn.commit()
    conn.close()


def insert_sensor_data(data, meta):
    if db_manager:
        db_manager.insert_sensor_data(data, meta)
        return

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sensor_data
        (sensor_id, sensor_type, value, unit, topic, mode, timestamp,
         experiment_id, seq, publish_timestamp, received_timestamp,
         measured_latency, payload_size, qos, compression, encryption, integrity, schema_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("sensor_id"),
        data.get("sensor_type"),
        float(data.get("value")),
        data.get("unit"),
        meta.get("topic"),
        data.get("mode"),
        data.get("timestamp") or data.get("publish_timestamp"),
        meta.get("experiment_id"),
        meta.get("seq"),
        meta.get("publish_timestamp"),
        meta.get("received_timestamp"),
        meta.get("measured_latency"),
        meta.get("payload_size"),
        meta.get("qos"),
        meta.get("compression"),
        meta.get("encryption"),
        meta.get("integrity"),
        meta.get("schema_hash"),
    ))

    conn.commit()
    conn.close()


def insert_unknown_payload(topic, payload_text, payload_type="unknown", error_message=None, meta=None):
    if db_manager:
        db_manager.insert_unknown_payload(topic, payload_text, payload_type, error_message, meta)
        return

    if meta is None:
        received_timestamp = now_iso()
        meta = extract_common_metadata({}, topic, payload_text, received_timestamp)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO unknown_payload_data
        (topic, payload_text, payload_size, payload_type, error_message, received_at,
         experiment_id, seq, publish_timestamp, received_timestamp,
         measured_latency, qos, compression, encryption, integrity, schema_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        topic,
        payload_text,
        meta.get("payload_size"),
        payload_type,
        error_message,
        meta.get("received_timestamp"),
        meta.get("experiment_id"),
        meta.get("seq"),
        meta.get("publish_timestamp"),
        meta.get("received_timestamp"),
        meta.get("measured_latency"),
        meta.get("qos"),
        meta.get("compression"),
        meta.get("encryption"),
        meta.get("integrity"),
        meta.get("schema_hash"),
    ))

    conn.commit()
    conn.close()


def on_connect(client, userdata, flags, rc):
    print("MQTT connected:", rc)
    client.subscribe("iot/sensor/#")


def on_message(client, userdata, msg):
    start_time = time.time()
    topic = msg.topic

    if topic.startswith(POLICY_TOPIC_PREFIX):
        return
    
    if queue_monitor:
        queue_monitor.record_receive(topic)
        
    received_timestamp = now_iso()
    payload_text = msg.payload.decode("utf-8", errors="replace")

    try:
        data = json.loads(payload_text)
    except json.JSONDecodeError as e:
        meta = extract_common_metadata({}, topic, payload_text, received_timestamp)
        meta["schema_hash"] = calc_payload_fingerprint(payload_text)
        upsert_unknown_schema_profile(meta, "non_json", payload_text, None)
        insert_unknown_payload(
            topic=topic,
            payload_text=payload_text,
            payload_type="non_json",
            error_message=str(e),
            meta=meta
        )
        insert_experiment_log(meta, "non_json", True, payload_text)
        print("Unknown non-JSON payload saved:", topic, payload_text)
        return

    # Check if this is an APR dynamic envelope
    is_encoded = False
    metadata_header = None
    if isinstance(data, dict) and "metadata" in data and "data" in data:
        metadata_header = data["metadata"]
        if isinstance(metadata_header, dict) and ("compression" in metadata_header or "encryption" in metadata_header):
            is_encoded = True
            
    if is_encoded and decode_payload:
        try:
            decoded_data = decode_payload(metadata_header, data["data"])
            # Replace the outer data with the decoded inner JSON dict
            data = decoded_data
        except Exception as e:
            meta = extract_common_metadata({}, topic, payload_text, received_timestamp, metadata_header=metadata_header)
            meta["schema_hash"] = calc_payload_fingerprint(payload_text)
            insert_unknown_payload(
                topic=topic,
                payload_text=payload_text,
                payload_type="decryption_failed",
                error_message=str(e),
                meta=meta
            )
            insert_experiment_log(meta, "decryption_failed", True, payload_text)
            print("Decryption/Decompression failed for payload:", topic, e)
            return

    meta = extract_common_metadata(data, topic, payload_text, received_timestamp, metadata_header=metadata_header)

    if is_defined_sensor_payload(data):
        insert_sensor_data(data, meta)
        insert_experiment_log(meta, "defined_sensor", False, None)
        print("Received sensor data:", data, "latency=", meta.get("measured_latency"))
    else:
        insert_unknown_payload(
            topic=topic,
            payload_text=payload_text,
            payload_type="json_undefined_schema",
            error_message="Payload schema does not match defined sensor_data format",
            meta=meta
        )
        upsert_unknown_schema_profile(meta, "json_undefined_schema", payload_text, data)
        insert_experiment_log(meta, "json_undefined_schema", True, payload_text)
        print("Unknown JSON payload saved:", topic, data, "latency=", meta.get("measured_latency"))

    # 관리자 트리거 수집 모드: 활성화된 경우만 메트릭 버퍼링
    try:
        apr_collect_metrics(topic, payload_text, meta, data)
    except Exception as e:
        print(f"[APR Collect] 오류: {e}")

    if queue_monitor:
        delay_ms = (time.time() - start_time) * 1000.0
        queue_monitor.record_processed(delay_ms)


def apr_collect_metrics(topic: str, payload_text: str, meta: dict, data: dict):
    """
    관리자 트리거 시 수집 모드(collection mode)에서만 메트릭을 버퍼에 누적한다.
    수집 모드가 꺼져 있으면 아무것도 하지 않는다.
    """
    global apr_collection_active, apr_metrics_buffer, apr_auto_last_evaluation_at

    if apr_engine is None:
        return

    sensor_id = topic.split('/')[-1]
    runtime = get_platform_runtime_config()
    auto_enabled = runtime.get("enable_apr") and runtime.get("auto_apr")
    manual_enabled = apr_collection_active.get(sensor_id, False)

    # 수동 수집 모드 또는 자동 APR 모드일 때 메트릭을 누적한다.
    if not (manual_enabled or auto_enabled):
        return

    # 수신된 payload에서 정책 결정에 필요한 메트릭 추출
    payload_size = meta.get("payload_size") or len(payload_text.encode("utf-8"))
    latency_ms = (meta.get("measured_latency") or 0.0) * 1000.0  # seconds → ms
    queue_depth = 0
    if queue_monitor:
        queue_depth = get_combined_queue_depth()
    schema_type = "standard" if is_defined_sensor_payload(data) else "unknown"

    # payload에 collector 필드가 포함된 경우 추가 활용 (device가 enriched mode일 때)
    measured_latency_from_device = data.get("measured_latency_ms")  # device가 보낸 측정값
    if measured_latency_from_device is not None:
        latency_ms = float(measured_latency_from_device)

    metric = {
        "payload_size": int(payload_size),
        "network_latency_ms": float(latency_ms),
        "queue_depth": int(queue_depth),
        "topic": topic,
        "schema_type": schema_type,
        "timestamp": now_iso()
    }

    if sensor_id not in apr_metrics_buffer:
        apr_metrics_buffer[sensor_id] = []
    apr_metrics_buffer[sensor_id].append(metric)

    count = len(apr_metrics_buffer[sensor_id])
    print(f"[APR Collect] [{sensor_id}] 메트릭 버퍼링 {count}건: size={payload_size}B, latency={latency_ms:.1f}ms, queue={queue_depth}")

    if auto_enabled:
        min_samples = int(runtime.get("apr_min_samples", APR_MIN_SAMPLES))
        interval = int(runtime.get("apr_evaluation_interval_seconds", APR_AUTO_EVALUATION_INTERVAL_SECONDS))
        now_ts = time.time()
        last_ts = apr_auto_last_evaluation_at.get(sensor_id, 0)
        if (
            count >= min_samples and
            now_ts - last_ts >= interval and
            sensor_id not in apr_auto_evaluation_inflight
        ):
            apr_auto_last_evaluation_at[sensor_id] = now_ts
            apr_auto_evaluation_inflight.add(sensor_id)
            threading.Thread(
                target=apr_run_auto_evaluation,
                args=(sensor_id,),
                daemon=True
            ).start()

    # 피드백 수집: 정책 적용 후 메트릭도 별도로 누적
    if sensor_id in apr_feedback_buffer and apr_feedback_log_id.get(sensor_id):
        apr_feedback_buffer[sensor_id].append(metric)
        fb_count = len(apr_feedback_buffer[sensor_id])

        # 피드백 샘플이 충분히 쌓이면 DB 업데이트
        if fb_count >= APR_FEEDBACK_SAMPLES:
            try:
                fb = apr_feedback_buffer[sensor_id]
                after_latency = sum(m["network_latency_ms"] for m in fb) / len(fb)
                after_size = sum(m["payload_size"] for m in fb) / len(fb)
                after_queue = sum(m["queue_depth"] for m in fb) / len(fb)
                log_id = apr_feedback_log_id[sensor_id]
                runtime = get_platform_runtime_config()
                feedback_status = "completed"
                rollback_policy = None

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT before_avg_latency_ms, before_policy FROM apr_policy_log WHERE id=?", (log_id,))
                row = cur.fetchone()
                before_latency = float(row[0]) if row and row[0] is not None else None
                before_policy = json.loads(row[1]) if row and row[1] else None

                if (
                    runtime.get("apr_rollback_enabled") and
                    before_latency is not None and
                    before_policy and
                    after_latency > before_latency * (1.0 + float(runtime.get("apr_rollback_latency_increase_pct", 10.0)) / 100.0)
                ):
                    try:
                        publish_policy_to_device(sensor_id, before_policy)
                        apr_policy_cache[sensor_id] = normalize_policy(before_policy)
                        feedback_status = "rolled_back"
                        rollback_policy = before_policy
                        print(f"[APR Rollback] [{sensor_id}] latency worsened {before_latency:.1f}ms -> {after_latency:.1f}ms, restored {before_policy}")
                    except Exception as rollback_error:
                        feedback_status = "rollback_failed"
                        print(f"[APR Rollback] [{sensor_id}] rollback publish failed: {rollback_error}")

                cur.execute("""
                    UPDATE apr_policy_log
                    SET after_avg_latency_ms=?, after_avg_payload_size=?,
                        after_avg_queue_depth=?, after_sample_count=?,
                        feedback_status=?
                    WHERE id=?
                """, (after_latency, after_size, after_queue, fb_count, feedback_status, log_id))
                conn.commit()
                conn.close()
                print(f"[APR Feedback] [{sensor_id}] 피드백 완료: latency {after_latency:.1f}ms, status={feedback_status}, rollback={rollback_policy is not None} (log_id={log_id})")

                # 피드백 수집 종료
                del apr_feedback_buffer[sensor_id]
                del apr_feedback_log_id[sensor_id]
            except Exception as e:
                print(f"[APR Feedback] DB 업데이트 실패: {e}")


def apr_run_auto_evaluation(sensor_id: str):
    try:
        result = apr_evaluate_and_push(sensor_id)
        print(f"[APR Auto] [{sensor_id}] evaluation result: {result}")
    finally:
        apr_auto_evaluation_inflight.discard(sensor_id)


def apr_evaluate_and_push(sensor_id: str) -> dict:
    """
    버퍼에 누적된 메트릭의 평균으로 XGBoost 추론 실행 후 결과 정책을 C2 push한다.
    관리자가 '정책 결정' 버튼을 누를 때 또는 충분한 샘플이 쌓였을 때 호출.
    """
    global apr_collection_active, apr_metrics_buffer, apr_policy_cache, apr_mqtt_client

    buffer = apr_metrics_buffer.get(sensor_id, [])
    if not buffer:
        return {"error": f"수집된 데이터 없음: {sensor_id}"}
    runtime = get_platform_runtime_config()
    min_samples = int(runtime.get("apr_min_samples", APR_MIN_SAMPLES))
    if len(buffer) < min_samples:
        return {"warning": f"샘플 부족 ({len(buffer)}/{min_samples}건). 더 수집 후 시도 권장.", "sample_count": len(buffer)}

    # 버퍼 평균으로 대표 메트릭 계산
    avg_size = sum(m["payload_size"] for m in buffer) / len(buffer)
    avg_latency = sum(m["network_latency_ms"] for m in buffer) / len(buffer)
    avg_queue = sum(m["queue_depth"] for m in buffer) / len(buffer)
    # 마지막 메트릭의 topic/schema 사용
    last = buffer[-1]

    # XGBoost 추론으로 최적 정책 결정
    new_policy = apr_engine.recommend(
        payload_size=int(avg_size),
        network_latency_ms=float(avg_latency),
        queue_depth=int(avg_queue),
        topic=last["topic"],
        schema_type=last["schema_type"]
    )

    print(f"[APR Eval] [{sensor_id}] {len(buffer)}건 평균 → {new_policy} (size={avg_size:.0f}B, latency={avg_latency:.1f}ms, queue={avg_queue:.1f})")
    previous_policy = apr_policy_cache.get(sensor_id)
    if runtime.get("apr_skip_unchanged_policy") and previous_policy and policies_equal(previous_policy, new_policy):
        apr_collection_active[sensor_id] = False
        apr_metrics_buffer[sensor_id] = []
        print(f"[APR Eval] [{sensor_id}] unchanged policy skipped: {new_policy}")
        return {
            "status": "skipped_unchanged_policy",
            "sensor_id": sensor_id,
            "sample_count": len(buffer),
            "avg_metrics": {"payload_size": avg_size, "latency_ms": avg_latency, "queue_depth": avg_queue},
            "policy": normalize_policy(new_policy),
        }

    # 정책 C2 push (기존과 같아도 명시적으로 재전송)
    try:
        policy_topic, new_policy = publish_policy_to_device(sensor_id, new_policy)
        print(f"[APR Push] [{sensor_id}] 정책 C2 push 완료: {policy_topic} → {new_policy}")
    except Exception as e:
        return {"error": f"C2 push 실패: {e}"}

    # 정책 결정 이력을 DB에 저장 (피드백 추적 시작)
    log_id = None
    try:
        before_policy_str = json.dumps(previous_policy) if previous_policy else None
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO apr_policy_log
            (sensor_id, decided_at, sample_count,
             before_avg_latency_ms, before_avg_payload_size, before_avg_queue_depth,
             before_policy, new_policy, feedback_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            sensor_id, now_iso(), len(buffer),
            avg_latency, avg_size, avg_queue,
            before_policy_str, json.dumps(new_policy),
            now_iso()
        ))
        log_id = cur.lastrowid
        conn.commit()
        conn.close()
        print(f"[APR Log] [{sensor_id}] 정책 결정 이력 저장: log_id={log_id}")
    except Exception as e:
        print(f"[APR Log] DB 저장 실패: {e}")

    # 캐시 업데이트 후 피드백 수집 시작
    apr_policy_cache[sensor_id] = new_policy

    # 수집 모드 해제 및 버퍼 초기화
    apr_collection_active[sensor_id] = False
    apr_metrics_buffer[sensor_id] = []

    # 피드백 수집 버퍼 활성화
    apr_feedback_buffer[sensor_id] = []
    if log_id:
        apr_feedback_log_id[sensor_id] = log_id

    return {
        "status": "success",
        "sensor_id": sensor_id,
        "sample_count": len(buffer),
        "log_id": log_id,
        "avg_metrics": {"payload_size": avg_size, "latency_ms": avg_latency, "queue_depth": avg_queue},
        "policy": new_policy
    }


def start_mqtt():
    global apr_mqtt_client
    config = load_config()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    if connect_client_to_any_broker:
        broker = connect_client_to_any_broker(client, config.get("mqtt", {}), 60)
        print(f"MQTT active broker: {broker['name']} {broker['host']}:{broker['port']}")
    else:
        client.connect(config["mqtt"]["broker"], config["mqtt"]["port"], 60)
    client.loop_start()
    apr_mqtt_client = client  # C2 push용으로 참조 보관
    return client


@app.context_processor
def inject_auth_context():
    return {"current_user": getattr(g, "current_user", None)}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(request.args.get("next") or url_for("dashboard"))
        return render_template("login.html", error=None, next_url=request.args.get("next", ""))

    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    next_url = request.form.get("next") or url_for("dashboard")
    user = fetch_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        log_access_event("LOGIN_FAIL", email=email, failure_reason="INVALID_CREDENTIALS")
        return render_template("login.html", error="Email or password is incorrect.", next_url=next_url), 401
    if user.get("status") != "ACTIVE":
        log_access_event("LOGIN_FAIL", email=email, user_id=user["id"], failure_reason=user.get("status"))
        if user.get("status") == "PENDING":
            return render_template("login.html", error="관리자 승인 대기 중인 계정입니다.", next_url=next_url), 403
        return render_template("login.html", error="This account is suspended.", next_url=next_url), 403

    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    log_access_event("LOGIN_SUCCESS", email=email, user_id=user["id"])
    return redirect(next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", error=None, message=None)

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    company = (request.form.get("company") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    if not name or not email or not password:
        return render_template("register.html", error="Name, email, and password are required.", message=None), 400
    if len(password) < 4:
        return render_template("register.html", error="Password must be at least 4 characters.", message=None), 400

    conn = get_db_connection()
    cur = conn.cursor()
    site_id, group_id, group_topic_path = get_default_site_group(cur)
    user_topic_name = default_user_topic_name(name)
    user_topic_path = build_user_topic_path(group_topic_path, user_topic_name)
    try:
        cur.execute("""
            INSERT INTO users
            (name, email, password_hash, company, phone, role, status, site_id, group_id,
             user_topic_name, user_topic_path, created_at)
            VALUES (?, ?, ?, ?, ?, 'USER', 'PENDING', ?, ?, ?, ?, ?)
        """, (
            name,
            email,
            generate_password_hash(password),
            company,
            phone,
            site_id,
            group_id,
            user_topic_name,
            user_topic_path,
            now_iso(),
        ))
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="Email already exists.", message=None), 400
    conn.close()

    log_access_event("REGISTER_PENDING", email=email, user_id=user_id)
    log_audit_event("USER_REGISTERED_PENDING", "users", user_id, {"email": email, "site_id": site_id, "group_id": group_id}, actor_user_id=None)
    return render_template("register.html", error=None, message="가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다.")


@app.route("/logout")
def logout():
    user = fetch_user_by_id(session.get("user_id"))
    if user:
        log_access_event("LOGOUT", email=user.get("email"), user_id=user.get("id"))
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/auth/me")
def api_auth_me():
    return jsonify({
        "authenticated": True,
        "user": getattr(g, "current_user", None),
    })


@app.route("/admin/users")
def admin_users():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.company, u.phone, u.role, u.status, u.created_at,
               u.site_id, s.name, s.topic_name,
               u.group_id, g.name, g.topic_path,
               u.user_topic_name, u.user_topic_path
        FROM users u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN user_groups g ON g.id = u.group_id
        ORDER BY s.name, g.name, u.name, u.id
    """)
    users = [
        {
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "company": r[3],
            "phone": r[4],
            "role": r[5],
            "status": r[6],
            "created_at": r[7],
            "site_id": r[8],
            "site_name": r[9],
            "site_topic_name": r[10],
            "group_id": r[11],
            "group_name": r[12],
            "group_topic_path": r[13],
            "user_topic_name": r[14],
            "user_topic_path": r[15],
        }
        for r in cur.fetchall()
    ]
    cur.execute("SELECT id, name, topic_name, description, created_at, updated_at FROM sites ORDER BY name")
    sites = [row_to_site(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT g.id, g.site_id, s.name, s.topic_name, g.name, g.topic_name, g.topic_path,
               g.description, g.is_default, g.created_at, g.updated_at
        FROM user_groups g
        JOIN sites s ON s.id = g.site_id
        ORDER BY s.name, g.is_default DESC, g.name
    """)
    groups = [row_to_group(r) for r in cur.fetchall()]
    conn.close()
    return render_template("admin_users.html", users=users, sites=sites, groups=groups)


@app.route("/admin/access-logs")
def admin_access_logs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, user_id, email, event_type, failure_reason, ip_address, user_agent, created_at
        FROM access_logs
        ORDER BY id DESC
        LIMIT 300
    """)
    rows = cur.fetchall()
    conn.close()
    return render_template("admin_logs.html", log_type="access", rows=rows)


@app.route("/admin/audit-logs")
def admin_audit_logs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, actor_user_id, action, target_type, target_id, detail_json, ip_address, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT 300
    """)
    rows = cur.fetchall()
    conn.close()
    return render_template("admin_logs.html", log_type="audit", rows=rows)


@app.route("/api/admin/users/<int:user_id>/status", methods=["POST"])
def api_admin_update_user_status(user_id):
    current = getattr(g, "current_user", None)
    if current and current.get("id") == user_id:
        return jsonify({"error": "cannot_change_own_status"}), 400
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).upper()
    if status not in USER_STATUSES:
        return jsonify({"error": "invalid_status"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, status FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "user_not_found"}), 404
    old_status = row[2]
    cur.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
    conn.commit()
    conn.close()

    if status == "ACTIVE" and old_status == "PENDING":
        action = "USER_APPROVED"
    elif status == "ACTIVE":
        action = "USER_ACTIVATED"
    elif status == "PENDING":
        action = "USER_MARKED_PENDING"
    else:
        action = "USER_SUSPENDED"
    log_audit_event(action, "users", user_id, {"email": row[1], "old_status": old_status, "new_status": status})
    return jsonify({"status": "ok", "user_id": user_id, "new_status": status})


@app.route("/api/admin/users/<int:user_id>/password-reset", methods=["POST"])
def api_admin_reset_user_password(user_id):
    data = request.get_json(silent=True) or {}
    new_password = data.get("password") or ""
    if len(new_password) < 4:
        return jsonify({"error": "password_too_short"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "user_not_found"}), 404

    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()
    conn.close()

    log_audit_event("USER_PASSWORD_RESET", "users", user_id, {"email": row[1]})
    return jsonify({"status": "ok", "user_id": user_id})


@app.route("/api/admin/sites", methods=["GET"])
def api_admin_get_sites():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, topic_name, description, created_at, updated_at FROM sites ORDER BY name")
    sites = [row_to_site(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(sites)


@app.route("/api/admin/sites", methods=["POST"])
def api_admin_create_site():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    topic_name = normalize_topic_part(data.get("topic_name") or name, "site")
    if not name:
        return jsonify({"error": "site_name_required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    timestamp = now_iso()
    try:
        cur.execute("""
            INSERT INTO sites (name, topic_name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, topic_name, description, timestamp, timestamp))
        site_id = cur.lastrowid
        default_group_topic = "default_group"
        cur.execute("""
            INSERT INTO user_groups
            (site_id, name, topic_name, topic_path, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            site_id,
            "Default Group",
            default_group_topic,
            f"{topic_name}/{default_group_topic}",
            "Default group created with site",
            timestamp,
            timestamp,
        ))
        group_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "site_or_topic_already_exists"}), 400
    conn.close()

    log_audit_event("SITE_CREATED", "sites", site_id, {"name": name, "topic_name": topic_name, "default_group_id": group_id})
    return jsonify({"status": "ok", "site_id": site_id, "default_group_id": group_id, "topic_name": topic_name})


@app.route("/api/admin/groups", methods=["GET"])
def api_admin_get_groups():
    site_id = request.args.get("site_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT g.id, g.site_id, s.name, s.topic_name, g.name, g.topic_name, g.topic_path,
               g.description, g.is_default, g.created_at, g.updated_at
        FROM user_groups g
        JOIN sites s ON s.id = g.site_id
    """
    params = []
    if site_id:
        sql += " WHERE g.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY s.name, g.is_default DESC, g.name"
    cur.execute(sql, params)
    groups = [row_to_group(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(groups)


@app.route("/api/admin/groups", methods=["POST"])
def api_admin_create_group():
    data = request.get_json(silent=True) or {}
    site_id = data.get("site_id")
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    if not site_id or not name:
        return jsonify({"error": "site_id_and_group_name_required"}), 400
    try:
        site_id = int(site_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_site_id"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, topic_name FROM sites WHERE id = ?", (site_id,))
    site = cur.fetchone()
    if not site:
        conn.close()
        return jsonify({"error": "site_not_found"}), 404

    topic_name = normalize_topic_part(data.get("topic_name") or name, "group")
    topic_path = f"{site[1]}/{topic_name}"
    timestamp = now_iso()
    try:
        cur.execute("""
            INSERT INTO user_groups
            (site_id, name, topic_name, topic_path, description, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
        """, (site_id, name, topic_name, topic_path, description, timestamp, timestamp))
        group_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "group_or_topic_already_exists"}), 400
    conn.close()

    log_audit_event("GROUP_CREATED", "user_groups", group_id, {"site_id": site_id, "name": name, "topic_path": topic_path})
    return jsonify({"status": "ok", "group_id": group_id, "topic_path": topic_path})


@app.route("/api/admin/site-tree")
def api_admin_site_tree():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, topic_name, description, created_at, updated_at FROM sites ORDER BY name")
    sites = [row_to_site(r) for r in cur.fetchall()]
    for site in sites:
        cur.execute("""
            SELECT g.id, g.site_id, s.name, s.topic_name, g.name, g.topic_name, g.topic_path,
                   g.description, g.is_default, g.created_at, g.updated_at
            FROM user_groups g
            JOIN sites s ON s.id = g.site_id
            WHERE g.site_id = ?
            ORDER BY g.is_default DESC, g.name
        """, (site["id"],))
        groups = [row_to_group(r) for r in cur.fetchall()]
        for group in groups:
            cur.execute("""
                SELECT id, name, email, role, status, user_topic_name, user_topic_path
                FROM users
                WHERE group_id = ?
                ORDER BY name, email
            """, (group["id"],))
            group["users"] = [
                {
                    "id": r[0],
                    "name": r[1],
                    "email": r[2],
                    "role": r[3],
                    "status": r[4],
                    "user_topic_name": r[5],
                    "user_topic_path": r[6],
                }
                for r in cur.fetchall()
            ]
        site["groups"] = groups
    conn.close()
    return jsonify(sites)


@app.route("/api/admin/topic-consistency", methods=["GET"])
def api_admin_topic_consistency():
    return jsonify(topic_consistency_report(repair_missing=False))


@app.route("/api/admin/topic-consistency/repair-missing", methods=["POST"])
def api_admin_repair_missing_topics():
    report = topic_consistency_report(repair_missing=True)
    log_audit_event("TOPIC_CONSISTENCY_REPAIR", "topic_consistency", None, report.get("repaired"))
    return jsonify(report)


@app.route("/api/admin/users", methods=["POST"])
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = str(data.get("role", "USER")).upper()
    status = str(data.get("status", "PENDING")).upper()
    company = (data.get("company") or "").strip()
    phone = (data.get("phone") or "").strip()
    temporary = bool(data.get("temporary"))

    if not name or not email or not password:
        return jsonify({"error": "name_email_password_required"}), 400
    if role not in ("ADMIN", "USER"):
        return jsonify({"error": "invalid_role"}), 400
    if status not in USER_STATUSES:
        return jsonify({"error": "invalid_status"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    if temporary:
        site_id, group_id, group_topic_path = get_default_site_group(cur)
    else:
        if not data.get("site_id") or not data.get("group_id"):
            conn.close()
            return jsonify({"error": "site_and_group_required"}), 400
        try:
            site_id = int(data.get("site_id"))
            group_id = int(data.get("group_id"))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "invalid_site_or_group"}), 400
        group_row = fetch_group_for_site(cur, site_id, group_id)
        if not group_row:
            conn.close()
            return jsonify({"error": "group_not_found_for_site"}), 400
        group_topic_path = group_row[1]

    user_topic_name = normalize_topic_part(data.get("user_topic_name") or default_user_topic_name(name), "user")
    user_topic_path = build_user_topic_path(group_topic_path, user_topic_name)
    try:
        cur.execute("""
            INSERT INTO users
            (name, email, password_hash, company, phone, role, status, site_id, group_id,
             user_topic_name, user_topic_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name,
            email,
            generate_password_hash(password),
            company,
            phone,
            role,
            status,
            site_id,
            group_id,
            user_topic_name,
            user_topic_path,
            now_iso(),
        ))
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "email_already_exists"}), 400
    conn.close()

    log_audit_event("USER_CREATED", "users", user_id, {
        "email": email,
        "role": role,
        "status": status,
        "site_id": site_id,
        "group_id": group_id,
        "temporary": temporary,
        "user_topic_path": user_topic_path,
    })
    return jsonify({
        "status": "ok",
        "user_id": user_id,
        "site_id": site_id,
        "group_id": group_id,
        "user_topic_name": user_topic_name,
        "user_topic_path": user_topic_path,
    })


@app.route("/device_management")
def device_management():
    return render_template("device_management.html")


@app.route("/api/admin/users/options")
def api_admin_user_options():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, u.role, u.status,
               u.site_id, s.name, u.group_id, g.name, u.user_topic_path
        FROM users u
        LEFT JOIN sites s ON s.id = u.site_id
        LEFT JOIN user_groups g ON g.id = u.group_id
        ORDER BY u.name, u.email
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify([
        {
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "role": r[3],
            "status": r[4],
            "site_id": r[5],
            "site_name": r[6],
            "group_id": r[7],
            "group_name": r[8],
            "user_topic_path": r[9],
        }
        for r in rows
    ])


@app.route("/api/fleets", methods=["GET"])
def api_get_fleets():
    owner_filter = request.args.get("owner_user_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT f.id, f.name, f.description, f.owner_user_id, u.name, u.email,
               f.topic_name, f.topic_path, f.created_at, f.updated_at,
               fps.policy_json, fps.applied_at
        FROM fleets f
        LEFT JOIN users u ON u.id = f.owner_user_id
        LEFT JOIN fleet_policy_state fps ON fps.fleet_id = f.id
    """
    params = []
    clauses = []
    if current_user_is_admin():
        if owner_filter:
            clauses.append("f.owner_user_id = ?")
            params.append(owner_filter)
    else:
        clauses.append("f.owner_user_id = ?")
        params.append(current_user_id())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY u.name, f.name"
    cur.execute(sql, params)
    fleets = [serialize_fleet(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(fleets)


@app.route("/api/fleets", methods=["POST"])
def api_create_fleet():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    if not name:
        return jsonify({"error": "fleet_name_required"}), 400
    try:
        owner_user_id = resolve_owner_user_id(data)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_owner_user_id"}), 400
    owner_context = fetch_user_topic_context(owner_user_id)
    if not owner_context:
        return jsonify({"error": "owner_user_not_found"}), 404
    if owner_context["status"] != "ACTIVE":
        return jsonify({"error": "owner_user_not_active"}), 400
    topic_name = normalize_topic_part(data.get("topic_name") or name, "fleet")
    topic_path = build_fleet_topic_path(owner_context["user_topic_path"], topic_name)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO fleets
            (name, description, owner_user_id, topic_name, topic_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, description, owner_user_id, topic_name, topic_path, now_iso(), now_iso()))
        fleet_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "fleet_name_already_exists_for_user"}), 400
    conn.close()

    log_audit_event("FLEET_CREATED", "fleets", fleet_id, {"name": name, "owner_user_id": owner_user_id, "topic_path": topic_path})
    return jsonify({"status": "ok", "fleet_id": fleet_id, "topic_name": topic_name, "topic_path": topic_path})


@app.route("/api/fleets/<int:fleet_id>", methods=["PUT"])
def api_update_fleet(fleet_id):
    row = fetch_fleet_row(fleet_id)
    if not row:
        return jsonify({"error": "fleet_not_found"}), 404
    current_owner = row[3]
    if not can_manage_owner(current_owner):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    if not name:
        return jsonify({"error": "fleet_name_required"}), 400
    owner_user_id = current_owner
    if current_user_is_admin() and data.get("owner_user_id"):
        try:
            owner_user_id = int(data.get("owner_user_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_owner_user_id"}), 400
        if not fetch_user_exists(owner_user_id):
            return jsonify({"error": "owner_user_not_found"}), 404
    owner_context = fetch_user_topic_context(owner_user_id)
    if not owner_context:
        return jsonify({"error": "owner_user_not_found"}), 404
    if owner_context["status"] != "ACTIVE":
        return jsonify({"error": "owner_user_not_active"}), 400
    old_topic_path = row[7]
    topic_name = normalize_topic_part(data.get("topic_name") or name, "fleet")
    topic_path = build_fleet_topic_path(owner_context["user_topic_path"], topic_name)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE fleets
            SET name = ?, description = ?, owner_user_id = ?, topic_name = ?, topic_path = ?, updated_at = ?
            WHERE id = ?
        """, (name, description, owner_user_id, topic_name, topic_path, now_iso(), fleet_id))
        if owner_user_id != current_owner:
            cur.execute("UPDATE devices SET owner_user_id = ? WHERE fleet_id = ?", (owner_user_id, fleet_id))
        cur.execute("""
            SELECT id, device_id, device_type, topic_prefix, telemetry_topic, policy_topic
            FROM devices
            WHERE fleet_id = ?
        """, (fleet_id,))
        for device_row_id, device_id, device_type, current_prefix, current_telemetry, current_policy in cur.fetchall():
            old_telemetry = build_device_telemetry_topic(old_topic_path or "", device_type, device_id) if old_topic_path else None
            old_policy = build_device_policy_topic(old_topic_path or "", device_id) if old_topic_path else None
            should_rebase = (
                not current_prefix
                or current_prefix == old_topic_path
                or (old_telemetry and current_telemetry == old_telemetry)
                or (old_policy and current_policy == old_policy)
            )
            if should_rebase:
                next_telemetry = build_device_telemetry_topic(topic_path, device_type, device_id)
                next_policy = build_device_policy_topic(topic_path, device_id)
                cur.execute("""
                    UPDATE devices
                    SET topic_prefix = ?, telemetry_topic = ?, policy_topic = ?, updated_at = ?
                    WHERE id = ?
                """, (topic_path, next_telemetry, next_policy, now_iso(), device_row_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "fleet_name_already_exists_for_user"}), 400
    conn.close()

    log_audit_event("FLEET_UPDATED", "fleets", fleet_id, {"name": name, "owner_user_id": owner_user_id, "topic_path": topic_path})
    return jsonify({"status": "ok", "fleet_id": fleet_id, "topic_name": topic_name, "topic_path": topic_path})


@app.route("/api/fleets/<int:fleet_id>", methods=["DELETE"])
def api_delete_fleet(fleet_id):
    row = fetch_fleet_row(fleet_id)
    if not row:
        return jsonify({"error": "fleet_not_found"}), 404
    if not can_manage_owner(row[3]):
        return jsonify({"error": "forbidden"}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM devices WHERE fleet_id = ?", (fleet_id,))
    device_count = cur.fetchone()[0]
    if device_count:
        conn.close()
        return jsonify({"error": "fleet_has_devices", "device_count": device_count}), 400
    cur.execute("DELETE FROM fleet_policy_state WHERE fleet_id = ?", (fleet_id,))
    cur.execute("DELETE FROM policy_deployment_log WHERE target_type = 'fleet' AND target_id = ?", (fleet_id,))
    cur.execute("DELETE FROM fleets WHERE id = ?", (fleet_id,))
    conn.commit()
    conn.close()

    log_audit_event("FLEET_DELETED", "fleets", fleet_id, {"name": row[1]})
    return jsonify({"status": "ok", "fleet_id": fleet_id})


@app.route("/api/devices", methods=["GET"])
def api_get_devices():
    owner_filter = request.args.get("owner_user_id", type=int)
    fleet_filter = request.args.get("fleet_id", type=int)
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT d.id, d.device_id, d.device_name, d.device_type, d.device_os, d.fleet_id, f.name,
               d.owner_user_id, u.name, u.email, d.status, d.topic_prefix,
               d.telemetry_topic, d.policy_topic, d.description, d.created_at, d.updated_at,
               dps.policy_json, dps.applied_at
        FROM devices d
        LEFT JOIN fleets f ON f.id = d.fleet_id
        LEFT JOIN users u ON u.id = d.owner_user_id
        LEFT JOIN device_policy_state dps ON dps.device_row_id = d.id
    """
    clauses = []
    params = []
    if current_user_is_admin():
        if owner_filter:
            clauses.append("d.owner_user_id = ?")
            params.append(owner_filter)
    else:
        clauses.append("d.owner_user_id = ?")
        params.append(current_user_id())
    if fleet_filter:
        clauses.append("d.fleet_id = ?")
        params.append(fleet_filter)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY u.name, f.name, d.device_name"
    cur.execute(sql, params)
    devices = [serialize_device(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(devices)


@app.route("/api/devices", methods=["POST"])
def api_create_device():
    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or "").strip()
    device_name = (data.get("device_name") or "").strip()
    device_type = (data.get("device_type") or "raspberry_pi").strip()
    device_os = normalize_device_os(data.get("device_os"))
    status = str(data.get("status") or "ACTIVE").upper()
    description = (data.get("description") or "").strip()
    fleet_id = data.get("fleet_id") or None
    if not device_id or not device_name:
        return jsonify({"error": "device_id_and_name_required"}), 400
    if status not in ("ACTIVE", "INACTIVE", "MAINTENANCE"):
        return jsonify({"error": "invalid_status"}), 400
    try:
        owner_user_id = resolve_owner_user_id(data)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_owner_user_id"}), 400
    owner_context = fetch_user_topic_context(owner_user_id)
    if not owner_context:
        return jsonify({"error": "owner_user_not_found"}), 404
    if owner_context["status"] != "ACTIVE":
        return jsonify({"error": "owner_user_not_active"}), 400
    fleet_context = None
    if fleet_id:
        try:
            fleet_id = int(fleet_id)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_fleet_id"}), 400
        fleet_context = fetch_fleet_topic_context(fleet_id)
        if not fleet_context:
            return jsonify({"error": "fleet_not_found"}), 404
        if int(fleet_context["owner_user_id"]) != int(owner_user_id):
            return jsonify({"error": "fleet_owner_mismatch"}), 400
    try:
        resolved_topics = resolve_device_topics(owner_user_id, fleet_id, device_type, device_id, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not resolved_topics:
        return jsonify({"error": "device_topic_context_unavailable"}), 400
    topic_prefix, telemetry_topic, policy_topic = resolved_topics

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO devices
            (device_id, device_name, device_type, device_os, fleet_id, owner_user_id, status,
             topic_prefix, telemetry_topic, policy_topic, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            device_id, device_name, device_type, device_os, fleet_id, owner_user_id, status,
            topic_prefix, telemetry_topic, policy_topic, description, now_iso(), now_iso()
        ))
        row_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "device_id_already_exists"}), 400
    conn.close()

    log_audit_event("DEVICE_CREATED", "devices", row_id, {"device_id": device_id, "device_os": device_os, "owner_user_id": owner_user_id, "fleet_id": fleet_id, "telemetry_topic": telemetry_topic})
    return jsonify({"status": "ok", "id": row_id})


@app.route("/api/devices/<int:row_id>", methods=["PUT"])
def api_update_device(row_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, owner_user_id FROM devices WHERE id = ?", (row_id,))
    existing = cur.fetchone()
    conn.close()
    if not existing:
        return jsonify({"error": "device_not_found"}), 404
    if not can_manage_owner(existing[1]):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or "").strip()
    device_name = (data.get("device_name") or "").strip()
    device_type = (data.get("device_type") or "raspberry_pi").strip()
    device_os = normalize_device_os(data.get("device_os"))
    status = str(data.get("status") or "ACTIVE").upper()
    description = (data.get("description") or "").strip()
    fleet_id = data.get("fleet_id") or None
    owner_user_id = existing[1]
    if current_user_is_admin() and data.get("owner_user_id"):
        try:
            owner_user_id = int(data.get("owner_user_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_owner_user_id"}), 400
    if not device_id or not device_name:
        return jsonify({"error": "device_id_and_name_required"}), 400
    if status not in ("ACTIVE", "INACTIVE", "MAINTENANCE"):
        return jsonify({"error": "invalid_status"}), 400
    owner_context = fetch_user_topic_context(owner_user_id)
    if not owner_context:
        return jsonify({"error": "owner_user_not_found"}), 404
    if owner_context["status"] != "ACTIVE":
        return jsonify({"error": "owner_user_not_active"}), 400
    fleet_context = None
    if fleet_id:
        try:
            fleet_id = int(fleet_id)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_fleet_id"}), 400
        fleet_context = fetch_fleet_topic_context(fleet_id)
        if not fleet_context:
            return jsonify({"error": "fleet_not_found"}), 404
        if int(fleet_context["owner_user_id"]) != int(owner_user_id):
            return jsonify({"error": "fleet_owner_mismatch"}), 400
    try:
        resolved_topics = resolve_device_topics(owner_user_id, fleet_id, device_type, device_id, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not resolved_topics:
        return jsonify({"error": "device_topic_context_unavailable"}), 400
    topic_prefix, telemetry_topic, policy_topic = resolved_topics

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE devices
            SET device_id = ?, device_name = ?, device_type = ?, device_os = ?, fleet_id = ?, owner_user_id = ?,
                status = ?, topic_prefix = ?, telemetry_topic = ?, policy_topic = ?,
                description = ?, updated_at = ?
            WHERE id = ?
        """, (
            device_id, device_name, device_type, device_os, fleet_id, owner_user_id, status,
            topic_prefix, telemetry_topic, policy_topic, description, now_iso(), row_id
        ))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "device_id_already_exists"}), 400
    conn.close()

    log_audit_event("DEVICE_UPDATED", "devices", row_id, {"device_id": device_id, "device_os": device_os, "owner_user_id": owner_user_id, "fleet_id": fleet_id, "telemetry_topic": telemetry_topic})
    return jsonify({"status": "ok", "id": row_id})


@app.route("/api/devices/<int:row_id>", methods=["DELETE"])
def api_delete_device(row_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, device_id, owner_user_id FROM devices WHERE id = ?", (row_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "device_not_found"}), 404
    if not can_manage_owner(existing[2]):
        conn.close()
        return jsonify({"error": "forbidden"}), 403
    cur.execute("DELETE FROM device_policy_state WHERE device_row_id = ?", (row_id,))
    cur.execute("DELETE FROM policy_deployment_log WHERE device_row_id = ?", (row_id,))
    cur.execute("DELETE FROM policy_deployment_log WHERE target_type = 'device' AND target_id = ?", (row_id,))
    cur.execute("DELETE FROM devices WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()

    log_audit_event("DEVICE_DELETED", "devices", row_id, {"device_id": existing[1]})
    return jsonify({"status": "ok", "id": row_id})


COMMON_CLIENT_PACKAGE_FILES = (
    "raspi_iot_publisher.py",
    "raspi-requirements.txt",
)

OS_CLIENT_PACKAGE_FILES = {
    "raspberry_pi": (
        "raspi_system_metrics_publisher.py",
        "run_raspi_client.sh",
        "run_raspi_system_metrics.sh",
        "apr-raspi-client.service",
        "README_RASPI_EDGE.md",
    ),
    "ubuntu_linux": (
        "pc_test_publisher.py",
        "run_pc_test_publisher.sh",
        "README_RASPI_EDGE.md",
    ),
    "windows_pc": (
        "pc_test_publisher.py",
        "run_pc_test_publisher.bat",
        "README_RASPI_EDGE.md",
    ),
}

def fetch_device_client_context(row_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT d.id, d.device_id, d.device_name, d.device_type, d.device_os, d.fleet_id, f.name,
               d.owner_user_id, u.name, u.email, d.status, d.topic_prefix,
               d.telemetry_topic, d.policy_topic, d.description
        FROM devices d
        LEFT JOIN fleets f ON f.id = d.fleet_id
        LEFT JOIN users u ON u.id = d.owner_user_id
        WHERE d.id = ?
    """, (row_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "device_id": row[1],
        "device_name": row[2],
        "device_type": row[3],
        "device_os": normalize_device_os(row[4]),
        "fleet_id": row[5],
        "fleet_name": row[6],
        "owner_user_id": row[7],
        "owner_name": row[8],
        "owner_email": row[9],
        "status": row[10],
        "topic_prefix": row[11],
        "telemetry_topic": row[12],
        "policy_topic": row[13],
        "description": row[14],
    }


def mqtt_client_config_values():
    config = load_config()
    mqtt_config = config.get("mqtt", {})
    broker = mqtt_config.get("broker")
    port = mqtt_config.get("port", 1883)
    if not broker and mqtt_config.get("brokers"):
        first_broker = next((item for item in mqtt_config["brokers"] if item.get("enabled", True)), mqtt_config["brokers"][0])
        broker = first_broker.get("host")
        port = first_broker.get("port", port)
    return {
        "broker": broker or "127.0.0.1",
        "port": int(port or 1883),
        "username": mqtt_config.get("username", ""),
        "password": mqtt_config.get("password", ""),
        "tls": str(bool(mqtt_config.get("tls", False))).lower(),
    }


def render_client_config(device):
    mqtt_values = mqtt_client_config_values()
    sensor_type = normalize_topic_part(device.get("device_type"), "raspberry_pi")
    return f"""[mqtt]
broker = {mqtt_values["broker"]}
port = {mqtt_values["port"]}
username = {mqtt_values["username"]}
password = {mqtt_values["password"]}
tls = {mqtt_values["tls"]}

[device]
sensor_id = {device["device_id"]}
sensor_type = {sensor_type}
unit =
client_id = apr-{device["device_id"]}

[topics]
telemetry = {device["telemetry_topic"]}
policy = {device["policy_topic"]}

[runtime]
interval = 1.0
experiment_id = RASPI_RUNTIME

[security]
apr_aes_key_hex = 01010101010101010101010101010101
"""


def render_system_metrics_config(device):
    mqtt_values = mqtt_client_config_values()
    return f"""[mqtt]
broker = {mqtt_values["broker"]}
port = {mqtt_values["port"]}
username = {mqtt_values["username"]}
password = {mqtt_values["password"]}
tls = {mqtt_values["tls"]}

[device]
device_id = {device["device_id"]}
device_name = {device["device_name"]}
location = {device.get("fleet_name") or ""}
client_id = apr-system-{device["device_id"]}

[topics]
topic_prefix = {device["topic_prefix"]}
telemetry = {device["telemetry_topic"]}
policy = {device["policy_topic"]}

[runtime]
enabled = true
interval = 5.0
experiment_id = RASPI_SYSTEM_RUNTIME
metrics = cpu_percent,memory_percent,cpu_temp_c,disk_percent,load_1m

[security]
apr_aes_key_hex = 01010101010101010101010101010101
"""


@app.route("/api/devices/<int:row_id>/client-package", methods=["GET"])
def api_download_device_client_package(row_id):
    device = fetch_device_client_context(row_id)
    if not device:
        return jsonify({"error": "device_not_found"}), 404
    if not can_manage_owner(device["owner_user_id"]):
        return jsonify({"error": "forbidden"}), 403

    memory = io.BytesIO()
    device_dir = os.path.join(app.root_path, "device")
    device_os = normalize_device_os(request.args.get("device_os") or device.get("device_os"))
    topic_override_requested = any(request.args.get(key) for key in ("topic_prefix", "telemetry_topic", "policy_topic"))
    if topic_override_requested:
        try:
            requested_topics = resolve_device_topics(
                device["owner_user_id"],
                device["fleet_id"],
                device["device_type"],
                device["device_id"],
                request.args,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if requested_topics:
            device["topic_prefix"], device["telemetry_topic"], device["policy_topic"] = requested_topics
    package_files = list(COMMON_CLIENT_PACKAGE_FILES) + list(OS_CLIENT_PACKAGE_FILES.get(device_os, OS_CLIENT_PACKAGE_FILES["raspberry_pi"]))
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("client.config", render_client_config(device))
        if device_os == "raspberry_pi":
            archive.writestr("system_metrics.config", render_system_metrics_config(device))
        for filename in package_files:
            file_path = os.path.join(device_dir, filename)
            if os.path.exists(file_path):
                archive.write(file_path, filename)
        archive.writestr(
            "START_HERE.txt",
            "\n".join([
                "APR dynamic client package",
                "",
                f"Device OS: {device_os}",
                f"Telemetry topic: {device['telemetry_topic']}",
                f"Policy topic: {device['policy_topic']}",
                "",
                "Raspberry Pi: ./run_raspi_client.sh",
                "Raspberry Pi system metrics: ./run_raspi_system_metrics.sh",
                "Ubuntu/Linux PC test: ./run_pc_test_publisher.sh",
                "Windows PC test: run_pc_test_publisher.bat",
                "",
                "The downloaded config is generated from the Device Management screen.",
                "If you change OS or topics on the screen, save the device and download again.",
            ])
        )
    memory.seek(0)
    download_name = f"apr_client_{normalize_topic_part(device['device_id'], 'device')}_{device_os}.zip"
    log_audit_event("DEVICE_CLIENT_PACKAGE_DOWNLOADED", "devices", row_id, {
        "device_id": device["device_id"],
        "device_os": device_os,
        "telemetry_topic": device["telemetry_topic"],
        "policy_topic": device["policy_topic"],
    })
    return send_file(memory, mimetype="application/zip", as_attachment=True, download_name=download_name)


def get_policy_deployment_logs(target_type, target_id, limit=20):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, target_type, target_id, device_row_id, device_id, policy_json, source,
               published_topic, publish_status, last_error, actor_user_id, created_at
        FROM policy_deployment_log
        WHERE target_type = ? AND target_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (target_type, target_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "target_type": r[1],
            "target_id": r[2],
            "device_row_id": r[3],
            "device_id": r[4],
            "policy": safe_json_loads(r[5]),
            "source": r[6],
            "published_topic": r[7],
            "publish_status": r[8],
            "last_error": r[9],
            "actor_user_id": r[10],
            "created_at": r[11],
        }
        for r in rows
    ]


def get_device_policy_state(row_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT policy_json, source, applied_by_user_id, applied_at,
               published_topic, publish_status, last_error
        FROM device_policy_state
        WHERE device_row_id = ?
    """, (row_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "policy": safe_json_loads(row[0]),
        "source": row[1],
        "applied_by_user_id": row[2],
        "applied_at": row[3],
        "published_topic": row[4],
        "publish_status": row[5],
        "last_error": row[6],
    }


def get_fleet_policy_state(fleet_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT policy_json, source, applied_by_user_id, applied_at,
               publish_status, last_error
        FROM fleet_policy_state
        WHERE fleet_id = ?
    """, (fleet_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "policy": safe_json_loads(row[0]),
        "source": row[1],
        "applied_by_user_id": row[2],
        "applied_at": row[3],
        "publish_status": row[4],
        "last_error": row[5],
    }


def policy_from_request(data, topic):
    mode = (data.get("mode") or "manual").strip().lower()
    if mode == "recommend":
        return recommend_policy_from_runtime(data, topic), "apr_recommend"
    return validate_policy_payload(data.get("policy")), data.get("source") or "manual"


@app.route("/api/devices/<int:row_id>/policy", methods=["GET"])
def api_get_device_policy(row_id):
    device = fetch_device_policy_target(row_id)
    if not device:
        return jsonify({"error": "device_not_found"}), 404
    if not can_manage_owner(device["owner_user_id"]):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({
        "device": device,
        "state": get_device_policy_state(row_id),
        "logs": get_policy_deployment_logs("device", row_id),
    })


@app.route("/api/devices/<int:row_id>/policy/apply", methods=["POST"])
def api_apply_device_policy(row_id):
    device = fetch_device_policy_target(row_id)
    if not device:
        return jsonify({"error": "device_not_found"}), 404
    if not can_manage_owner(device["owner_user_id"]):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    try:
        policy, source = policy_from_request(data, device.get("telemetry_topic") or device.get("device_id"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 501

    result = apply_policy_to_device_target(device, policy, source=source)
    log_audit_event("DEVICE_POLICY_APPLIED", "devices", row_id, {
        "device_id": device["device_id"],
        "policy": result["policy"],
        "publish_status": result["publish_status"],
    })
    return jsonify({"status": "ok", "result": result, "state": get_device_policy_state(row_id)})


@app.route("/api/fleets/<int:fleet_id>/policy", methods=["GET"])
def api_get_fleet_policy(fleet_id):
    fleet = fetch_fleet_row(fleet_id)
    if not fleet:
        return jsonify({"error": "fleet_not_found"}), 404
    fleet_data = serialize_fleet(fleet)
    if not can_manage_owner(fleet_data["owner_user_id"]):
        return jsonify({"error": "forbidden"}), 403
    return jsonify({
        "fleet": fleet_data,
        "state": get_fleet_policy_state(fleet_id),
        "logs": get_policy_deployment_logs("fleet", fleet_id),
    })


@app.route("/api/fleets/<int:fleet_id>/policy/apply", methods=["POST"])
def api_apply_fleet_policy(fleet_id):
    fleet = fetch_fleet_row(fleet_id)
    if not fleet:
        return jsonify({"error": "fleet_not_found"}), 404
    fleet_data = serialize_fleet(fleet)
    if not can_manage_owner(fleet_data["owner_user_id"]):
        return jsonify({"error": "forbidden"}), 403

    data = request.get_json(silent=True) or {}
    try:
        policy, source = policy_from_request(data, fleet_data["name"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 501

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id
        FROM devices
        WHERE fleet_id = ? AND owner_user_id = ?
        ORDER BY device_name
    """, (fleet_id, fleet_data["owner_user_id"]))
    device_ids = [r[0] for r in cur.fetchall()]
    conn.close()

    results = []
    for device_row_id in device_ids:
        device = fetch_device_policy_target(device_row_id)
        if device:
            results.append(apply_policy_to_device_target(device, policy, source=source))

    failure_count = len([r for r in results if r["publish_status"] != "success"])
    if not results:
        publish_status = "no_devices"
        last_error = "Fleet has no devices."
    elif failure_count:
        publish_status = "partial_failed"
        last_error = f"{failure_count} of {len(results)} device policy publishes failed."
    else:
        publish_status = "success"
        last_error = None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fleet_policy_state
        (fleet_id, policy_json, source, applied_by_user_id, applied_at, publish_status, last_error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fleet_id) DO UPDATE SET
            policy_json = excluded.policy_json,
            source = excluded.source,
            applied_by_user_id = excluded.applied_by_user_id,
            applied_at = excluded.applied_at,
            publish_status = excluded.publish_status,
            last_error = excluded.last_error
    """, (
        fleet_id,
        json.dumps(policy, ensure_ascii=False),
        source,
        current_user_id(),
        now_iso(),
        publish_status,
        last_error,
    ))
    log_policy_deployment(cur, "fleet", fleet_id, None, policy, source, None, publish_status, last_error)
    conn.commit()
    conn.close()

    log_audit_event("FLEET_POLICY_APPLIED", "fleets", fleet_id, {
        "fleet": fleet_data["name"],
        "policy": policy,
        "publish_status": publish_status,
        "device_count": len(results),
    })
    return jsonify({
        "status": "ok",
        "fleet_id": fleet_id,
        "policy": policy,
        "publish_status": publish_status,
        "last_error": last_error,
        "device_results": results,
        "state": get_fleet_policy_state(fleet_id),
    })


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/all_dashboard")
def all_dashboard():
    return render_template("all_dashboard.html")


@app.route("/sensor_config")
def sensor_config():
    return render_template("sensor_config.html")


@app.route("/queue_dashboard")
def queue_dashboard():
    return render_template("queue_dashboard.html")


@app.route("/api/broker/status")
def api_broker_status():
    config = load_config()
    mqtt_config = config.get("mqtt", {})
    brokers = normalize_brokers(mqtt_config) if normalize_brokers else [{
        "name": "primary",
        "host": mqtt_config.get("broker"),
        "port": mqtt_config.get("port"),
        "priority": 1,
        "enabled": True,
    }]
    active = getattr(apr_mqtt_client, "_distributed_broker", None)
    return jsonify({
        "brokers": brokers,
        "active_broker": active,
        "connected": bool(apr_mqtt_client and apr_mqtt_client.is_connected()),
        "startup_error": mqtt_startup_error,
        "distributed_enabled": len(brokers) > 1,
    })


@app.route("/api/db/status")
def api_db_status():
    return jsonify(get_database_stats())


@app.route("/api/system/status")
def api_system_status():
    return jsonify({
        "current": get_system_identity(),
        "lock_file": SYSTEM_LOCK_FILE,
        "lock_active": system_lock_active,
        "lock": read_system_lock(),
        "db_writer": get_db_writer_stats(),
    })


@app.route("/api/system/shutdown", methods=["POST"])
def api_system_shutdown():
    threading.Thread(target=lambda: (time.sleep(0.5), graceful_shutdown(True)), daemon=True).start()
    return jsonify({
        "status": "shutting_down",
        "message": "MQTT and DB writer will stop; DB lock will be released.",
    })


@app.route("/latency_dashboard")
def latency_dashboard():
    return render_template("latency_dashboard.html")


@app.route("/experiment_dashboard")
def experiment_dashboard():
    return render_template("experiment_dashboard.html")


@app.route("/schema_dashboard")
def schema_dashboard():
    return render_template("schema_dashboard.html")


@app.route("/apr_dashboard")
def apr_dashboard():
    return render_template("apr_dashboard.html")


@app.route("/voice_dashboard")
def voice_dashboard():
    return render_template("voice_dashboard.html")


@app.route("/device_edge_doc")
def device_edge_doc():
    return render_markdown_doc(
        os.path.join(os.path.dirname(__file__), "device", "README_RASPI_EDGE.md"),
        "Device Edge README",
    )


@app.route("/server_operation_manual")
def server_operation_manual():
    return render_markdown_doc(
        os.path.join(os.path.dirname(__file__), "docs", "SERVER_OPERATION_MANUAL.md"),
        "Server Operation Manual",
    )


def render_markdown_doc(doc_path, title):
    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return app.response_class(f"{title} not found", status=404, mimetype="text/plain")

    escaped = html.escape(content)
    page = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" href="/static/css/dashboard_common.css">
    <script src="/static/js/common_menu.js"></script>
    <style>
        .doc-shell {{
            display: grid;
            grid-template-columns: 280px minmax(0, 1fr);
            min-height: 100vh;
            background: #f8fafc;
        }}
        .doc-main {{
            padding: 28px 36px;
        }}
        .doc-card {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 24px;
            max-width: 980px;
        }}
        .doc-card h2 {{
            margin-top: 0;
            color: #111827;
        }}
        .doc-content {{
            white-space: pre-wrap;
            font-family: Consolas, "Courier New", monospace;
            font-size: 13px;
            line-height: 1.55;
            color: #1f2937;
        }}
    </style>
</head>
<body>
    <div class="doc-shell">
        <aside class="sidebar">
            <button id="sidebarToggle" class="sidebar-toggle" type="button">Menu</button>
            <div id="commonMenu"></div>
        </aside>
        <main class="doc-main">
            <section class="doc-card">
                <h2>{html.escape(title)}</h2>
                <pre class="doc-content">{escaped}</pre>
            </section>
        </main>
    </div>
</body>
</html>"""
    return app.response_class(page, mimetype="text/html")


@app.route("/api/stats")
def api_stats():
    warning_config = load_config().get("platform", {}).get("collection_delay_warning", {})
    late_multiplier = request.args.get("late_multiplier", default=warning_config.get("late_multiplier", 2.0), type=float)
    collection_window = request.args.get("collection_window", default=warning_config.get("window", 200), type=int)
    collection_min_samples = request.args.get("collection_min_samples", default=warning_config.get("min_samples", 5), type=int)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sensor_id,
            sensor_type,
            COUNT(*),
            ROUND(AVG(value), 2),
            ROUND(MIN(value), 2),
            ROUND(MAX(value), 2),
            ROUND(AVG(measured_latency), 6),
            ROUND(AVG(payload_size), 2)
        FROM sensor_data
        GROUP BY sensor_id, sensor_type
        ORDER BY sensor_id
    """)

    rows = cur.fetchall()
    result = []
    for r in rows:
        timing = calculate_collection_timing(
            cur,
            r[0],
            r[1],
            window=max(10, min(collection_window, 1000)),
            late_multiplier=max(1.0, late_multiplier),
            min_samples=max(2, collection_min_samples),
        )
        item = {
            "sensor_id": r[0],
            "sensor_type": r[1],
            "count": r[2],
            "avg": r[3],
            "min": r[4],
            "max": r[5],
            "avg_latency": r[6],
            "avg_payload_size": r[7]
        }
        item.update(timing)
        result.append(item)
    conn.close()

    return jsonify(result)


@app.route("/api/collection-warnings")
def api_collection_warnings():
    warning_config = load_config().get("platform", {}).get("collection_delay_warning", {})
    default_enabled = "true" if warning_config.get("enabled", True) else "false"
    enabled = request.args.get("enabled", default=default_enabled).lower() not in ("0", "false", "no", "off")
    late_multiplier = request.args.get("late_multiplier", default=warning_config.get("late_multiplier", 2.0), type=float)
    collection_window = request.args.get("collection_window", default=warning_config.get("window", 200), type=int)
    collection_min_samples = request.args.get("collection_min_samples", default=warning_config.get("min_samples", 5), type=int)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT sensor_id, sensor_type, COUNT(*)
        FROM sensor_data
        WHERE sensor_id IS NOT NULL
        GROUP BY sensor_id, sensor_type
        ORDER BY sensor_id
    """)
    rows = cur.fetchall()

    result = []
    for sensor_id, sensor_type, count in rows:
        timing = calculate_collection_timing(
            cur,
            sensor_id,
            sensor_type,
            window=max(10, min(collection_window, 1000)),
            late_multiplier=max(1.0, late_multiplier),
            min_samples=max(2, collection_min_samples),
        )
        timing.update({
            "enabled": enabled,
            "sensor_id": sensor_id,
            "sensor_type": sensor_type,
            "count": count,
        })
        if not enabled and timing["collection_warning"]:
            timing["collection_status"] = "DISABLED"
            timing["collection_warning"] = False
        result.append(timing)

    conn.close()
    return jsonify(result)


@app.route("/api/unknown-topic-stats")
def api_unknown_topic_stats():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            topic,
            payload_type,
            COUNT(*) AS message_count,
            SUM(payload_size) AS total_bytes,
            ROUND(AVG(payload_size), 2) AS avg_bytes,
            ROUND(AVG(measured_latency), 6) AS avg_latency,
            COUNT(DISTINCT schema_hash) AS schema_count,
            MIN(received_at) AS first_received_at,
            MAX(received_at) AS last_received_at
        FROM unknown_payload_data
        GROUP BY topic, payload_type
        ORDER BY message_count DESC, topic ASC
    """)

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "topic": r[0],
            "payload_type": r[1],
            "count": r[2],
            "total_bytes": r[3] or 0,
            "total_kb": round((r[3] or 0) / 1024, 2),
            "avg_bytes": r[4] or 0,
            "avg_latency": r[5],
            "schema_count": r[6] or 0,
            "first_received_at": r[7],
            "last_received_at": r[8]
        }
        for r in rows
    ])


@app.route("/api/topic-stats")
def api_topic_stats():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            topic,
            payload_type,
            COUNT(*) AS message_count,
            SUM(payload_size) AS total_bytes,
            ROUND(AVG(measured_latency), 6) AS avg_latency,
            MIN(received_timestamp) AS first_received_at,
            MAX(received_timestamp) AS last_received_at
        FROM mqtt_experiment_log
        GROUP BY topic, payload_type
        ORDER BY message_count DESC, topic ASC
    """)

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "topic": r[0],
            "payload_type": r[1],
            "count": r[2],
            "total_bytes": r[3] or 0,
            "total_kb": round((r[3] or 0) / 1024, 2),
            "avg_latency": r[4],
            "first_received_at": r[5],
            "last_received_at": r[6]
        }
        for r in rows
    ])


@app.route("/api/latency-stats")
def api_latency_stats():
    """Topic/policy별 latency 기본 통계. SQLite만 사용하기 위해 p95/p99는 Python에서 계산."""
    topic = request.args.get("topic", default=None, type=str)
    limit = request.args.get("limit", default=5000, type=int)

    conn = get_db_connection()
    cur = conn.cursor()

    if topic:
        cur.execute("""
            SELECT topic, measured_latency, payload_size, qos, compression, encryption, integrity
            FROM mqtt_experiment_log
            WHERE topic = ? AND measured_latency IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (topic, limit))
    else:
        cur.execute("""
            SELECT topic, measured_latency, payload_size, qos, compression, encryption, integrity
            FROM mqtt_experiment_log
            WHERE measured_latency IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    conn.close()

    groups = {}
    for r in rows:
        key = (r[0], r[3], r[4], r[5], r[6])
        groups.setdefault(key, {"latencies": [], "payload_sizes": []})
        groups[key]["latencies"].append(float(r[1]))
        groups[key]["payload_sizes"].append(int(r[2] or 0))

    result = []
    for key, vals in groups.items():
        latencies = vals["latencies"]
        payload_sizes = vals["payload_sizes"]
        
        stats = compute_latency_stats(latencies)
        
        result.append({
            "topic": key[0],
            "qos": key[1],
            "compression": key[2],
            "encryption": key[3],
            "integrity": key[4],
            "count": stats.get("count", 0),
            "avg_latency": stats.get("avg", 0),
            "min_latency": stats.get("min", 0),
            "max_latency": stats.get("max", 0),
            "median_latency": stats.get("median"),
            "p95_latency": stats.get("p95"),
            "p99_latency": stats.get("p99"),
            "avg_payload_size": round(sum(payload_sizes) / len(payload_sizes), 2) if payload_sizes else 0,
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return jsonify(result)


@app.route("/api/latency-histogram")
def api_latency_histogram():
    topic = request.args.get("topic", default=None, type=str)
    bins = request.args.get("bins", default=20, type=int)
    limit = request.args.get("limit", default=1000, type=int)

    conn = get_db_connection()
    cur = conn.cursor()

    if topic:
        cur.execute("SELECT measured_latency FROM mqtt_experiment_log WHERE topic = ? AND measured_latency IS NOT NULL ORDER BY id DESC LIMIT ?", (topic, limit))
    else:
        cur.execute("SELECT measured_latency FROM mqtt_experiment_log WHERE measured_latency IS NOT NULL ORDER BY id DESC LIMIT ?", (limit,))

    rows = cur.fetchall()
    conn.close()

    latencies = [float(r[0]) for r in rows]
    hist = generate_histogram(latencies, bins=bins)
    
    return jsonify({"topic": topic or "all", "histogram": hist})


@app.route("/api/latency-trend")
def api_latency_trend():
    topic = request.args.get("topic", default=None, type=str)
    limit = request.args.get("limit", default=200, type=int)
    window = request.args.get("window", default=10, type=int)

    conn = get_db_connection()
    cur = conn.cursor()

    if topic:
        # Get oldest to newest for trend
        cur.execute("SELECT measured_latency FROM (SELECT id, measured_latency FROM mqtt_experiment_log WHERE topic = ? AND measured_latency IS NOT NULL ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (topic, limit))
    else:
        cur.execute("SELECT measured_latency FROM (SELECT id, measured_latency FROM mqtt_experiment_log WHERE measured_latency IS NOT NULL ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,))

    rows = cur.fetchall()
    conn.close()

    latencies = [float(r[0]) for r in rows]
    trend = compute_latency_trend(latencies, window_size=window)
    
    return jsonify({"topic": topic or "all", "trend": trend})


@app.route("/api/experiment-log")
def api_experiment_log():
    limit = request.args.get("limit", default=100, type=int)
    experiment_id = request.args.get("experiment_id", default=None, type=str)

    conn = get_db_connection()
    cur = conn.cursor()

    if experiment_id:
        cur.execute("""
            SELECT experiment_id, topic, sensor_id, sensor_type, seq,
                   publish_timestamp, received_timestamp, measured_latency,
                   payload_size, qos, compression, encryption, integrity,
                   is_unknown_schema, payload_type, platform_mode, policy_key,
                   latency_ms, schema_hash
            FROM mqtt_experiment_log
            WHERE experiment_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (experiment_id, limit))
    else:
        cur.execute("""
            SELECT experiment_id, topic, sensor_id, sensor_type, seq,
                   publish_timestamp, received_timestamp, measured_latency,
                   payload_size, qos, compression, encryption, integrity,
                   is_unknown_schema, payload_type, platform_mode, policy_key,
                   latency_ms, schema_hash
            FROM mqtt_experiment_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "experiment_id": r[0],
            "topic": r[1],
            "sensor_id": r[2],
            "sensor_type": r[3],
            "seq": r[4],
            "publish_timestamp": r[5],
            "received_timestamp": r[6],
            "measured_latency": r[7],
            "payload_size": r[8],
            "qos": r[9],
            "compression": r[10],
            "encryption": r[11],
            "integrity": r[12],
            "is_unknown_schema": bool(r[13]),
            "payload_type": r[14],
            "platform_mode": r[15] if len(r) > 15 else None,
            "policy_key": r[16] if len(r) > 16 else None,
            "latency_ms": r[17] if len(r) > 17 else None,
            "schema_hash": r[18] if len(r) > 18 else None
        }
        for r in rows
    ])


@app.route("/api/experiment-summary")
def api_experiment_summary():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            experiment_id,
            platform_mode,
            COUNT(*) AS total_messages,
            SUM(CASE WHEN is_unknown_schema = 1 THEN 1 ELSE 0 END) AS unknown_messages,
            COUNT(DISTINCT topic) AS topic_count,
            COUNT(DISTINCT policy_key) AS policy_count,
            ROUND(AVG(measured_latency), 6) AS avg_latency,
            ROUND(MAX(measured_latency), 6) AS max_latency,
            SUM(payload_size) AS total_bytes,
            MIN(received_timestamp) AS first_received_at,
            MAX(received_timestamp) AS last_received_at
        FROM mqtt_experiment_log
        GROUP BY experiment_id, platform_mode
        ORDER BY last_received_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify([
        {
            "experiment_id": r[0],
            "platform_mode": r[1],
            "total_messages": r[2],
            "unknown_messages": r[3] or 0,
            "unknown_ratio": round(((r[3] or 0) / r[2]) * 100, 2) if r[2] else 0,
            "topic_count": r[4],
            "policy_count": r[5],
            "avg_latency": r[6],
            "max_latency": r[7],
            "total_bytes": r[8] or 0,
            "total_kb": round((r[8] or 0) / 1024, 2),
            "first_received_at": r[9],
            "last_received_at": r[10],
        }
        for r in rows
    ])


@app.route("/api/policy-stats")
def api_policy_stats():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            policy_key, qos, compression, encryption, integrity,
            COUNT(*) AS message_count,
            ROUND(AVG(measured_latency), 6) AS avg_latency,
            ROUND(MAX(measured_latency), 6) AS max_latency,
            ROUND(AVG(payload_size), 2) AS avg_payload_size,
            SUM(CASE WHEN is_unknown_schema = 1 THEN 1 ELSE 0 END) AS unknown_messages
        FROM mqtt_experiment_log
        GROUP BY policy_key, qos, compression, encryption, integrity
        ORDER BY message_count DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return jsonify([
        {
            "policy_key": r[0],
            "qos": r[1],
            "compression": r[2],
            "encryption": r[3],
            "integrity": r[4],
            "count": r[5],
            "avg_latency": r[6],
            "max_latency": r[7],
            "avg_payload_size": r[8],
            "unknown_messages": r[9] or 0,
        }
        for r in rows
    ])


@app.route("/api/schema-stats")
def api_schema_stats():
    limit = request.args.get("limit", default=100, type=int)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_hash, payload_type, first_topic, last_topic, key_count,
               message_count, total_bytes, first_seen, last_seen, sample_payload_text,
               inferred_fields, semantic_summary, recommended_mapping, confidence_score,
               storage_strategy
        FROM unknown_schema_profile
        ORDER BY message_count DESC, last_seen DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    schema_hashes = [r[0] for r in rows]
    definitions = {}
    if schema_hashes:
        placeholders = ",".join(["?"] * len(schema_hashes))
        cur.execute(f"""
            SELECT schema_hash, display_name, target_type, status, field_mapping,
                   storage_strategy, scope_type, scope_id, notes, created_by_user_id,
                   approved_by_user_id, created_at, updated_at, approved_at
            FROM usi_schema_definitions
            WHERE schema_hash IN ({placeholders})
        """, schema_hashes)
        for d in cur.fetchall():
            definitions[d[0]] = {
                "schema_hash": d[0],
                "display_name": d[1],
                "target_type": d[2],
                "status": d[3],
                "field_mapping": safe_json_loads(d[4]) or {},
                "storage_strategy": d[5],
                "scope_type": d[6],
                "scope_id": d[7],
                "notes": d[8],
                "created_by_user_id": d[9],
                "approved_by_user_id": d[10],
                "created_at": d[11],
                "updated_at": d[12],
                "approved_at": d[13],
            }
    conn.close()
    return jsonify([
        {
            "schema_hash": r[0],
            "payload_type": r[1],
            "first_topic": r[2],
            "last_topic": r[3],
            "key_count": r[4] or 0,
            "message_count": r[5] or 0,
            "total_bytes": r[6] or 0,
            "total_kb": round((r[6] or 0) / 1024, 2),
            "first_seen": r[7],
            "last_seen": r[8],
            "sample_payload_text": r[9],
            "inferred_fields": safe_json_loads(r[10]) or [],
            "semantic_summary": safe_json_loads(r[11]) or {},
            "recommended_mapping": safe_json_loads(r[12]) or {},
            "confidence_score": r[13] or 0,
            "storage_strategy": r[14],
            "definition": definitions.get(r[0]),
        }
        for r in rows
    ])


@app.route("/api/schema-inference/<schema_hash>")
def api_schema_inference(schema_hash):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_hash, payload_type, first_topic, last_topic, schema_keys,
               inferred_fields, semantic_summary, recommended_mapping, confidence_score,
               storage_strategy, sample_payload_text, message_count, total_bytes,
               first_seen, last_seen
        FROM unknown_schema_profile
        WHERE schema_hash = ?
    """, (schema_hash,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "schema_not_found"}), 404
    cur.execute("""
        SELECT schema_hash, display_name, target_type, status, field_mapping,
               storage_strategy, scope_type, scope_id, notes, created_by_user_id,
               approved_by_user_id, created_at, updated_at, approved_at
        FROM usi_schema_definitions
        WHERE schema_hash = ?
    """, (schema_hash,))
    definition_row = cur.fetchone()
    conn.close()
    definition = None
    if definition_row:
        definition = {
            "schema_hash": definition_row[0],
            "display_name": definition_row[1],
            "target_type": definition_row[2],
            "status": definition_row[3],
            "field_mapping": safe_json_loads(definition_row[4]) or {},
            "storage_strategy": definition_row[5],
            "scope_type": definition_row[6],
            "scope_id": definition_row[7],
            "notes": definition_row[8],
            "created_by_user_id": definition_row[9],
            "approved_by_user_id": definition_row[10],
            "created_at": definition_row[11],
            "updated_at": definition_row[12],
            "approved_at": definition_row[13],
        }
    return jsonify({
        "schema_hash": row[0],
        "payload_type": row[1],
        "first_topic": row[2],
        "last_topic": row[3],
        "schema_keys": safe_json_loads(row[4]) or [],
        "inferred_fields": safe_json_loads(row[5]) or [],
        "semantic_summary": safe_json_loads(row[6]) or {},
        "recommended_mapping": safe_json_loads(row[7]) or {},
        "confidence_score": row[8] or 0,
        "storage_strategy": row[9],
        "sample_payload_text": row[10],
        "message_count": row[11] or 0,
        "total_bytes": row[12] or 0,
        "first_seen": row[13],
        "last_seen": row[14],
        "definition": definition,
    })


@app.route("/api/usi/profiles/<schema_hash>/definition", methods=["GET"])
def api_get_usi_definition(schema_hash):
    definition = fetch_usi_definition(schema_hash)
    if not definition:
        return jsonify({"error": "definition_not_found"}), 404
    return jsonify(definition)


@app.route("/api/usi/profiles/<schema_hash>/definition", methods=["POST"])
def api_save_usi_definition(schema_hash):
    data = request.get_json(silent=True) or {}
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT schema_hash FROM unknown_schema_profile WHERE schema_hash = ?", (schema_hash,))
    if not cur.fetchone():
        conn.close()
        return jsonify({"error": "schema_not_found"}), 404
    try:
        payload = validate_usi_definition_payload(data, require_mapping=False)
    except ValueError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400
    timestamp = now_iso()
    cur.execute("""
        INSERT INTO usi_schema_definitions
        (schema_hash, display_name, target_type, status, field_mapping, storage_strategy,
         scope_type, scope_id, notes, created_by_user_id, created_at, updated_at)
        VALUES (?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(schema_hash) DO UPDATE SET
            display_name = excluded.display_name,
            target_type = excluded.target_type,
            status = CASE
                WHEN usi_schema_definitions.status = 'APPROVED' THEN 'DRAFT'
                ELSE usi_schema_definitions.status
            END,
            field_mapping = excluded.field_mapping,
            storage_strategy = excluded.storage_strategy,
            scope_type = excluded.scope_type,
            scope_id = excluded.scope_id,
            notes = excluded.notes,
            updated_at = excluded.updated_at
    """, (
        schema_hash,
        payload["display_name"],
        payload["target_type"],
        json.dumps(payload["field_mapping"], ensure_ascii=False),
        payload["storage_strategy"],
        payload["scope_type"],
        payload["scope_id"],
        payload["notes"],
        current_user_id(),
        timestamp,
        timestamp,
    ))
    log_usi_mapping_action(cur, schema_hash, "SAVE_DRAFT", payload)
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "definition": fetch_usi_definition(schema_hash)})


@app.route("/api/usi/profiles/<schema_hash>/approve", methods=["POST"])
def api_approve_usi_definition(schema_hash):
    data = request.get_json(silent=True) or {}
    definition = fetch_usi_definition(schema_hash)
    if not definition:
        return jsonify({"error": "definition_not_found"}), 404
    try:
        validate_usi_definition_payload(definition, require_mapping=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    timestamp = now_iso()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE usi_schema_definitions
        SET status = 'APPROVED',
            approved_by_user_id = ?,
            approved_at = ?,
            updated_at = ?,
            notes = CASE WHEN ? != '' THEN ? ELSE notes END
        WHERE schema_hash = ?
    """, (
        current_user_id(),
        timestamp,
        timestamp,
        (data.get("notes") or "").strip(),
        (data.get("notes") or "").strip(),
        schema_hash,
    ))
    log_usi_mapping_action(cur, schema_hash, "APPROVE", {"notes": (data.get("notes") or "").strip()})
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "definition": fetch_usi_definition(schema_hash)})


@app.route("/api/usi/profiles/<schema_hash>/reject", methods=["POST"])
def api_reject_usi_definition(schema_hash):
    data = request.get_json(silent=True) or {}
    if not fetch_usi_definition(schema_hash):
        return jsonify({"error": "definition_not_found"}), 404
    timestamp = now_iso()
    notes = (data.get("notes") or "").strip()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE usi_schema_definitions
        SET status = 'REJECTED',
            notes = CASE WHEN ? != '' THEN ? ELSE notes END,
            updated_at = ?
        WHERE schema_hash = ?
    """, (notes, notes, timestamp, schema_hash))
    log_usi_mapping_action(cur, schema_hash, "REJECT", {"notes": notes})
    conn.commit()
    conn.close()
    return jsonify({"status": "ok", "definition": fetch_usi_definition(schema_hash)})


@app.route("/api/admin/usi/rebuild-profiles", methods=["POST"])
def api_admin_rebuild_usi_profiles():
    data = request.get_json(silent=True) or {}
    limit = int(data.get("limit") or 5000)
    limit = max(1, min(limit, 20000))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        WITH schema_agg AS (
            SELECT schema_hash,
                   MAX(id) AS latest_id,
                   COUNT(*) AS message_count,
                   SUM(payload_size) AS total_bytes,
                   MIN(received_at) AS first_seen,
                   MAX(received_at) AS last_seen
            FROM unknown_payload_data
            WHERE schema_hash IS NOT NULL AND trim(schema_hash) != ''
            GROUP BY schema_hash
            ORDER BY latest_id DESC
            LIMIT ?
        )
        SELECT u.topic, u.payload_type, u.payload_text, u.received_at,
               u.experiment_id, u.seq, u.publish_timestamp, u.received_timestamp,
               u.measured_latency, u.qos, u.compression, u.encryption, u.integrity,
               u.schema_hash, a.message_count, a.total_bytes, a.first_seen, a.last_seen
        FROM schema_agg a
        JOIN unknown_payload_data u ON u.id = a.latest_id
        ORDER BY a.latest_id DESC
    """, (limit,))
    rows = cur.fetchall()
    cur.execute("""
        SELECT topic, payload_type, payload_text, received_at, experiment_id, seq,
               publish_timestamp, received_timestamp, measured_latency, qos,
               compression, encryption, integrity, schema_hash,
               1 AS message_count, payload_size AS total_bytes, received_at AS first_seen, received_at AS last_seen
        FROM unknown_payload_data
        WHERE schema_hash IS NULL OR trim(schema_hash) = ''
        ORDER BY id DESC
        LIMIT ?
    """, (max(0, min(100, limit - len(rows))),))
    rows.extend(cur.fetchall())
    conn.close()

    rebuilt = 0
    failed = 0
    for r in rows:
        payload_text = r[2] or ""
        payload_type = r[1] or "unknown"
        parsed = None
        if payload_type not in ("non_json", "decryption_failed"):
            try:
                parsed = json.loads(payload_text)
            except Exception:
                parsed = None
        meta = {
            "topic": r[0],
            "experiment_id": r[4],
            "seq": r[5],
            "publish_timestamp": r[6],
            "received_timestamp": r[7] or r[3] or now_iso(),
            "measured_latency": r[8],
            "qos": r[9],
            "compression": r[10],
            "encryption": r[11],
            "integrity": r[12],
            "schema_hash": r[13] or (calc_schema_hash(parsed) if isinstance(parsed, dict) else calc_payload_fingerprint(payload_text)),
            "payload_size": len(payload_text.encode("utf-8")),
        }
        try:
            upsert_unknown_schema_profile(meta, payload_type, payload_text, parsed)
            conn = get_db_connection()
            conn.execute("""
                UPDATE unknown_schema_profile
                SET message_count = ?,
                    total_bytes = ?,
                    first_seen = ?,
                    last_seen = ?
                WHERE schema_hash = ?
            """, (
                int(r[14] or 1),
                int(r[15] or meta["payload_size"]),
                r[16] or meta["received_timestamp"],
                r[17] or meta["received_timestamp"],
                meta["schema_hash"],
            ))
            conn.commit()
            conn.close()
            rebuilt += 1
        except Exception as exc:
            failed += 1
            print(f"[USI] profile rebuild failed: {exc}")

    log_audit_event("USI_PROFILE_REBUILD", "unknown_schema_profile", None, {"limit": limit, "rebuilt": rebuilt, "failed": failed})
    return jsonify({"status": "ok", "limit": limit, "rebuilt": rebuilt, "failed": failed})


@app.route("/api/schema-samples")
def api_schema_samples():
    schema_hash = request.args.get("schema_hash", default=None, type=str)
    limit = request.args.get("limit", default=30, type=int)
    if not schema_hash:
        return jsonify({"error": "schema_hash is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT topic, payload_type, payload_size, payload_text, error_message,
               received_at, measured_latency, experiment_id, seq, schema_hash
        FROM unknown_payload_data
        WHERE schema_hash = ?
        ORDER BY id DESC
        LIMIT ?
    """, (schema_hash, limit))
    rows = cur.fetchall()
    conn.close()
    return jsonify([
        {
            "topic": r[0],
            "payload_type": r[1],
            "payload_size": r[2],
            "payload_text": r[3],
            "error_message": r[4],
            "received_at": r[5],
            "measured_latency": r[6],
            "experiment_id": r[7],
            "seq": r[8],
            "schema_hash": r[9],
        }
        for r in rows
    ])


@app.route("/api/unknown-payloads")
def api_unknown_payloads():
    limit = request.args.get("limit", default=100, type=int)
    topic = request.args.get("topic", default=None, type=str)

    conn = get_db_connection()
    cur = conn.cursor()

    if topic:
        cur.execute("""
            SELECT topic, payload_type, payload_size, payload_text, error_message,
                   received_at, measured_latency, experiment_id, seq, schema_hash
            FROM unknown_payload_data
            WHERE topic = ?
            ORDER BY id DESC
            LIMIT ?
        """, (topic, limit))
    else:
        cur.execute("""
            SELECT topic, payload_type, payload_size, payload_text, error_message,
                   received_at, measured_latency, experiment_id, seq, schema_hash
            FROM unknown_payload_data
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "topic": r[0],
            "payload_type": r[1],
            "payload_size": r[2],
            "payload_text": r[3],
            "error_message": r[4],
            "received_at": r[5],
            "measured_latency": r[6],
            "experiment_id": r[7],
            "seq": r[8],
            "schema_hash": r[9] if len(r) > 9 else None
        }
        for r in rows
    ])


@app.route("/api/chart/<sensor_id>")
def api_chart(sensor_id):
    limit = request.args.get("limit", default=200, type=int)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT timestamp, value
        FROM sensor_data
        WHERE sensor_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (sensor_id, limit))

    rows = cur.fetchall()
    conn.close()

    rows.reverse()

    return jsonify({
        "labels": [format_kst_time_label(r[0]) for r in rows],
        "values": [r[1] for r in rows]
    })


def sensor_definition_from_row(row):
    sensor = {
        "id": row[1],
        "type": row[2],
        "unit": row[3] or "",
        "topic": row[4],
        "definition_source": row[5] or "SIMULATOR",
        "source": row[5] or "SIMULATOR",
        "owner_user_id": row[6],
        "owner_name": row[7] or "",
        "owner_email": row[8] or "",
        "payload_schema_mode": row[9] or "defined_sensor",
        "policy": row[10] or "none",
        "min": row[11],
        "max": row[12],
        "start": row[13],
        "step": row[14],
        "interval": row[15],
        "mode": row[16] or "",
        "enabled": bool(row[18]),
    }
    color_rule = safe_json_loads(row[17])
    if color_rule:
        sensor["color_rule"] = color_rule
    return sensor


def fetch_sensor_definitions(enabled_only=False, definition_source=None):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        SELECT sd.id, sd.sensor_id, sd.sensor_type, sd.unit, sd.topic,
               sd.definition_source, sd.owner_user_id, u.name, u.email,
               sd.payload_schema_mode, sd.policy, sd.min_value, sd.max_value,
               sd.start_value, sd.step_value, sd.interval_seconds,
               sd.simulation_mode, sd.color_rule_json, sd.enabled
        FROM sensor_definitions sd
        LEFT JOIN users u ON u.id = sd.owner_user_id
    """
    clauses = []
    params = []
    if enabled_only:
        clauses.append("sd.enabled = ?")
        params.append(1)
    if definition_source:
        clauses.append("UPPER(sd.definition_source) = ?")
        params.append(str(definition_source).upper())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY sd.definition_source, sd.sensor_id"
    cur.execute(sql, params)
    sensors = [sensor_definition_from_row(row) for row in cur.fetchall()]
    conn.close()
    return sensors


def optional_float(value, field_name):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_{field_name}") from exc


def normalize_sensor_definition(data):
    sensor_id = str(data.get("id") or "").strip()
    sensor_type = str(data.get("type") or "").strip()
    if not sensor_id or not sensor_type:
        raise ValueError("sensor_id_and_type_required")

    definition_source = str(data.get("definition_source") or data.get("source") or "USER").strip().upper()
    if definition_source not in ("SIMULATOR", "USER"):
        raise ValueError("invalid_sensor_definition_source")

    owner_user_id = data.get("owner_user_id")
    if definition_source == "USER":
        if current_user_is_admin() and owner_user_id:
            owner_user_id = int(owner_user_id)
        else:
            owner_user_id = current_user_id()
        if not owner_user_id:
            raise ValueError("owner_user_required")
        owner_context = fetch_user_topic_context(owner_user_id)
        if not owner_context:
            raise ValueError("invalid_owner_user_id")
        if owner_context["status"] != "ACTIVE":
            raise ValueError("owner_user_not_active")
    else:
        owner_user_id = None

    config = load_config()
    topic = str(data.get("topic") or "").strip()
    if not topic:
        prefix = config.get("mqtt", {}).get("topic_prefix", "iot/sensor")
        topic = f"{prefix}/{normalize_topic_part(sensor_type, 'sensor')}/{normalize_topic_part(sensor_id, 'sensor')}"
    topic = clean_mqtt_publish_topic(topic)

    color_rule = data.get("color_rule")
    if color_rule is not None and not isinstance(color_rule, dict):
        raise ValueError("invalid_color_rule")

    return {
        "id": sensor_id,
        "type": sensor_type,
        "unit": str(data.get("unit") or "").strip(),
        "topic": topic,
        "definition_source": definition_source,
        "source": definition_source,
        "owner_user_id": owner_user_id,
        "payload_schema_mode": str(data.get("payload_schema_mode") or "defined_sensor").strip(),
        "policy": str(data.get("policy") or "none").strip(),
        "min": optional_float(data.get("min"), "min"),
        "max": optional_float(data.get("max"), "max"),
        "start": optional_float(data.get("start"), "start"),
        "step": optional_float(data.get("step"), "step"),
        "interval": optional_float(data.get("interval"), "interval"),
        "mode": str(data.get("mode") or "").strip(),
        "color_rule": color_rule,
        "enabled": bool(data.get("enabled", True)),
    }


def sensor_definition_db_values(sensor):
    timestamp = now_iso()
    return (
        sensor["id"],
        sensor["type"],
        sensor["unit"],
        sensor["topic"],
        sensor["definition_source"],
        sensor["owner_user_id"],
        sensor["payload_schema_mode"],
        sensor["policy"],
        sensor["min"],
        sensor["max"],
        sensor["start"],
        sensor["step"],
        sensor["interval"],
        sensor["mode"],
        json.dumps(sensor.get("color_rule"), ensure_ascii=False) if sensor.get("color_rule") else None,
        1 if sensor.get("enabled", True) else 0,
        timestamp,
        timestamp,
    )


@app.route("/api/config", methods=["GET"])
def api_get_config():
    config = load_config()
    config["sensors"] = fetch_sensor_definitions()
    return jsonify(config)


@app.route("/api/sensors", methods=["GET"])
def api_get_sensors():
    source = request.args.get("source")
    return jsonify(fetch_sensor_definitions(definition_source=source))


@app.route("/api/sensors", methods=["POST"])
def api_add_sensor():
    data = request.get_json(silent=True) or {}
    try:
        sensor = normalize_sensor_definition(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO sensor_definitions
            (sensor_id, sensor_type, unit, topic, definition_source, owner_user_id,
             payload_schema_mode, policy,
             min_value, max_value, start_value, step_value, interval_seconds,
             simulation_mode, color_rule_json, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sensor_definition_db_values(sensor))
        row_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.close()
        error = "sensor_topic_already_exists" if "topic" in str(exc).lower() else "sensor_id_already_exists"
        return jsonify({"error": error}), 400
    conn.close()

    log_audit_event("SENSOR_DEFINITION_CREATED", "sensor_definitions", row_id, {
        "sensor_id": sensor["id"],
        "topic": sensor["topic"],
        "definition_source": sensor["definition_source"],
        "owner_user_id": sensor["owner_user_id"],
    })
    return jsonify({"message": "sensor added", "id": row_id, "sensor": sensor})


@app.route("/api/sensors/<sensor_id>", methods=["PUT"])
def api_update_sensor(sensor_id):
    data = request.get_json(silent=True) or {}
    data["id"] = sensor_id
    try:
        sensor = normalize_sensor_definition(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM sensor_definitions WHERE sensor_id = ?", (sensor_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "sensor not found"}), 404
    try:
        values = sensor_definition_db_values(sensor)
        cur.execute("""
            UPDATE sensor_definitions
            SET sensor_type = ?, unit = ?, topic = ?, definition_source = ?,
                owner_user_id = ?, payload_schema_mode = ?, policy = ?,
                min_value = ?, max_value = ?, start_value = ?, step_value = ?,
                interval_seconds = ?, simulation_mode = ?, color_rule_json = ?,
                enabled = ?, updated_at = ?
            WHERE sensor_id = ?
        """, values[1:16] + (values[17], sensor_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "sensor_topic_already_exists"}), 400
    conn.close()

    log_audit_event("SENSOR_DEFINITION_UPDATED", "sensor_definitions", row[0], {
        "sensor_id": sensor_id,
        "topic": sensor["topic"],
        "definition_source": sensor["definition_source"],
        "owner_user_id": sensor["owner_user_id"],
    })
    return jsonify({"message": "sensor updated", "sensor": sensor})


@app.route("/api/sensors/<sensor_id>", methods=["DELETE"])
def api_delete_sensor(sensor_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, topic FROM sensor_definitions WHERE sensor_id = ?", (sensor_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "sensor not found"}), 404
    cur.execute("DELETE FROM sensor_definitions WHERE sensor_id = ?", (sensor_id,))
    conn.commit()
    conn.close()

    log_audit_event("SENSOR_DEFINITION_DELETED", "sensor_definitions", row[0], {
        "sensor_id": sensor_id,
        "topic": row[1],
    })
    return jsonify({"message": "sensor deleted"})


@app.route("/api/queue-stats")
def api_queue_stats():
    if not queue_monitor:
        return jsonify({"error": "Queue monitor not available"}), 501
    stats = queue_monitor.get_queue_stats()
    db_stats = get_db_writer_stats()
    stats["callback_backlog"] = stats.get("backlog", 0)
    stats["db_writer"] = db_stats
    stats["db_writer_queue_depth"] = db_stats.get("queue_depth", 0)
    stats["combined_backlog"] = int(stats.get("callback_backlog", 0)) + int(stats.get("db_writer_queue_depth", 0))
    stats["backlog"] = stats["combined_backlog"]
    return jsonify(stats)


@app.route("/api/topic-rate")
def api_topic_rate():
    if not queue_monitor:
        return jsonify({"error": "Queue monitor not available"}), 501
    return jsonify(queue_monitor.get_topic_rates())


@app.route("/api/backlog-estimation")
def api_backlog_estimation():
    if not queue_monitor:
        return jsonify({"error": "Queue monitor not available"}), 501
    stats = queue_monitor.get_queue_stats()
    db_stats = get_db_writer_stats()
    estimated_backlog = int(stats.get("backlog", 0)) + int(db_stats.get("queue_depth", 0))
    return jsonify({
        "estimated_backlog": estimated_backlog,
        "callback_backlog": stats.get("backlog", 0),
        "db_writer_queue_depth": db_stats.get("queue_depth", 0),
        "trend": "stable"
    })


@app.route("/api/apr/recommend", methods=["POST"])
def api_apr_recommend():
    if apr_engine is None:
        return jsonify({"error": "APR engine not available"}), 501
    
    data = request.json or {}
    payload_size = data.get("payload_size", 0)
    network_latency_ms = data.get("network_latency_ms", 0.0)
    queue_depth = data.get("queue_depth", 0)
    topic = data.get("topic", "unknown")
    schema_type = data.get("schema_type", "unknown")
    
    recommendation = apr_engine.recommend(
        payload_size=payload_size,
        network_latency_ms=network_latency_ms,
        queue_depth=queue_depth,
        topic=topic,
        schema_type=schema_type
    )
    
    return jsonify(recommendation)


@app.route("/api/apr/collection/start", methods=["POST"])
def api_apr_collection_start():
    """
    관리자 트리거: 특정 센서의 데이터 수집 모드 시작.
    device에 'collect' 명령을 policy topic으로 전송 → device가 enriched payload 포함 시작.
    """
    global apr_collection_active, apr_metrics_buffer
    data = request.json or {}
    sensor_id = data.get("sensor_id", "")
    if not sensor_id:
        return jsonify({"error": "sensor_id 필수"}), 400

    # 수집 모드 활성화 및 버퍼 초기화
    apr_collection_active[sensor_id] = True
    apr_metrics_buffer[sensor_id] = []

    # device에 'collect' 명령 전송 (device가 추가 메트릭 포함하도록 지시)
    try:
        config = load_config()
        policy_topic = f"iot/sensor/policy/{sensor_id}"
        cmd = {"command": "collect", "message": "추가 메트릭 수집 요청"}
        if publish_single_to_any_broker:
            publish_single_to_any_broker(policy_topic, json.dumps(cmd), config.get("mqtt", {}), qos=1)
        else:
            import paho.mqtt.publish as mqtt_publish
            mqtt_publish.single(
                policy_topic,
                payload=json.dumps(cmd),
                hostname=config["mqtt"]["broker"],
                port=config["mqtt"]["port"],
                qos=1
            )
        print(f"[APR Admin] [{sensor_id}] 수집 모드 시작 → 명령 전송: {policy_topic}")
    except Exception as e:
        print(f"[APR Admin] collect 명령 전송 실패: {e}")

    return jsonify({"status": "started", "sensor_id": sensor_id, "message": "수집 모드 시작됨"})


@app.route("/api/apr/collection/status", methods=["GET"])
def api_apr_collection_status():
    """수집 모드 현황 및 버퍼 건수 조회"""
    runtime = get_platform_runtime_config()
    status = {}
    sensor_ids = set(apr_collection_active.keys()) | set(apr_metrics_buffer.keys()) | set(apr_policy_cache.keys())
    for sid in sorted(sensor_ids):
        active = apr_collection_active.get(sid, False)
        status[sid] = {
            "active": active,
            "auto_apr": bool(runtime.get("enable_apr") and runtime.get("auto_apr")),
            "buffered_samples": len(apr_metrics_buffer.get(sid, [])),
            "min_required": runtime.get("apr_min_samples", APR_MIN_SAMPLES),
            "ready_to_evaluate": len(apr_metrics_buffer.get(sid, [])) >= int(runtime.get("apr_min_samples", APR_MIN_SAMPLES)),
            "auto_inflight": sid in apr_auto_evaluation_inflight,
            "current_policy": apr_policy_cache.get(sid)
        }
    return jsonify(status)


@app.route("/api/apr/collection/evaluate", methods=["POST"])
def api_apr_collection_evaluate():
    """
    관리자 트리거: 수집된 메트릭으로 XGBoost 추론 후 최적 정책을 device C2 push.
    수집 완료 후 버퍼 초기화 및 수집 모드 해제.
    """
    data = request.json or {}
    sensor_id = data.get("sensor_id", "")
    if not sensor_id:
        return jsonify({"error": "sensor_id 필수"}), 400

    result = apr_evaluate_and_push(sensor_id)
    return jsonify(result)


@app.route("/api/apr/publish-with-policy", methods=["POST"])
def api_apr_publish_with_policy():
    from policy.codec import encode_payload
    
    data = request.json or {}
    policy = data.get("policy", {})
    topic = data.get("topic", "iot/sensor/normal")
    payload_size = data.get("payload_size", 256)
    
    # 1. Create a dummy telemetry payload
    telemetry = {
        "sensor_id": "apr_dashboard_client",
        "sensor_type": "temperature",
        "value": 24.5,
        "unit": "°C",
        "timestamp": now_iso()
    }
    
    # 2. Add padding to match payload_size if needed
    telemetry_str = json.dumps(telemetry)
    current_len = len(telemetry_str)
    if current_len < payload_size:
        padding_size = payload_size - current_len - 15  # Account for padding key overhead
        if padding_size > 0:
            telemetry["padding"] = "A" * padding_size
            
    # 3. Dynamic encode based on recommendations
    try:
        config = load_config()
        
        # We need an experiment_id to make it log as an experiment run
        experiment_id = f"EXP_APR_DASH_{int(time.time())}"
        
        telemetry["experiment_id"] = experiment_id
        telemetry["platform_mode"] = get_platform_runtime_config().get("mode")
        telemetry["seq"] = 0
        telemetry["topic"] = topic
        telemetry["publish_timestamp"] = telemetry["timestamp"]
        
        # Encode
        envelope = encode_payload(telemetry, policy, seq=0, experiment_id=experiment_id)
        
        # Extract sensor_id from topic to identify the device
        topic_parts = topic.split('/')
        sensor_id = topic_parts[-1] if topic_parts else "normal"
        
        # Publish the new policy combination order to device-dependent control topic
        policy_topic = f"iot/sensor/policy/{sensor_id}"
        if publish_single_to_any_broker:
            publish_single_to_any_broker(policy_topic, json.dumps(policy), config.get("mqtt", {}), qos=1)
        else:
            import paho.mqtt.publish as publish
            publish.single(
                policy_topic,
                payload=json.dumps(policy),
                hostname=config["mqtt"]["broker"],
                port=config["mqtt"]["port"],
                qos=1
            )
        print(f"[*] Sent dynamic policy combination order to device topic: {policy_topic} -> {policy}")
        
        # Publish the telemetry validation packet to the target data topic
        if publish_single_to_any_broker:
            publish_single_to_any_broker(topic, json.dumps(envelope), config.get("mqtt", {}), qos=policy.get("qos", 0))
        else:
            import paho.mqtt.publish as publish
            publish.single(
                topic,
                payload=json.dumps(envelope),
                hostname=config["mqtt"]["broker"],
                port=config["mqtt"]["port"],
                qos=policy.get("qos", 0)
            )
        
        return jsonify({
            "status": "success",
            "message": f"Successfully pushed policy combo order to '{policy_topic}' and published verification payload to '{topic}'",
            "policy": policy,
            "experiment_id": experiment_id
        })
    except Exception as e:
        return jsonify({"error": f"Failed to push policy or publish telemetry: {str(e)}"}), 500


def calculate_jaccard(set1, set2):
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union


@app.route("/api/schema-clusters")
def api_schema_clusters():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT schema_hash, schema_keys, message_count, payload_type FROM unknown_schema_profile")
    rows = cur.fetchall()
    conn.close()
    
    schemas = []
    for r in rows:
        hsh, keys_json, count, p_type = r
        try:
            keys = set(json.loads(keys_json)) if keys_json else set([p_type])
        except Exception:
            keys = set([p_type])
        schemas.append({
            "schema_hash": hsh,
            "keys": keys,
            "keys_list": list(keys),
            "message_count": count,
            "payload_type": p_type
        })
        
    threshold = 0.5
    clusters = []
    visited = set()
    
    for i, s1 in enumerate(schemas):
        if s1["schema_hash"] in visited:
            continue
            
        cluster = [s1]
        visited.add(s1["schema_hash"])
        
        for j, s2 in enumerate(schemas):
            if s2["schema_hash"] in visited:
                continue
            sim = calculate_jaccard(s1["keys"], s2["keys"])
            if sim >= threshold:
                cluster.append(s2)
                visited.add(s2["schema_hash"])
                
        clusters.append(cluster)
        
    formatted_clusters = []
    for idx, cl in enumerate(clusters):
        formatted_clusters.append({
            "cluster_id": f"CLUSTER_{idx+1}",
            "schemas": [
                {
                    "schema_hash": s["schema_hash"],
                    "keys": s["keys_list"],
                    "message_count": s["message_count"],
                    "payload_type": s["payload_type"]
                }
                for s in cl
            ]
        })
        
    return jsonify(formatted_clusters)


@app.route("/api/schema-evolution")
def api_schema_evolution():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT schema_hash, received_at, topic, payload_size 
        FROM unknown_payload_data 
        ORDER BY received_at ASC
    """)
    rows = cur.fetchall()
    conn.close()
    
    timeline = []
    for r in rows:
        timeline.append({
            "schema_hash": r[0] or "unknown",
            "timestamp": r[1],
            "topic": r[2],
            "payload_size": r[3]
        })
    return jsonify(timeline)


@app.route("/api/experiment/run", methods=["POST"])
def api_run_experiment():
    import subprocess
    import threading
    
    data = request.json or {}
    exp_type = data.get("type")
    
    script_map = {
        "qos": "experiment/qos_test.py",
        "payload_size": "experiment/payload_size_test.py",
        "queue": "experiment/queue_test.py",
        "schema": "experiment/schema_variation_test.py",
        "apr": "experiment/apr_validation.py",
        "voice": "experiment/voice_stream_test.py"
    }
    
    script = script_map.get(exp_type)
    if not script:
        return jsonify({"error": "Invalid experiment type"}), 400
        
    import sys
    cmd = [sys.executable, script]
    if exp_type == "voice":
        duration = data.get("duration", 15)
        fps = data.get("fps", 50)
        prebuffer = data.get("prebuffer", 300)
        drop_on = data.get("drop_on", False)
        qos = data.get("qos", 0)
        
        cmd += [
            "--duration", str(duration),
            "--fps", str(fps),
            "--prebuffer", str(prebuffer),
            "--qos", str(qos)
        ]
        if drop_on:
            cmd.append("--drop-on")
            
    def run_script():
        try:
            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"Error running experiment {exp_type}: {e}")
            
    threading.Thread(target=run_script).start()
    return jsonify({"message": f"Experiment {exp_type} started in the background"})


@app.route("/api/voice/results", methods=["GET"])
def api_voice_results():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT experiment_id, scenario, topic, qos, fps, prebuffer_ms, max_queue_ms, drop_on, duration_s,
               received_frames, played_ticks, played_frames, gap_inserted, gap_ratio_pct,
               latency_avg_ms, latency_p95_ms, latency_p99_ms, latency_max_ms, jitter_ms, created_at
        FROM voice_experiment_results
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "experiment_id": r[0],
            "scenario": r[1],
            "topic": r[2],
            "qos": r[3],
            "fps": r[4],
            "prebuffer_ms": r[5],
            "max_queue_ms": r[6],
            "drop_on": bool(r[7]),
            "duration_s": r[8],
            "received_frames": r[9],
            "played_ticks": r[10],
            "played_frames": r[11],
            "gap_inserted": r[12],
            "gap_ratio_pct": r[13],
            "latency_avg_ms": r[14],
            "latency_p95_ms": r[15],
            "latency_p99_ms": r[16],
            "latency_max_ms": r[17],
            "jitter_ms": r[18],
            "created_at": r[19]
        })
    return jsonify(results)


if __name__ == "__main__":
    app_port = DEFAULT_APP_PORT
    assert_port_available(app_port)
    db_health = check_db_file_health()
    print(f"[startup] DB health: {db_health}")
    acquire_system_lock()
    init_db()
    table_health = validate_required_tables()
    print(f"[startup] DB schema: {table_health}")
    if db_manager:
        db_manager.db_name = DB_NAME
        db_writer_config = get_platform_runtime_config().get("db_writer", {})
        db_manager.configure(
            batch_size=db_writer_config.get("batch_size"),
            flush_interval=db_writer_config.get("flush_interval"),
            max_queue_size=db_writer_config.get("max_queue_size"),
        )
        db_manager.start()
    try:
        mqtt_client = start_mqtt()
        mqtt_startup_error = None
    except Exception as exc:
        mqtt_client = None
        mqtt_startup_error = str(exc)
        print(f"[startup] MQTT unavailable; dashboard will continue without broker connection: {exc}")
    try:
        app.run(host="0.0.0.0", port=app_port, debug=False, use_reloader=False)
    finally:
        graceful_shutdown()
