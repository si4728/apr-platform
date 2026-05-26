import json
import os
import threading
import time
import uuid

import paho.mqtt.client as mqtt


host = os.getenv("TARGET_MQTT_HOST", os.getenv("SOURCE_MQTT_HOST", "218.146.225.166"))
port = int(os.getenv("TARGET_MQTT_PORT", os.getenv("SOURCE_MQTT_PORT", "1883")))
input_topic = os.getenv("TEST_INPUT_TOPIC", "iot/sensor/test/apr_gateway")
output_topic = os.getenv("TEST_OUTPUT_TOPIC", "iot/optimized/test/apr_gateway")

ready = threading.Event()
done = threading.Event()
received = []


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(output_topic, qos=0)
        ready.set()
    else:
        raise RuntimeError(f"subscriber connect failed: {reason_code}")


def on_message(client, userdata, message):
    received.append((message.topic, message.payload.decode("utf-8", errors="replace")))
    done.set()


suffix = uuid.uuid4().hex[:8]
subscriber = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"apr-client-test-sub-{suffix}")
subscriber.on_connect = on_connect
subscriber.on_message = on_message
subscriber.connect(host, port, keepalive=60)
subscriber.loop_start()

if not ready.wait(5):
    raise TimeoutError("subscriber did not become ready")

publisher = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"apr-client-test-pub-{suffix}")
publisher.connect(host, port, keepalive=60)

payload = {
    "sensor_id": "apr_gateway_client_test",
    "sensor_type": "temperature",
    "value": 25.5,
    "unit": "C",
    "timestamp": time.time(),
}

result = publisher.publish(input_topic, json.dumps(payload), qos=0)
result.wait_for_publish(timeout=5)
publisher.disconnect()

if not done.wait(10):
    raise TimeoutError(f"did not receive optimized output on {output_topic}")

subscriber.loop_stop()
subscriber.disconnect()

print(json.dumps({
    "input_topic": input_topic,
    "output_topic": received[0][0],
    "output_payload": json.loads(received[0][1]),
}, ensure_ascii=False, indent=2))
