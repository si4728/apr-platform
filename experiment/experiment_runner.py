import os
import time
import csv
import json
import uuid
import sys
import threading
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Add project root to sys.path so we can import from policy
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from policy.codec import encode_payload
except ImportError:
    encode_payload = None
try:
    from network_emulation import apply_network_profile, normalize_network_profile
except ImportError:
    apply_network_profile = None
    normalize_network_profile = None
try:
    from distributed_broker import connect_client_to_any_broker, get_primary_broker
except ImportError:
    connect_client_to_any_broker = None
    get_primary_broker = None

class ExperimentRunner:
    def __init__(self, name="base_experiment"):
        self.name = name
        self.experiment_id = f"EXP_{name}_{int(time.time())}"
        self.started_at = None
        self.finished_at = None
        self.status = "initialized"
        self.error = None
        self.publish_attempted = 0
        self.publish_succeeded = 0
        self.publish_failed = 0
        self.emulated_dropped = 0
        self.emulated_delay_ms_total = 0.0
        self._metrics_lock = threading.Lock()
        self.network_profile = {
            "enabled": False,
            "base_delay_ms": 0.0,
            "jitter_ms": 0.0,
            "drop_rate": 0.0,
        }
        
        # Load broker config
        self.broker = "127.0.0.1"
        self.port = 1883
        self.mqtt_config = {}
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                if "mqtt" in config:
                    self.mqtt_config = config["mqtt"]
                    if get_primary_broker:
                        primary = get_primary_broker(self.mqtt_config)
                        self.broker = primary["host"]
                        self.port = primary["port"]
                    else:
                        self.broker = config["mqtt"].get("broker", "127.0.0.1")
                        self.port = config["mqtt"].get("port", 1883)
                if normalize_network_profile:
                    platform = config.get("platform", {})
                    self.network_profile = normalize_network_profile(platform.get("network_profile"))
        except Exception:
            pass
            
        # Hardcode fallback if localhost is not the actual broker but we know it
        if self.broker == "127.0.0.1":
            self.broker = "218.146.225.166"
            
        # Suppress deprecation warning for Callback API Version 1 if paho-mqtt version >= 2.0
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except AttributeError:
            self.client = mqtt.Client()
            
        self.results_dir = "experiment_results"
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
            
    def connect(self):
        self.status = "connecting"
        if connect_client_to_any_broker:
            active_broker = connect_client_to_any_broker(self.client, self.mqtt_config, 60)
            self.broker = active_broker["host"]
            self.port = active_broker["port"]
        else:
            self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()
        self.status = "running"
        
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        
    def publish_message(self, topic, payload_dict, qos=0, policy=None):
        # Inject experiment ID
        payload_dict["experiment_id"] = self.experiment_id
        if "publish_timestamp" not in payload_dict:
            payload_dict["publish_timestamp"] = datetime.now(timezone.utc).isoformat()
            
        if policy and encode_payload:
            # We want to dynamically encode/compress/encrypt/hash the packet
            seq = payload_dict.get("seq", 0)
            packed = encode_payload(payload_dict, policy, seq=seq, experiment_id=self.experiment_id)
            payload_str = json.dumps(packed)
        else:
            payload_str = json.dumps(payload_dict)

        with self._metrics_lock:
            self.publish_attempted += 1

        if apply_network_profile:
            emulation = apply_network_profile(self.network_profile)
            with self._metrics_lock:
                self.emulated_delay_ms_total += emulation["delay_ms"]
                if emulation["dropped"]:
                    self.emulated_dropped += 1
                    return None

        try:
            info = self.client.publish(topic, payload_str, qos=qos)
            # Paho returns rc=0 for successful enqueue to the client network loop.
            if getattr(info, "rc", 0) == mqtt.MQTT_ERR_SUCCESS:
                with self._metrics_lock:
                    self.publish_succeeded += 1
            else:
                with self._metrics_lock:
                    self.publish_failed += 1
            return info
        except Exception:
            with self._metrics_lock:
                self.publish_failed += 1
            raise
        
    def run(self):
        """Override this method to implement specific experiment logic."""
        raise NotImplementedError("Subclasses must implement run()")

    def execute(self):
        self.started_at = datetime.now(timezone.utc)
        self.status = "running"
        try:
            self.run()
            if self.status not in ("failed", "completed"):
                self.status = "completed"
        except Exception as e:
            self.status = "failed"
            self.error = str(e)
            raise
        finally:
            self.finished_at = datetime.now(timezone.utc)
            self.export_summary()

    def get_summary(self):
        duration_s = None
        if self.started_at and self.finished_at:
            duration_s = round((self.finished_at - self.started_at).total_seconds(), 3)
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "broker": self.broker,
            "port": self.port,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_s": duration_s,
            "publish_attempted": self.publish_attempted,
            "publish_succeeded": self.publish_succeeded,
            "publish_failed": self.publish_failed,
            "emulated_dropped": self.emulated_dropped,
            "emulated_delay_ms_total": round(self.emulated_delay_ms_total, 3),
            "network_profile": dict(self.network_profile),
        }

    def export_summary(self):
        path = os.path.join(self.results_dir, f"{self.experiment_id}.summary.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_summary(), f, indent=2, ensure_ascii=False)
        print(f"Summary exported to {path}")
        return path
        
    def export_csv(self, filename, headers, rows):
        path = os.path.join(self.results_dir, filename)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        print(f"Results exported to {path}")
