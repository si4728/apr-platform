import argparse
import base64
import configparser
import gzip
import hashlib
import json
import os
import random
import signal
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
    "sensor_id": "temp_001",
    "sensor_type": "temperature",
    "unit": "",
    "topic": "",
    "policy_topic": "",
    "interval": 1.0,
    "experiment_id": "RASPI_RUNTIME",
    "client_id": "",
    "username": "",
    "password": "",
    "tls": False,
    "aes_key_hex": "",
}

running = True
active_policy = dict(DEFAULT_POLICY)
collecting_mode = False
seq = 0


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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

    config["sensor_id"] = _get_config_value(parser, "device", "sensor_id", config["sensor_id"])
    config["sensor_type"] = _get_config_value(parser, "device", "sensor_type", config["sensor_type"])
    config["unit"] = _get_config_value(parser, "device", "unit", config["unit"])
    config["client_id"] = _get_config_value(parser, "device", "client_id", config["client_id"])

    config["topic"] = _get_config_value(parser, "topics", "telemetry", config["topic"])
    config["policy_topic"] = _get_config_value(parser, "topics", "policy", config["policy_topic"])

    config["interval"] = _get_config_value(parser, "runtime", "interval", config["interval"])
    config["experiment_id"] = _get_config_value(parser, "runtime", "experiment_id", config["experiment_id"])

    config["aes_key_hex"] = _get_config_value(parser, "security", "apr_aes_key_hex", config["aes_key_hex"])
    if config["aes_key_hex"]:
        os.environ["APR_AES_KEY_HEX"] = config["aes_key_hex"]

    return SimpleNamespace(**config)


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


def read_sensor_value(sensor_type):
    # Replace this block with real GPIO/I2C/SPI sensor reads on Raspberry Pi.
    if sensor_type == "temperature":
        return round(24.0 + random.uniform(-1.5, 1.5), 3), "C"
    if sensor_type == "humidity":
        return round(55.0 + random.uniform(-6.0, 6.0), 3), "%"
    if sensor_type == "vibration":
        return round(2.0 + random.uniform(-0.4, 0.4), 3), "mm/s"
    return round(random.random() * 100.0, 3), "unit"


def build_payload(args, seq_num):
    value, unit = read_sensor_value(args.sensor_type)
    payload = {
        "experiment_id": args.experiment_id,
        "platform_mode": "edge_device",
        "seq": seq_num,
        "sensor_id": args.sensor_id,
        "sensor_type": args.sensor_type,
        "value": value,
        "unit": args.unit or unit,
        "topic": args.topic,
        "timestamp": now_iso(),
        "publish_timestamp": now_iso(),
        "policy": dict(active_policy),
    }
    if collecting_mode:
        payload["_collecting"] = True
        payload["payload_size"] = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        payload["measured_latency_ms"] = 0.0
    return payload


def on_policy_message(client, userdata, msg):
    global active_policy, collecting_mode
    try:
        command = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[policy] invalid JSON: {exc}")
        return

    if command.get("command") == "collect":
        collecting_mode = True
        print("[policy] collection mode enabled")
        return

    if command.get("command") in ("reset_policy", "default_policy"):
        active_policy = dict(DEFAULT_POLICY)
        collecting_mode = False
        print("[policy] reset to default policy")
        return

    active_policy = normalize_policy(command)
    collecting_mode = False
    print(f"[policy] updated: {active_policy}")


def on_connect(client, userdata, flags, rc):
    args = userdata["args"]
    print(f"[mqtt] connected rc={rc}")
    client.subscribe(args.policy_topic, qos=1)
    print(f"[mqtt] subscribed policy topic: {args.policy_topic}")


def handle_signal(signum, frame):
    global running
    running = False


def parse_args():
    parser = argparse.ArgumentParser(description="Raspberry Pi MQTT edge publisher for the APR IoT platform.")
    parser.add_argument("--config", default="client.config", help="Client config file path.")
    return parser.parse_args()


def main():
    global seq
    cli = parse_args()
    args = load_client_config(cli.config)
    if not args.topic:
        args.topic = f"iot/sensor/{args.sensor_id}"
    if not args.policy_topic:
        args.policy_topic = f"iot/sensor/policy/{args.sensor_id}"

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    client = mqtt.Client(client_id=args.client_id or f"raspi-{args.sensor_id}", userdata={"args": args})
    client.on_connect = on_connect
    client.on_message = on_policy_message
    if args.username:
        client.username_pw_set(args.username, args.password)
    if args.tls:
        client.tls_set()

    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    print(f"[edge] publishing topic: {args.topic}")
    print(f"[edge] initial policy: {active_policy}")

    try:
        while running:
            seq += 1
            payload = build_payload(args, seq)
            policy = normalize_policy(active_policy)
            qos = int(policy.get("qos", 0))

            if requires_envelope(policy):
                outgoing = encode_payload(payload, policy, args.experiment_id, seq)
            else:
                outgoing = payload

            payload_text = json.dumps(outgoing, ensure_ascii=False)
            info = client.publish(args.topic, payload_text, qos=qos)
            print(f"[publish] seq={seq} qos={qos} policy={policy} rc={getattr(info, 'rc', None)}")
            time.sleep(max(0.05, args.interval))
    finally:
        client.loop_stop()
        client.disconnect()
        print("[edge] stopped")


if __name__ == "__main__":
    main()
