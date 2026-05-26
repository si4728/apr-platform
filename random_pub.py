# random_pub.py
# MQTT random JSON publisher for undefined schema payload testing
# usage:
#   python random_pub.py
#   python random_pub.py test
#   python random_pub.py plc01 2

import json
import time
import random
import sys
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

CONFIG_FILE = "config.json"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


config = load_config()

BROKER = config["mqtt"]["broker"]
PORT = config["mqtt"]["port"]
TOPIC_PREFIX = config["mqtt"]["topic_prefix"]
platform = config.get("platform", {})
default_policy = platform.get("default_policy", {})
EXPERIMENT_ID = platform.get("experiment_id", "EXP_DEFAULT")
PLATFORM_MODE = platform.get("mode", "hybrid")
DEFAULT_QOS = int(platform.get("default_qos", 0))

# argv[1] = topic name, argv[2] = interval
topic_name = "test"
publish_interval = 10

if len(sys.argv) >= 2:
    topic_name = sys.argv[1]

if len(sys.argv) >= 3:
    try:
        publish_interval = float(sys.argv[2])
    except ValueError:
        print("invalid interval value")
        sys.exit(1)

TOPIC = f"{TOPIC_PREFIX}/{topic_name}"

active_policy = None

def on_policy_message(client, userdata, msg):
    global active_policy
    try:
        active_policy = json.loads(msg.payload.decode('utf-8'))
        print(f"\n[POLICY CMD RECEIVED] -> QoS={active_policy.get('qos', 0)}, Comp={active_policy.get('compression', 'none').upper()}, Enc={active_policy.get('encryption', 'none').upper()}")
    except Exception as e:
        print(f"Error parsing policy message: {e}")

client = mqtt.Client()
client.on_message = on_policy_message
client.connect(BROKER, PORT, 60)
client.loop_start()

sensor_id = topic_name.split('/')[-1]
POLICY_TOPIC = f"iot/sensor/policy/{sensor_id}"
client.subscribe(POLICY_TOPIC)
print(f"Subscribed to dynamic policy control topic: {POLICY_TOPIC}")

seq = 0


def generate_random_body():
    payload_types = [
        lambda: {
            "device": f"dev_{random.randint(1,5)}",
            "temperature": round(random.uniform(20, 40), 2),
            "humidity": round(random.uniform(30, 90), 2),
            "timestamp": now_iso()
        },
        lambda: {
            "plc_id": f"plc_{random.randint(100,999)}",
            "motor_rpm": random.randint(500, 3000),
            "status": random.choice(["RUN", "STOP", "IDLE"]),
            "load": round(random.uniform(0, 100), 2),
            "time": now_iso()
        },
        lambda: {
            "camera": f"cam_{random.randint(1,10)}",
            "detected": random.choice(["person", "forklift", "helmet"]),
            "confidence": round(random.uniform(0.5, 0.99), 3),
            "event_time": now_iso()
        },
        lambda: {
            "node": f"edge_{random.randint(1,20)}",
            "cpu": round(random.uniform(5, 95), 1),
            "memory": round(random.uniform(10, 90), 1),
            "disk": round(random.uniform(20, 99), 1),
            "created_at": now_iso()
        }
    ]
    return random.choice(payload_types)()


def query_apr_recommendation(payload_size, topic):
    import urllib.request
    fallback = {
        "qos": DEFAULT_QOS,
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


def generate_random_payload(sensor_policy="none"):
    global seq
    seq += 1
    publish_timestamp = now_iso()
    
    # 1. Generate core telemetry data
    telemetry_data = generate_random_body()
    
    # 2. Check for dynamic MQTT-pushed policy first
    if active_policy is not None:
        qos = int(active_policy.get("qos", 0))
        comp = active_policy.get("compression", "none")
        enc = active_policy.get("encryption", "none")
        integ = active_policy.get("integrity", "none")
        
        if comp == "none" and enc == "none":
            # Send plain JSON with dynamic QoS
            payload = {
                "experiment_id": EXPERIMENT_ID,
                "platform_mode": PLATFORM_MODE,
                "seq": seq,
                "topic": TOPIC,
                "publish_timestamp": publish_timestamp,
                "policy": {
                    "qos": qos,
                    "compression": "none",
                    "encryption": "none",
                    "integrity": "none"
                },
                "data": telemetry_data
            }
            payload_text = json.dumps(payload, ensure_ascii=False)
            payload["payload_size"] = len(payload_text.encode("utf-8"))
            payload_text_with_size = json.dumps(payload, ensure_ascii=False)
            
            print(f"[Dynamic Order PLAIN] QoS={qos}")
            return payload_text_with_size, qos
        else:
            # Dynamic encrypt/compress formatting
            from policy.codec import encode_payload
            payload = {
                "experiment_id": EXPERIMENT_ID,
                "platform_mode": PLATFORM_MODE,
                "seq": seq,
                "topic": TOPIC,
                "publish_timestamp": publish_timestamp,
                "data": telemetry_data
            }
            encode_policy = {
                "qos": qos,
                "compression": comp,
                "encryption": enc,
                "integrity": integ,
            }
            try:
                envelope = encode_payload(payload, encode_policy, seq=seq, experiment_id=EXPERIMENT_ID)
                envelope_text = json.dumps(envelope, ensure_ascii=False)
                print(f"[Dynamic Order APR] QoS {qos}, Comp={comp.upper()}, Enc={enc.upper()}")
                return envelope_text, qos
            except Exception as e:
                print(f"[!] Dynamic order encoding failed: {e}")
                
    # 3. Fall back to static sensor policy
    if sensor_policy == "apr":
        from policy.codec import encode_payload
        
        # Calculate raw telemetry size
        raw_payload = {
            "experiment_id": EXPERIMENT_ID,
            "platform_mode": PLATFORM_MODE,
            "seq": seq,
            "topic": TOPIC,
            "publish_timestamp": publish_timestamp,
            "data": telemetry_data
        }
        raw_text = json.dumps(raw_payload, ensure_ascii=False)
        payload_size = len(raw_text.encode("utf-8"))
        
        # Query recommendation
        rec = query_apr_recommendation(payload_size, TOPIC)
        
        try:
            envelope = encode_payload(raw_payload, rec, seq=seq, experiment_id=EXPERIMENT_ID)
            envelope_text = json.dumps(envelope, ensure_ascii=False)
            print(f"[*] APR Dynamic Policy applied: QoS {rec['qos']}, Comp={rec['compression'].upper()}, Enc={rec['encryption'].upper()}, Hash={rec['integrity'].upper()}")
            return envelope_text, rec.get("qos", 0)
        except Exception as e:
            print(f"[!] Failed to encode APR payload: {e}")
            
    # Default 'none' plain JSON publishing
    payload = {
        "experiment_id": EXPERIMENT_ID,
        "platform_mode": PLATFORM_MODE,
        "seq": seq,
        "topic": TOPIC,
        "publish_timestamp": publish_timestamp,
        "policy": {
            "qos": DEFAULT_QOS,
            "compression": "none",
            "encryption": "none",
            "integrity": "none",
        },
        "data": telemetry_data
    }
    payload_text = json.dumps(payload, ensure_ascii=False)
    payload["payload_size"] = len(payload_text.encode("utf-8"))
    payload_text_with_size = json.dumps(payload, ensure_ascii=False)
    
    print("[*] Normal Policy applied: 'none' (plain JSON)")
    return payload_text_with_size, DEFAULT_QOS


print("=" * 60)
print("MQTT Random JSON Publisher")
print(f"Broker   : {BROKER}:{PORT}")
print(f"Topic    : {TOPIC}")
print(f"Interval : {publish_interval} sec")
print(f"QoS      : {DEFAULT_QOS}")
print("=" * 60)

try:
    while True:
        # Reload config to get latest policy edits
        try:
            config = load_config()
        except Exception:
            pass
            
        # Match topic to get configured sensor policy
        sensor_policy = "none"
        for s in config.get("sensors", []):
            if s.get("topic") == TOPIC:
                sensor_policy = s.get("policy", "none")
                break
                
        payload_text, qos = generate_random_payload(sensor_policy)

        client.publish(TOPIC, payload_text, qos=qos)

        # Show if we are using dynamic push or static policy in log
        policy_label = f"Dynamic Order" if active_policy is not None else f"Static: {sensor_policy}"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Published (Policy Mode: {policy_label})")
        print(payload_text)
        print("-" * 60)

        time.sleep(publish_interval)

except KeyboardInterrupt:
    print("Publisher stopped.")

finally:
    client.loop_stop()
    client.disconnect()
