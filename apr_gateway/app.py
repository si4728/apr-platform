import logging

from flask import Flask, jsonify, request

from gateway.config import GatewayConfig
from gateway.decision_engine import APREngine
from gateway.metrics import MetricsStore
from gateway.mqtt_proxy import MqttProxy


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

config = GatewayConfig.from_env()
metrics = MetricsStore()
apr_engine = APREngine(model_dir=config.model_dir)
proxy = MqttProxy(config=config, apr_engine=apr_engine, metrics=metrics)

app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok" if proxy.is_running else "starting",
            "mode": config.apr_mode,
            "source": f"{config.source_mqtt_host}:{config.source_mqtt_port}",
            "target": f"{config.target_mqtt_host}:{config.target_mqtt_port}",
            "subscribe_topic": config.subscribe_topic,
            "publish_prefix": config.publish_prefix,
            "model_loaded": apr_engine.model_loaded,
        }
    )


@app.get("/api/metrics")
def get_metrics():
    return jsonify(metrics.snapshot())


@app.get("/api/policies/current")
def get_current_policies():
    return jsonify(metrics.policy_snapshot())


@app.post("/api/recommend")
def recommend_policy():
    payload = request.get_json(silent=True) or {}
    policy = apr_engine.recommend(
        payload_size=int(payload.get("payload_size", 0)),
        network_latency_ms=float(payload.get("latency_ms", 0.0)),
        queue_depth=int(payload.get("queue_depth", 0)),
        topic=str(payload.get("topic", "")),
        schema_type=str(payload.get("schema_type", "defined_sensor")),
        sensitive=bool(payload.get("sensitive", False)),
    )
    return jsonify({"policy": policy, "model_loaded": apr_engine.model_loaded})


if __name__ == "__main__":
    proxy.start()
    app.run(host="0.0.0.0", port=config.http_port)
