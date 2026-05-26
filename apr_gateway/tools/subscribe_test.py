import os

import paho.mqtt.client as mqtt


host = os.getenv("TARGET_MQTT_HOST", "localhost")
port = int(os.getenv("TARGET_MQTT_PORT", "1883"))
topic = os.getenv("TEST_SUBSCRIBE_TOPIC", "iot/optimized/#")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"connected; subscribing to {topic}")
        client.subscribe(topic, qos=0)
    else:
        print(f"connect failed: {reason_code}")


def on_message(client, userdata, message):
    print(f"{message.topic}: {message.payload.decode('utf-8', errors='replace')}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="apr-test-subscriber")
client.on_connect = on_connect
client.on_message = on_message
client.connect(host, port, keepalive=60)
client.loop_forever()
