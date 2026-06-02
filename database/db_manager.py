import queue
import sqlite3
import threading
import time
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class DBManager:
    def __init__(self, db_name="iot_data.db", batch_size=50, flush_interval=0.1, max_queue_size=10000):
        self.db_name = db_name
        self.batch_size = int(batch_size)
        self.flush_interval = float(flush_interval)
        self.max_queue_size = int(max_queue_size)
        self.queue = queue.Queue(maxsize=self.max_queue_size)
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.stats = {
            "queued": 0,
            "committed": 0,
            "failed": 0,
            "dropped": 0,
            "flush_count": 0,
            "last_flush_size": 0,
            "last_flush_duration_ms": 0.0,
            "last_error": None,
        }
        
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        logger.info("Database async writer started.")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        logger.info("Database async writer stopped.")

    def configure(self, batch_size=None, flush_interval=None, max_queue_size=None):
        if batch_size is not None:
            self.batch_size = max(1, int(batch_size))
        if flush_interval is not None:
            self.flush_interval = max(0.01, float(flush_interval))
        if max_queue_size is not None and int(max_queue_size) != self.max_queue_size and not self.running:
            self.max_queue_size = max(1, int(max_queue_size))
            self.queue = queue.Queue(maxsize=self.max_queue_size)

    def _enqueue(self, task):
        try:
            self.queue.put_nowait(task)
            with self.lock:
                self.stats["queued"] += 1
            return True
        except queue.Full:
            with self.lock:
                self.stats["dropped"] += 1
            logger.warning("Database writer queue is full; dropping task.")
            return False
        
    def insert_sensor_data(self, data, meta):
        return self._enqueue(("sensor_data", (data, meta)))
        
    def insert_unknown_payload(self, topic, payload_text, payload_type="unknown", error_message=None, meta=None):
        if meta is None:
            # We will pack the base meta. We can evaluate length here.
            payload_size = len(payload_text.encode("utf-8"))
            meta = {
                "topic": topic,
                "payload_size": payload_size,
                "received_timestamp": now_iso()
            }
        return self._enqueue(("unknown_payload", (topic, payload_text, payload_type, error_message, meta)))
        
    def insert_experiment_log(self, meta, payload_type, is_unknown_schema, payload_text=None, runtime_mode=None, enable_log=True):
        if not enable_log:
            return
        return self._enqueue(("experiment_log", (meta, payload_type, is_unknown_schema, payload_text, runtime_mode)))
        
    def upsert_unknown_schema_profile(self, meta, payload_type, payload_text, data=None):
        return self._enqueue(("schema_profile", (meta, payload_type, payload_text, data)))

    def get_queue_depth(self):
        return self.queue.qsize()

    def get_stats(self):
        with self.lock:
            stats = dict(self.stats)
        stats.update({
            "queue_depth": self.get_queue_depth(),
            "running": self.running,
            "batch_size": self.batch_size,
            "flush_interval": self.flush_interval,
            "max_queue_size": self.max_queue_size,
        })
        return stats
        
    def _worker(self):
        busy_timeout_ms = int(os.environ.get("DB_BUSY_TIMEOUT_MS", "30000"))
        conn = sqlite3.connect(
            self.db_name,
            timeout=busy_timeout_ms / 1000,
            check_same_thread=False
        )
        journal_mode = os.environ.get("DB_JOURNAL_MODE", "WAL").upper()
        conn.execute(f"PRAGMA journal_mode={journal_mode}")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        last_flush = time.time()
        buffer = []
        
        while self.running or not self.queue.empty():
            try:
                task = self.queue.get(timeout=0.05)
                buffer.append(task)
            except queue.Empty:
                pass
                
            now = time.time()
            if buffer and (len(buffer) >= self.batch_size or (now - last_flush) >= self.flush_interval):
                self._flush_buffer(conn, buffer)
                buffer.clear()
                last_flush = now
                
        if buffer:
            self._flush_buffer(conn, buffer)
        conn.close()

    def _flush_buffer(self, conn, buffer):
        started_at = time.time()
        max_retries = int(os.environ.get("DB_LOCK_RETRIES", "5"))
        for attempt in range(max_retries + 1):
            cur = conn.cursor()
            try:
                cur.execute("BEGIN TRANSACTION")
                for task_type, args in buffer:
                    if task_type == "sensor_data":
                        self._execute_sensor_data(cur, args)
                    elif task_type == "unknown_payload":
                        self._execute_unknown_payload(cur, args)
                    elif task_type == "experiment_log":
                        self._execute_experiment_log(cur, args)
                    elif task_type == "schema_profile":
                        self._execute_schema_profile(cur, args)
                conn.commit()
                duration_ms = round((time.time() - started_at) * 1000, 3)
                with self.lock:
                    self.stats["committed"] += len(buffer)
                    self.stats["flush_count"] += 1
                    self.stats["last_flush_size"] = len(buffer)
                    self.stats["last_flush_duration_ms"] = duration_ms
                    self.stats["last_error"] = None
                return
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "locked" not in str(e).lower() or attempt >= max_retries:
                    self._record_failed_flush(buffer, e)
                    return
                time.sleep(0.05 * (attempt + 1))
            except Exception as e:
                conn.rollback()
                self._record_failed_flush(buffer, e)
                return

    def _record_failed_flush(self, buffer, error):
        with self.lock:
            self.stats["failed"] += len(buffer)
            self.stats["last_error"] = str(error)
        logger.error(f"Failed to commit DB transaction: {error}")

    def _execute_sensor_data(self, cur, args):
        data, meta = args
        cur.execute("""
            INSERT INTO sensor_data
            (sensor_id, sensor_type, value, unit, topic, mode, timestamp,
             experiment_id, seq, publish_timestamp, received_timestamp,
             measured_latency, payload_size, qos, compression, encryption, integrity, schema_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("sensor_id"),
            data.get("sensor_type"),
            float(data.get("value")) if data.get("value") is not None else 0.0,
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

    def _execute_unknown_payload(self, cur, args):
        topic, payload_text, payload_type, error_message, meta = args
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
            meta.get("received_timestamp") or meta.get("received_at"),
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

    def _execute_experiment_log(self, cur, args):
        meta, payload_type, is_unknown_schema, payload_text, runtime_mode = args
        
        latency = meta.get("measured_latency")
        latency_ms = round(float(latency) * 1000, 3) if latency is not None else None
        platform_mode = meta.get("platform_mode") or runtime_mode
        experiment_id = meta.get("experiment_id")
        
        # Build policy key
        qos = meta.get("qos")
        compression = meta.get("compression") or 'none'
        encryption = meta.get("encryption") or 'none'
        integrity = meta.get("integrity") or 'none'
        policy_key = f"qos={qos}|comp={compression}|enc={encryption}|int={integrity}"
        
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

    def _execute_schema_profile(self, cur, args):
        meta, payload_type, payload_text, data = args
        
        schema_hash = meta.get("schema_hash")
        received_at = meta.get("received_timestamp") or now_iso()
        
        # Flatten keys helper inside thread
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
            
        schema_keys = ""
        if isinstance(data, dict):
            schema_keys = json.dumps(flatten_schema_keys(data), ensure_ascii=False)
            
        key_count = len(json.loads(schema_keys)) if schema_keys else 0
        payload_size = int(meta.get("payload_size") or len(payload_text.encode("utf-8")))

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

db_manager = DBManager()
