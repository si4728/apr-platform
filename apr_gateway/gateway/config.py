import os
from dataclasses import dataclass
from pathlib import Path


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class GatewayConfig:
    source_mqtt_host: str
    source_mqtt_port: int
    target_mqtt_host: str
    target_mqtt_port: int
    subscribe_topic: str
    publish_prefix: str
    apr_mode: str
    http_port: int
    default_qos: int
    default_compression: str
    default_encryption: str
    default_integrity: str
    model_dir: str

    @classmethod
    def from_env(cls):
        load_env_file()
        return cls(
            source_mqtt_host=os.getenv("SOURCE_MQTT_HOST", "localhost"),
            source_mqtt_port=_get_int("SOURCE_MQTT_PORT", 1883),
            target_mqtt_host=os.getenv("TARGET_MQTT_HOST", "localhost"),
            target_mqtt_port=_get_int("TARGET_MQTT_PORT", 1883),
            subscribe_topic=os.getenv("SUBSCRIBE_TOPIC", "iot/raw/#"),
            publish_prefix=os.getenv("PUBLISH_PREFIX", "iot/optimized"),
            apr_mode=os.getenv("APR_MODE", "proxy").lower(),
            http_port=_get_int("HTTP_PORT", 8080),
            default_qos=_get_int("DEFAULT_QOS", 0),
            default_compression=os.getenv("DEFAULT_COMPRESSION", "none"),
            default_encryption=os.getenv("DEFAULT_ENCRYPTION", "none"),
            default_integrity=os.getenv("DEFAULT_INTEGRITY", "none"),
            model_dir=os.getenv("MODEL_DIR", "models"),
        )


def load_env_file(path: str = ".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
