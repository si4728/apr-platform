import json
import time
import random
import threading
import os
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from publisher.async_publisher import AsyncPublisher
from network_emulation import normalize_network_profile
from distributed_broker import connect_client_to_any_broker

CONFIG_FILE = "config.json"

sensor_state = {}
running_threads = {}
stop_flags = {}
seq_state = {}
active_policies = {}   # Dynamic in-memory policy cache (device-dependent)
async_publisher = None
collecting_mode = {}   # {sensor_id: bool} - 서버 수집 명령 수신 시 True → enriched payload 포함


def on_policy_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split('/')
        sensor_id = topic_parts[-1]
        payload = json.loads(msg.payload.decode('utf-8'))

        # 수집 명령(command=collect) 수신 시 → enriched 모드 활성화
        if payload.get("command") == "collect":
            collecting_mode[sensor_id] = True
            print(f"\n[COLLECT CMD] 센서 [{sensor_id}] 데이터 수집 모드 시작 → payload에 추가 메트릭 포함")
        elif payload.get("command") in ("reset_policy", "default_policy"):
            collecting_mode[sensor_id] = False
            active_policies.pop(sensor_id, None)
            print(f"\n[POLICY RESET] 센서 [{sensor_id}] 기본 설정 정책으로 복귀")
        else:
            # 일반 정책 명령: 기존대로 active_policies에 캐싱
            collecting_mode[sensor_id] = False  # 수집 모드 종료
            active_policies[sensor_id] = normalize_policy(payload)
            policy = active_policies[sensor_id]
            print(f"\n[POLICY CMD] 센서 [{sensor_id}] → QoS={policy.get('qos',0)}, Comp={policy.get('compression','none').upper()}, Enc={policy.get('encryption','none').upper()}")
    except Exception as e:
        print(f"Error parsing policy command: {e}")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_platform_config(config):
    platform = config.get("platform", {})
    return {
        "experiment_id": platform.get("experiment_id", "EXP_DEFAULT"),
        "mode": platform.get("mode", "hybrid"),
        "default_qos": int(platform.get("default_qos", 0)),
        "policy": platform.get("default_policy", {
            "compression": "none",
            "encryption": "none",
            "integrity": "none"
        }),
        "publisher_queue_size": int(platform.get("publisher_queue_size", 1000)),
        "publisher_retry_count": int(platform.get("publisher_retry_count", 1)),
        "network_profile": normalize_network_profile(platform.get("network_profile")),
    }


def normalize_policy(policy=None, default_qos=0):
    if not isinstance(policy, dict):
        policy = {}
    return {
        "qos": int(policy.get("qos", default_qos)),
        "compression": policy.get("compression", "none") or "none",
        "encryption": policy.get("encryption", "none") or "none",
        "integrity": policy.get("integrity", "none") or "none",
    }


def requires_envelope(policy):
    return (
        policy.get("compression", "none") != "none" or
        policy.get("encryption", "none") != "none" or
        policy.get("integrity", "none") != "none"
    )


def get_configured_policy(sensor, platform_config):
    policy = normalize_policy(platform_config.get("policy"), platform_config["default_qos"])
    if isinstance(sensor.get("policy"), dict):
        policy.update(normalize_policy(sensor.get("policy"), policy["qos"]))
    for key in ("qos", "compression", "encryption", "integrity"):
        if key in sensor:
            policy[key] = int(sensor[key]) if key == "qos" else sensor[key]
    return policy


def next_seq(sid):
    if sid not in seq_state:
        seq_state[sid] = 0
    seq_state[sid] += 1
    return seq_state[sid]


def generate_sensor_value(sensor):
    sid = sensor["id"]
    if sid not in sensor_state:
        sensor_state[sid] = float(sensor.get("start", 0))

    mode = sensor.get("mode", "random_walk")
    if mode == "random":
        s_min = float(sensor.get("min", 0))
        s_max = float(sensor.get("max", 100))
        val = random.uniform(s_min, s_max)
        sensor_state[sid] = val
        return val

    # random_walk
    def generate_random_walk(s):
        curr = sensor_state[sid]
        step = float(s.get("step", 1.0))
        s_min = float(s.get("min", 0))
        s_max = float(s.get("max", 100))
        delta = random.uniform(-step, step)
        new_val = curr + delta
        if new_val < s_min:
            new_val = s_min
        elif new_val > s_max:
            new_val = s_max
        sensor_state[sid] = new_val
        return new_val

    return generate_random_walk(sensor)


def query_apr_recommendation(payload_size, topic, default_qos=0):
    import urllib.request
    fallback = {
        "qos": default_qos,
        "compression": "none",
        "encryption": "none",
        "integrity": "none"
    }
    try:
        url = "http://127.0.0.1:5000/api/apr/recommend"
        req_data = json.dumps({
            "payload_size": payload_size,
            "network_latency_ms": 15.0,
            "queue_depth": 5,
            "topic": topic,
            "schema_type": "standard"
        }).encode("utf-8")
        
        req = urllib.request.Request(
            url, 
            data=req_data, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=1.0) as res:
            if res.status == 200:
                return json.loads(res.read().decode("utf-8"))
    except Exception as e:
        print(f"[*] APR recommendation query failed, using fallback: {e}")
    return fallback


def sensor_worker(sensor, mqtt_client, platform_config, publisher):
    sid = sensor["id"]
    topic = sensor.get("topic", f"iot/sensor/{sid}")
    policy = sensor.get("policy", "none")

    print(f"[START] sensor={sid}, topic={topic}, policy={policy}")

    while not stop_flags.get(sid, False):
        publish_timestamp = now_iso()
        telemetry_val = generate_sensor_value(sensor)
        
        # Check for dynamic MQTT-pushed policy update first (Device-dependent caching)
        dyn_policy = active_policies.get(sid)
        
        if dyn_policy:
            # Dynamic Policy Command received and cached
            qos = int(dyn_policy.get("qos", 0))
            comp = dyn_policy.get("compression", "none")
            enc = dyn_policy.get("encryption", "none")
            integ = dyn_policy.get("integrity", "none")
            
            if not requires_envelope(dyn_policy):
                # Send plain JSON telemetry with the ordered QoS
                payload = {
                    "experiment_id": platform_config["experiment_id"],
                    "platform_mode": platform_config["mode"],
                    "seq": next_seq(sid),
                    "sensor_id": sid,
                    "sensor_type": sensor["type"],
                    "value": telemetry_val,
                    "unit": sensor["unit"],
                    "topic": topic,
                    "mode": sensor.get("mode", "random_walk"),
                    "timestamp": publish_timestamp,
                    "publish_timestamp": publish_timestamp,
                    "policy": {
                        "qos": qos,
                        "compression": "none",
                        "encryption": "none",
                        "integrity": "none"
                    }
                }
                payload_text = json.dumps(payload, ensure_ascii=False)
                payload["payload_size"] = len(payload_text.encode("utf-8"))
                payload_text_with_size = json.dumps(payload, ensure_ascii=False)
                
                publisher.publish(topic, payload_text_with_size, qos=qos)
                print(f"[Dynamic Order PLAIN {sid}] QoS={qos}: {payload_text_with_size}")
            else:
                # Dynamic encryption/compression payload formatting
                from policy.codec import encode_payload
                seq = next_seq(sid)
                payload = {
                    "experiment_id": platform_config["experiment_id"],
                    "platform_mode": platform_config["mode"],
                    "seq": seq,
                    "sensor_id": sid,
                    "sensor_type": sensor["type"],
                    "value": telemetry_val,
                    "unit": sensor["unit"],
                    "topic": topic,
                    "mode": sensor.get("mode", "random_walk"),
                    "timestamp": publish_timestamp,
                    "publish_timestamp": publish_timestamp,
                }
                encode_policy = {
                    "qos": qos,
                    "compression": comp,
                    "encryption": enc,
                    "integrity": integ,
                }
                try:
                    envelope = encode_payload(
                        payload,
                        encode_policy,
                        seq=seq,
                        experiment_id=platform_config["experiment_id"],
                    )
                    payload_text = json.dumps(envelope, ensure_ascii=False)
                    publisher.publish(topic, payload_text, qos=qos)
                    print(f"[Dynamic Order APR {sid}] QoS {qos}, Comp={comp.upper()}, Enc={enc.upper()}: {payload_text[:100]}...")
                except Exception as e:
                    print(f"[!] Dynamic order encoding failed: {e}")
                    
        elif policy == "apr":
            # Static APR enabled: request ML prediction dynamically on each publish
            from policy.codec import encode_payload
            
            raw_payload = {
                "experiment_id": platform_config["experiment_id"],
                "platform_mode": platform_config["mode"],
                "seq": next_seq(sid),
                "sensor_id": sid,
                "sensor_type": sensor["type"],
                "value": telemetry_val,
                "unit": sensor["unit"],
                "topic": topic,
                "mode": sensor.get("mode", "random_walk"),
                "publish_timestamp": publish_timestamp
            }
            raw_text = json.dumps(raw_payload, ensure_ascii=False)
            payload_size = len(raw_text.encode("utf-8"))
            
            # Query recommendation
            rec = query_apr_recommendation(payload_size, topic, platform_config["default_qos"])
            
            try:
                qos = int(rec.get("qos", 0))
                envelope = encode_payload(
                    raw_payload,
                    rec,
                    seq=raw_payload["seq"],
                    experiment_id=platform_config["experiment_id"],
                )
                payload_text = json.dumps(envelope, ensure_ascii=False)
                publisher.publish(topic, payload_text, qos=qos)
                print(f"[APR {sid}] QoS {qos}, Comp={rec['compression'].upper()}, Enc={rec['encryption'].upper()}: {payload_text[:120]}...")
            except Exception as e:
                print(f"[!] APR encoding failed: {e}")
                
        else:
            # Configured default policy publishing
            configured_policy = get_configured_policy(sensor, platform_config)
            payload = {
                "experiment_id": platform_config["experiment_id"],
                "platform_mode": platform_config["mode"],
                "seq": next_seq(sid),
                "sensor_id": sid,
                "sensor_type": sensor["type"],
                "value": telemetry_val,
                "unit": sensor["unit"],
                "topic": topic,
                "mode": sensor.get("mode", "random_walk"),
                "timestamp": publish_timestamp,
                "publish_timestamp": publish_timestamp,
                "policy": configured_policy
            }

            # 수집 모드(collecting_mode) 활성화 시 정책 결정용 추가 메트릭 포함
            if collecting_mode.get(sid, False):
                import socket
                t_before = time.time()
                payload_text_tmp = json.dumps(payload, ensure_ascii=False)
                payload["payload_size"] = len(payload_text_tmp.encode("utf-8"))
                payload["measured_latency_ms"] = round((time.time() - t_before) * 1000, 3)
                payload["_collecting"] = True
                print(f"[COLLECTING {sid}] enriched payload 포함 발행")
            qos = int(configured_policy["qos"])
            if requires_envelope(configured_policy):
                from policy.codec import encode_payload
                try:
                    envelope = encode_payload(
                        payload,
                        configured_policy,
                        seq=payload["seq"],
                        experiment_id=platform_config["experiment_id"],
                    )
                    payload_text = json.dumps(envelope, ensure_ascii=False)
                    publisher.publish(topic, payload_text, qos=qos)
                    print(f"[Configured APR {sid}] QoS {qos}, Comp={configured_policy['compression'].upper()}, Enc={configured_policy['encryption'].upper()}: {payload_text[:120]}...")
                except Exception as e:
                    print(f"[!] Configured policy encoding failed: {e}")
            else:
                payload_text = json.dumps(payload, ensure_ascii=False)
                payload["payload_size"] = len(payload_text.encode("utf-8"))
                payload_text_with_size = json.dumps(payload, ensure_ascii=False)
                publisher.publish(topic, payload_text_with_size, qos=qos)
                print(f"[Configured Plain {sid}] {payload_text_with_size}")

        time.sleep(sensor.get("interval", 1))

    print(f"[STOP] sensor={sid}")


def stop_all_sensors():
    for sid in list(stop_flags.keys()):
        stop_flags[sid] = True

    time.sleep(1)

    running_threads.clear()
    stop_flags.clear()


def start_sensors(config, mqtt_client, publisher):
    platform_config = get_platform_config(config)

    for sensor in config.get("sensors", []):
        sid = sensor["id"]
        stop_flags[sid] = False
        
        # Subscribe to device-specific policy command topic
        policy_topic = f"iot/sensor/policy/{sid}"
        mqtt_client.subscribe(policy_topic)
        print(f"Subscribed to dynamic policy control topic: {policy_topic}")

        t = threading.Thread(
            target=sensor_worker,
            args=(sensor, mqtt_client, platform_config, publisher),
            daemon=True
        )

        running_threads[sid] = t
        t.start()


def main():
    global async_publisher
    config = load_config()

    client = mqtt.Client()
    client.on_message = on_policy_message
    active_broker = connect_client_to_any_broker(client, config.get("mqtt", {}), 60)
    print(f"MQTT active broker: {active_broker['name']} {active_broker['host']}:{active_broker['port']}")
    client.loop_start()

    platform_config = get_platform_config(config)
    async_publisher = AsyncPublisher(
        client,
        max_queue_size=platform_config["publisher_queue_size"],
        retry_count=platform_config["publisher_retry_count"],
        network_profile=platform_config["network_profile"],
    )
    async_publisher.start()

    last_modified = 0

    try:
        while True:
            current_modified = os.path.getmtime(CONFIG_FILE)

            if current_modified != last_modified:
                print("\n[CONFIG CHANGED] reload config.json")

                stop_all_sensors()

                config = load_config()
                start_sensors(config, client, async_publisher)

                last_modified = current_modified

            time.sleep(2)
    except KeyboardInterrupt:
        print("Sensor simulator stopped.")
    finally:
        stop_all_sensors()
        if async_publisher:
            async_publisher.stop(drain=True)
            print(f"Async publisher stats: {async_publisher.get_stats()}")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
