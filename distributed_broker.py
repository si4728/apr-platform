DEFAULT_KEEPALIVE = 60


def normalize_brokers(mqtt_config=None):
    if not isinstance(mqtt_config, dict):
        mqtt_config = {}

    raw_brokers = mqtt_config.get("brokers")
    if not isinstance(raw_brokers, list) or not raw_brokers:
        raw_brokers = [{
            "name": "primary",
            "host": mqtt_config.get("broker", "127.0.0.1"),
            "port": mqtt_config.get("port", 1883),
            "priority": 1,
            "enabled": True,
        }]

    brokers = []
    for index, broker in enumerate(raw_brokers):
        if not isinstance(broker, dict) or broker.get("enabled", True) is False:
            continue
        host = broker.get("host") or broker.get("broker") or broker.get("hostname")
        if not host:
            continue
        brokers.append({
            "name": broker.get("name") or f"broker_{index + 1}",
            "host": host,
            "port": int(broker.get("port", 1883)),
            "priority": int(broker.get("priority", index + 1)),
            "enabled": True,
        })

    brokers.sort(key=lambda item: item["priority"])
    return brokers


def get_primary_broker(mqtt_config=None):
    brokers = normalize_brokers(mqtt_config)
    if not brokers:
        raise ValueError("No enabled MQTT brokers are configured")
    return brokers[0]


def connect_client_to_any_broker(client, mqtt_config, keepalive=DEFAULT_KEEPALIVE):
    errors = []
    for broker in normalize_brokers(mqtt_config):
        try:
            client.connect(broker["host"], broker["port"], keepalive)
            client._distributed_broker = broker
            return broker
        except Exception as exc:
            errors.append({
                "broker": broker,
                "error": str(exc),
            })
    raise ConnectionError(f"Unable to connect to any configured MQTT broker: {errors}")


def publish_single_to_any_broker(topic, payload, mqtt_config, qos=0, retain=False, publish_single=None):
    if publish_single is None:
        import paho.mqtt.publish as mqtt_publish
        publish_single = mqtt_publish.single

    errors = []
    for broker in normalize_brokers(mqtt_config):
        try:
            publish_single(
                topic,
                payload=payload,
                hostname=broker["host"],
                port=broker["port"],
                qos=int(qos),
                retain=bool(retain),
            )
            return broker
        except Exception as exc:
            errors.append({
                "broker": broker,
                "error": str(exc),
            })
    raise ConnectionError(f"Unable to publish via any configured MQTT broker: {errors}")
