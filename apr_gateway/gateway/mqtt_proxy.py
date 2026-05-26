import json
import logging
import queue
import threading
import time
import uuid
from time import perf_counter

import paho.mqtt.client as mqtt

from gateway.codec import encode_payload


logger = logging.getLogger(__name__)
POLICY_TOPIC_PREFIX = "iot/sensor/policy/"


class MqttProxy:
    def __init__(self, config, apr_engine, metrics):
        self.config = config
        self.apr_engine = apr_engine
        self.metrics = metrics
        self.is_running = False
        self._seq = 0
        self._work_queue = queue.Queue(maxsize=10000)
        client_suffix = uuid.uuid4().hex[:8]
        self._source = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"apr-gateway-source-{client_suffix}",
        )
        self._target = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"apr-gateway-target-{client_suffix}",
        )
        self._source.on_connect = self._on_connect
        self._source.on_message = self._on_message

    def start(self):
        worker = threading.Thread(target=self._worker_loop, name="apr-gateway-worker", daemon=True)
        worker.start()
        connector = threading.Thread(target=self._connect_clients_loop, name="apr-gateway-mqtt-connect", daemon=True)
        connector.start()
        self.is_running = True
        logger.info("APR Gateway started in %s mode", self.config.apr_mode)

    def _connect_clients_loop(self):
        while True:
            try:
                if self.config.apr_mode != "advisor":
                    self._connect_once(
                        self._target,
                        self.config.target_mqtt_host,
                        self.config.target_mqtt_port,
                        "target",
                    )
                    self._target.loop_start()

                self._connect_once(
                    self._source,
                    self.config.source_mqtt_host,
                    self.config.source_mqtt_port,
                    "source",
                )
                self._source.loop_start()
                return
            except OSError as exc:
                logger.warning("Waiting for MQTT broker connection (%s)", exc)
                time.sleep(2)

    def _connect_once(self, client, host: str, port: int, label: str):
        while True:
            try:
                client.connect(host, port, keepalive=60)
                logger.info("Connected to %s MQTT broker at %s:%s", label, host, port)
                return
            except OSError as exc:
                logger.warning("Waiting for %s MQTT broker at %s:%s (%s)", label, host, port, exc)
                raise

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Connected to source broker; subscribing to %s", self.config.subscribe_topic)
            client.subscribe(self.config.subscribe_topic, qos=0)
        else:
            logger.error("Source broker connection failed: %s", reason_code)

    def _on_message(self, client, userdata, message):
        if message.topic.startswith(POLICY_TOPIC_PREFIX):
            return

        self.metrics.record_received(message.topic)
        try:
            self._work_queue.put_nowait((message.topic, message.payload))
            self.metrics.set_queue_depth(self._work_queue.qsize())
        except queue.Full:
            self.metrics.record_failed("work queue full")
            logger.warning("Dropping message because work queue is full")

    def _worker_loop(self):
        while True:
            topic, payload = self._work_queue.get()
            self.metrics.set_queue_depth(self._work_queue.qsize())
            try:
                self._process_message(topic, payload)
            except Exception as exc:
                logger.exception("Failed to process message from topic %s", topic)
                self.metrics.record_failed(str(exc))
            finally:
                self._work_queue.task_done()

    def _process_message(self, topic: str, payload: bytes):
        payload_size = len(payload)
        data, schema_type, sensitive = self._parse_payload(payload)
        policy = self.apr_engine.recommend(
            payload_size=payload_size,
            network_latency_ms=0.0,
            queue_depth=self._work_queue.qsize(),
            topic=topic,
            schema_type=schema_type,
            sensitive=sensitive,
        )

        started = perf_counter()
        if self.config.apr_mode == "advisor":
            processing_latency_ms = (perf_counter() - started) * 1000
            self.metrics.record_forwarded(topic, policy, processing_latency_ms)
            logger.info("Advisor policy for %s: %s", topic, policy)
            return

        self._seq += 1
        envelope = encode_payload(data, policy, seq=self._seq, experiment_id="apr_gateway")
        output_payload = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        output_topic = self._map_output_topic(topic)
        result = self._target.publish(output_topic, output_payload, qos=int(policy.get("qos", 0)))
        result.wait_for_publish(timeout=5)

        processing_latency_ms = (perf_counter() - started) * 1000
        self.metrics.record_forwarded(topic, policy, processing_latency_ms)
        logger.info("Forwarded %s -> %s with policy %s", topic, output_topic, policy)

    def _parse_payload(self, payload: bytes):
        try:
            text = payload.decode("utf-8")
            data = json.loads(text)
            schema_type = str(data.get("schema_type", data.get("payload_schema_mode", "defined_sensor")))
            sensitive = bool(data.get("sensitive", False))
            return data, schema_type, sensitive
        except Exception:
            return {"raw": payload.hex(), "encoding": "hex"}, "non_json", False

    def _map_output_topic(self, topic: str) -> str:
        prefix = self.config.publish_prefix.strip("/")
        subscribed_root = self.config.subscribe_topic.split("#", 1)[0].strip("/")
        normalized_topic = topic.strip("/")
        if subscribed_root and normalized_topic.startswith(subscribed_root):
            suffix = normalized_topic[len(subscribed_root) :].strip("/")
        else:
            suffix = normalized_topic
        return f"{prefix}/{suffix}" if suffix else prefix
