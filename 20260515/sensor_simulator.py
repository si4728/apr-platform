import json
import time
import random
import threading
import os
from datetime import datetime
import paho.mqtt.client as mqtt

CONFIG_FILE = "config.json"

sensor_state = {}
running_threads = {}
stop_flags = {}


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_random(sensor):
    return round(random.uniform(sensor["min"], sensor["max"]), 2)


def generate_random_walk(sensor):
    sid = sensor["id"]

    if sid not in sensor_state:
        sensor_state[sid] = sensor.get("start", sensor["min"])

    current = sensor_state[sid]
    step = sensor.get("step", 1)

    value = current + random.uniform(-step, step)
    value = max(sensor["min"], min(sensor["max"], value))

    sensor_state[sid] = value

    return round(value, 2)


def generate_sensor_value(sensor):
    mode = sensor.get("mode", "random_walk")

    if mode == "random":
        return generate_random(sensor)

    return generate_random_walk(sensor)


def sensor_worker(sensor, mqtt_client):
    sid = sensor["id"]
    topic = sensor.get("topic", f"iot/sensor/{sid}")

    print(f"[START] sensor={sid}, topic={topic}")

    while not stop_flags.get(sid, False):
        value = generate_sensor_value(sensor)

        payload = {
            "sensor_id": sensor["id"],
            "sensor_type": sensor["type"],
            "value": value,
            "unit": sensor["unit"],
            "topic": topic,
            "mode": sensor.get("mode", "random_walk"),
            "timestamp": datetime.now().isoformat()
        }

        mqtt_client.publish(topic, json.dumps(payload))
        print("Published:", payload)

        time.sleep(sensor.get("interval", 1))

    print(f"[STOP] sensor={sid}")


def stop_all_sensors():
    for sid in list(stop_flags.keys()):
        stop_flags[sid] = True

    time.sleep(1)

    running_threads.clear()
    stop_flags.clear()


def start_sensors(config, mqtt_client):
    for sensor in config.get("sensors", []):
        sid = sensor["id"]
        stop_flags[sid] = False

        t = threading.Thread(
            target=sensor_worker,
            args=(sensor, mqtt_client),
            daemon=True
        )

        running_threads[sid] = t
        t.start()


def main():
    config = load_config()

    broker = config["mqtt"]["broker"]
    port = config["mqtt"]["port"]

    client = mqtt.Client()
    client.connect(broker, port, 60)
    client.loop_start()

    last_modified = 0

    while True:
        current_modified = os.path.getmtime(CONFIG_FILE)

        if current_modified != last_modified:
            print("\n[CONFIG CHANGED] reload config.json")

            stop_all_sensors()

            config = load_config()
            start_sensors(config, client)

            last_modified = current_modified

        time.sleep(2)


if __name__ == "__main__":
    main()