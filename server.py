from flask import Flask, render_template, jsonify, request
import sqlite3
import json
import hashlib
import time
import threading
import html
import os
import atexit
import socket
import uuid
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt

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

DB_NAME = os.environ.get("DB_NAME", "iot_data.db")
DB_JOURNAL_MODE = os.environ.get("DB_JOURNAL_MODE", "WAL").upper()
DB_BUSY_TIMEOUT_MS = int(os.environ.get("DB_BUSY_TIMEOUT_MS", "30000"))
SYSTEM_MODE = os.environ.get("SYSTEM_MODE", "windows")
SYSTEM_LOCK_FILE = os.environ.get("SYSTEM_LOCK_FILE", os.path.join("runtime", "iot_dashboard.lock"))
SYSTEM_LOCK_STALE_SECONDS = int(os.environ.get("SYSTEM_LOCK_STALE_SECONDS", "30"))
CONFIG_FILE = "config.json"
POLICY_TOPIC_PREFIX = "iot/sensor/policy/"
KST = timezone(timedelta(hours=9))
system_owner_id = str(uuid.uuid4())
system_lock_active = False
system_lock_stop_event = threading.Event()
system_lock_thread = None
mqtt_client = None

# 사전에 정의된 센서 데이터로 인정할 최소 필드
DEFINED_SENSOR_REQUIRED_FIELDS = {
    "sensor_id",
    "sensor_type",
    "value",
    "unit",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def add_column_if_missing(cur, table_name, column_name, column_type):
    cur.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cur.fetchall()]
    if column_name not in columns:
        cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def init_db():
    conn = get_db_connection()
    conn.execute(f"PRAGMA journal_mode={DB_JOURNAL_MODE}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
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
            sample_payload_text TEXT,
            message_count INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        )
    """)

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

    conn.commit()
    conn.close()


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


def upsert_unknown_schema_profile(meta, payload_type, payload_text, data=None):
    if db_manager:
        db_manager.upsert_unknown_schema_profile(meta, payload_type, payload_text, data)
        return

    schema_hash = meta.get("schema_hash") or calc_payload_fingerprint(payload_text)
    received_at = meta.get("received_timestamp") or now_iso()
    schema_keys = get_schema_keys_text(data) if isinstance(data, dict) else ""
    key_count = len(json.loads(schema_keys)) if schema_keys else 0
    payload_size = int(meta.get("payload_size") or len(payload_text.encode("utf-8")))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO unknown_schema_profile
        (schema_hash, payload_type, first_topic, last_topic, schema_keys, key_count,
         sample_payload_text, message_count, total_bytes, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
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
        "qos": int(policy.get("qos", 0)),
        "compression": policy.get("compression", "none") or "none",
        "encryption": policy.get("encryption", "none") or "none",
        "integrity": policy.get("integrity", "none") or "none",
    }


def policies_equal(left, right):
    return normalize_policy(left) == normalize_policy(right)


def publish_policy_to_device(sensor_id, policy):
    config = load_config()
    policy_topic = f"iot/sensor/policy/{sensor_id}"
    normalized = normalize_policy(policy)
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
               message_count, total_bytes, first_seen, last_seen, sample_payload_text
        FROM unknown_schema_profile
        ORDER BY message_count DESC, last_seen DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
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
        }
        for r in rows
    ])


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


@app.route("/api/config", methods=["GET"])
def api_get_config():
    return jsonify(load_config())


@app.route("/api/sensors", methods=["GET"])
def api_get_sensors():
    config = load_config()
    return jsonify(config.get("sensors", []))


@app.route("/api/sensors", methods=["POST"])
def api_add_sensor():
    data = request.json
    config = load_config()

    sensors = config.get("sensors", [])

    for s in sensors:
        if s["id"] == data["id"]:
            return jsonify({"error": "sensor id already exists"}), 400

    if not data.get("topic"):
        topic_prefix = config["mqtt"]["topic_prefix"]
        data["topic"] = f"{topic_prefix}/{data['id']}"

    sensors.append(data)
    config["sensors"] = sensors
    save_config(config)

    return jsonify({"message": "sensor added"})


@app.route("/api/sensors/<sensor_id>", methods=["PUT"])
def api_update_sensor(sensor_id):
    data = request.json
    config = load_config()

    sensors = config.get("sensors", [])

    for i, s in enumerate(sensors):
        if s["id"] == sensor_id:
            sensors[i] = data
            config["sensors"] = sensors
            save_config(config)
            return jsonify({"message": "sensor updated"})

    return jsonify({"error": "sensor not found"}), 404


@app.route("/api/sensors/<sensor_id>", methods=["DELETE"])
def api_delete_sensor(sensor_id):
    config = load_config()

    sensors = config.get("sensors", [])
    sensors = [s for s in sensors if s["id"] != sensor_id]

    config["sensors"] = sensors
    save_config(config)

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
    acquire_system_lock()
    init_db()
    if db_manager:
        db_manager.db_name = DB_NAME
        db_writer_config = get_platform_runtime_config().get("db_writer", {})
        db_manager.configure(
            batch_size=db_writer_config.get("batch_size"),
            flush_interval=db_writer_config.get("flush_interval"),
            max_queue_size=db_writer_config.get("max_queue_size"),
        )
        db_manager.start()
    mqtt_client = start_mqtt()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    finally:
        graceful_shutdown()
