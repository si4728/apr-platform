import argparse
import base64
import configparser
import gzip
import hashlib
import json
import os
import signal
import shutil
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import paho.mqtt.client as mqtt

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None


DEFAULT_POLICY = {
    "qos": 0,
    "compression": "none",
    "encryption": "none",
    "integrity": "none",
}

DEFAULT_CONFIG = {
    "broker": "218.146.225.166",
    "port": 1883,
    "username": "",
    "password": "",
    "tls": False,
    "device_id": "raspi_001",
    "device_name": "raspberry-pi-edge-001",
    "location": "",
    "client_id": "",
    "topic_prefix": "iot/sensor/system",
    "policy_topic": "",
    "interval": 5.0,
    "experiment_id": "RASPI_SYSTEM_RUNTIME",
    "metrics": "cpu_percent,memory_percent,cpu_temp_c,disk_percent,load_1m",
    "enabled": True,
    "aes_key_hex": "",
}

METRIC_DEFS = {
    "cpu_percent": ("cpu", "%"),
    "memory_percent": ("memory", "%"),
    "memory_used_mb": ("memory", "MB"),
    "memory_total_mb": ("memory", "MB"),
    "cpu_temp_c": ("temperature", "C"),
    "disk_percent": ("disk", "%"),
    "disk_used_gb": ("disk", "GB"),
    "disk_total_gb": ("disk", "GB"),
    "load_1m": ("load", "load"),
}

running = True
seq = 0
active_policy = dict(DEFAULT_POLICY)
collecting_mode = False
runtime_options = {
    "enabled": True,
    "interval": 5.0,
    "metrics": list(METRIC_DEFS.keys()),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_config_value(parser, section, key, default):
    if not parser.has_option(section, key):
        return default
    if isinstance(default, bool):
        return parser.getboolean(section, key)
    if isinstance(default, int):
        return parser.getint(section, key)
    if isinstance(default, float):
        return parser.getfloat(section, key)
    return parser.get(section, key).strip()


def normalize_metric_list(value):
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        items = []
    selected = [item for item in items if item in METRIC_DEFS]
    return selected or list(METRIC_DEFS.keys())


def load_client_config(config_path):
    config = dict(DEFAULT_CONFIG)
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Client config not found: {path}")

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    config["broker"] = _get_config_value(parser, "mqtt", "broker", config["broker"])
    config["port"] = _get_config_value(parser, "mqtt", "port", config["port"])
    config["username"] = _get_config_value(parser, "mqtt", "username", config["username"])
    config["password"] = _get_config_value(parser, "mqtt", "password", config["password"])
    config["tls"] = _get_config_value(parser, "mqtt", "tls", config["tls"])

    config["device_id"] = _get_config_value(parser, "device", "device_id", config["device_id"])
    config["device_name"] = _get_config_value(parser, "device", "device_name", config["device_name"])
    config["location"] = _get_config_value(parser, "device", "location", config["location"])
    config["client_id"] = _get_config_value(parser, "device", "client_id", config["client_id"])
    if not config["client_id"]:
        config["client_id"] = f"raspi-system-{config['device_id']}"

    config["topic_prefix"] = _get_config_value(parser, "topics", "topic_prefix", config["topic_prefix"])
    config["policy_topic"] = _get_config_value(parser, "topics", "policy", config["policy_topic"])
    if not config["policy_topic"]:
        config["policy_topic"] = f"iot/sensor/policy/{config['device_id']}_system"

    config["enabled"] = _get_config_value(parser, "runtime", "enabled", config["enabled"])
    config["interval"] = _get_config_value(parser, "runtime", "interval", config["interval"])
    config["experiment_id"] = _get_config_value(parser, "runtime", "experiment_id", config["experiment_id"])
    config["metrics"] = _get_config_value(parser, "runtime", "metrics", config["metrics"])

    config["aes_key_hex"] = _get_config_value(parser, "security", "apr_aes_key_hex", config["aes_key_hex"])
    if config["aes_key_hex"]:
        os.environ["APR_AES_KEY_HEX"] = config["aes_key_hex"]

    return SimpleNamespace(**config)


def normalize_policy(policy):
    if not isinstance(policy, dict):
        policy = {}
    return {
        "qos": int(policy.get("qos", DEFAULT_POLICY["qos"]) or 0),
        "compression": policy.get("compression", "none") or "none",
        "encryption": policy.get("encryption", "none") or "none",
        "integrity": policy.get("integrity", "none") or "none",
    }


def requires_envelope(policy):
    return (
        policy.get("compression", "none") != "none"
        or policy.get("encryption", "none") != "none"
        or policy.get("integrity", "none") != "none"
    )


def aes_key():
    key_hex = os.getenv("APR_AES_KEY_HEX")
    if key_hex:
        return bytes.fromhex(key_hex)
    return b"\x01" * 16


def compress_data(method, data_bytes):
    if method == "zlib":
        return zlib.compress(data_bytes)
    if method == "gzip":
        return gzip.compress(data_bytes)
    return data_bytes


def encrypt_data(method, data_bytes):
    if method != "AES-GCM":
        return data_bytes
    if AESGCM is None:
        raise RuntimeError("AES-GCM requested but cryptography is not installed.")
    nonce = os.urandom(12)
    encrypted = AESGCM(aes_key()).encrypt(nonce, data_bytes, None)
    return nonce + encrypted


def encode_payload(data, policy, experiment_id, seq_num):
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    compressed = compress_data(policy.get("compression", "none"), raw)
    encrypted = encrypt_data(policy.get("encryption", "none"), compressed)

    integrity = policy.get("integrity", "none")
    digest = hashlib.sha256(encrypted).hexdigest() if integrity == "sha256" else None

    return {
        "metadata": {
            "publish_timestamp": now_iso(),
            "experiment_id": experiment_id,
            "seq": seq_num,
            "qos": int(policy.get("qos", 0)),
            "compression": policy.get("compression", "none"),
            "encryption": policy.get("encryption", "none"),
            "integrity": integrity,
            "hash": digest,
        },
        "data": base64.b64encode(encrypted).decode("utf-8"),
    }


def read_proc_stat():
    with open("/proc/stat", "r", encoding="utf-8") as f:
        parts = f.readline().split()[1:]
    values = [int(part) for part in parts]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values)
    return idle, total


def cpu_percent(prev_stat):
    try:
        current = read_proc_stat()
    except OSError:
        return None, prev_stat
    if not prev_stat:
        return 0.0, current
    prev_idle, prev_total = prev_stat
    idle, total = current
    total_delta = total - prev_total
    idle_delta = idle - prev_idle
    if total_delta <= 0:
        return 0.0, current
    return round((1.0 - idle_delta / total_delta) * 100.0, 2), current


def read_memory_metrics():
    values = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, raw_value = line.split(":", 1)
                values[key] = int(raw_value.strip().split()[0])
    except OSError:
        return {}

    total_kb = values.get("MemTotal", 0)
    available_kb = values.get("MemAvailable", 0)
    used_kb = max(0, total_kb - available_kb)
    if total_kb <= 0:
        return {}

    return {
        "memory_percent": round(used_kb / total_kb * 100.0, 2),
        "memory_used_mb": round(used_kb / 1024.0, 2),
        "memory_total_mb": round(total_kb / 1024.0, 2),
    }


def read_cpu_temp_c():
    temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        if temp_path.exists():
            return round(int(temp_path.read_text(encoding="utf-8").strip()) / 1000.0, 2)
    except (OSError, ValueError):
        return None
    return None


def read_disk_metrics():
    usage = shutil.disk_usage("/")
    total = usage.total
    used = usage.used
    if total <= 0:
        return {}
    return {
        "disk_percent": round(used / total * 100.0, 2),
        "disk_used_gb": round(used / (1024 ** 3), 2),
        "disk_total_gb": round(total / (1024 ** 3), 2),
    }


def read_load_1m():
    try:
        return round(os.getloadavg()[0], 3)
    except (AttributeError, OSError):
        return None


def collect_system_metrics(prev_stat):
    cpu_value, next_stat = cpu_percent(prev_stat)
    metrics = {}
    if cpu_value is not None:
        metrics["cpu_percent"] = cpu_value
    metrics.update(read_memory_metrics())
    temp = read_cpu_temp_c()
    if temp is not None:
        metrics["cpu_temp_c"] = temp
    metrics.update(read_disk_metrics())
    load = read_load_1m()
    if load is not None:
        metrics["load_1m"] = load
    return metrics, next_stat


def build_system_payload(args, metrics, seq_num):
    base_sensor_id = f"{args.device_id}_system"
    topic = f"{args.topic_prefix}/{base_sensor_id}"
    metric_units = {
        name: METRIC_DEFS[name][1]
        for name in metrics
        if name in METRIC_DEFS
    }
    payload = {
        "experiment_id": args.experiment_id,
        "platform_mode": "edge_device",
        "seq": seq_num,
        "device_id": args.device_id,
        "device_name": args.device_name,
        "location": args.location,
        "sensor_id": base_sensor_id,
        "sensor_type": "system_metrics",
        "payload_type": "system_metrics",
        "metrics": metrics,
        "metric_units": metric_units,
        "topic": topic,
        "timestamp": now_iso(),
        "publish_timestamp": now_iso(),
        "policy": dict(active_policy),
        "device_options": dict(runtime_options),
    }
    if collecting_mode:
        payload["_collecting"] = True
        payload["payload_size"] = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        payload["measured_latency_ms"] = 0.0
    return topic, payload


def apply_runtime_options(command):
    if "enabled" in command:
        runtime_options["enabled"] = bool(command["enabled"])
    if "interval" in command:
        runtime_options["interval"] = max(1.0, float(command["interval"]))
    if "metrics" in command:
        runtime_options["metrics"] = normalize_metric_list(command["metrics"])


def on_policy_message(client, userdata, msg):
    global active_policy, collecting_mode
    try:
        command = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[policy] invalid JSON: {exc}")
        return

    command_name = command.get("command")
    if command_name == "collect":
        collecting_mode = True
        print("[policy] collection mode enabled")
        return

    if command_name in ("reset_policy", "default_policy"):
        active_policy = dict(DEFAULT_POLICY)
        collecting_mode = False
        print("[policy] reset to default policy")
        return

    if command_name in ("set_options", "update_options"):
        apply_runtime_options(command)
        print(f"[control] options updated: {runtime_options}")
        return

    if command_name in ("pause", "disable"):
        runtime_options["enabled"] = False
        print("[control] publishing disabled")
        return

    if command_name in ("resume", "enable"):
        runtime_options["enabled"] = True
        print("[control] publishing enabled")
        return

    if any(key in command for key in ("qos", "compression", "encryption", "integrity")):
        active_policy = normalize_policy(command)
        collecting_mode = False
        print(f"[policy] updated: {active_policy}")
        return

    apply_runtime_options(command)
    print(f"[control] options updated: {runtime_options}")


def on_connect(client, userdata, flags, rc):
    args = userdata["args"]
    print(f"[mqtt] connected rc={rc}")
    topics = [
        (args.policy_topic, 1),
        (f"{args.policy_topic}/system", 1),
        (f"iot/sensor/policy/{args.device_id}_system", 1),
    ]
    client.subscribe(topics)
    for topic, _qos in topics:
        print(f"[mqtt] subscribed control topic: {topic}")


def handle_signal(signum, frame):
    global running
    running = False


def parse_args():
    parser = argparse.ArgumentParser(description="Raspberry Pi system metrics publisher for the APR IoT platform.")
    parser.add_argument("--config", default="system_metrics.config", help="System metrics config file path.")
    return parser.parse_args()


def publish_payload(client, args, topic, payload, seq_num):
    policy = normalize_policy(active_policy)
    qos = int(policy.get("qos", 0))
    outgoing = encode_payload(payload, policy, args.experiment_id, seq_num) if requires_envelope(policy) else payload
    payload_text = json.dumps(outgoing, ensure_ascii=False)
    info = client.publish(topic, payload_text, qos=qos)
    print(f"[publish] topic={topic} seq={seq_num} qos={qos} policy={policy} rc={getattr(info, 'rc', None)}")


def main():
    global seq, runtime_options
    cli = parse_args()
    args = load_client_config(cli.config)

    runtime_options = {
        "enabled": bool(args.enabled),
        "interval": max(1.0, float(args.interval)),
        "metrics": normalize_metric_list(args.metrics),
    }

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    client = mqtt.Client(client_id=args.client_id, userdata={"args": args})
    client.on_connect = on_connect
    client.on_message = on_policy_message
    if args.username:
        client.username_pw_set(args.username, args.password)
    if args.tls:
        client.tls_set()

    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    print(f"[system] device: {args.device_id} ({args.device_name})")
    print(f"[system] topic prefix: {args.topic_prefix}/{args.device_id}_system")
    print(f"[system] policy topic: {args.policy_topic}, {args.policy_topic}/system")
    print(f"[system] initial options: {runtime_options}")
    print(f"[system] initial policy: {active_policy}")

    prev_stat = None
    try:
        while running:
            if not runtime_options.get("enabled", True):
                time.sleep(max(1.0, float(runtime_options.get("interval", 5.0))))
                continue

            metrics, prev_stat = collect_system_metrics(prev_stat)
            selected_metrics = {
                name: metrics[name]
                for name in runtime_options.get("metrics", [])
                if name in metrics
            }

            seq += 1
            topic, payload = build_system_payload(args, selected_metrics, seq)
            publish_payload(client, args, topic, payload, seq)

            time.sleep(max(1.0, float(runtime_options.get("interval", 5.0))))
    finally:
        client.loop_stop()
        client.disconnect()
        print("[system] stopped")


if __name__ == "__main__":
    main()
