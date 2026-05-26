import json
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gateway.config import GatewayConfig
from gateway.decision_engine import APREngine
from gateway.metrics import MetricsStore
from gateway.mqtt_proxy import MqttProxy


config = GatewayConfig.from_env()
metrics = MetricsStore()
proxy = MqttProxy(config, APREngine(config.model_dir), metrics)

input_topic = "iot/sensor/test/apr_gateway"
output_topic = "iot/optimized/test/apr_gateway"
received = []
ready = threading.Event()
done = threading.Event()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(output_topic, qos=0)
        ready.set()
    else:
        raise RuntimeError(f"subscriber connect failed: {reason_code}")


def on_message(client, userdata, message):
    received.append((message.topic, message.payload.decode("utf-8", errors="replace")))
    done.set()


proxy.start()
time.sleep(3)

subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="apr-e2e-subscriber")
subscriber.on_connect = on_connect
subscriber.on_message = on_message
subscriber.connect(config.target_mqtt_host, config.target_mqtt_port, keepalive=60)
subscriber.loop_start()

if not ready.wait(5):
    raise TimeoutError("subscriber did not become ready")

publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="apr-e2e-publisher")
publisher.connect(config.source_mqtt_host, config.source_mqtt_port, keepalive=60)

payload = {
    "sensor_id": "apr_gateway_test",
    "sensor_type": "temperature",
    "value": 25.5,
    "unit": "C",
    "timestamp": time.time(),
}
result = publisher.publish(input_topic, json.dumps(payload), qos=0)
result.wait_for_publish(timeout=5)
publisher.disconnect()

if not done.wait(10):
    raise TimeoutError(f"did not receive optimized output on {output_topic}; metrics={metrics.snapshot()}")

subscriber.loop_stop()
subscriber.disconnect()

print(json.dumps({
    "input_topic": input_topic,
    "output_topic": received[0][0],
    "output_payload": json.loads(received[0][1]),
    "metrics": metrics.snapshot(),
}, ensure_ascii=False, indent=2))
