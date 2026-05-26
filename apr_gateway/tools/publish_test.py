import json
import os
import time

import paho.mqtt.client as mqtt


host = os.getenv("SOURCE_MQTT_HOST", "localhost")
port = int(os.getenv("SOURCE_MQTT_PORT", "1883"))
topic = os.getenv("TEST_PUBLISH_TOPIC", "iot/raw/temperature/temp_001")

payload = {
    "sensor_id": "temp_001",
    "sensor_type": "temperature",
    "value": 24.7,
    "unit": "C",
    "timestamp": time.time(),
}

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="apr-test-publisher")
client.connect(host, port, keepalive=60)
result = client.publish(topic, json.dumps(payload), qos=0)
result.wait_for_publish(timeout=5)
client.disconnect()

print(f"published {topic}: {payload}")
