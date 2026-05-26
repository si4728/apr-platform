import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class APREngine:
    def __init__(self, model_dir: str = "models"):
        self.high_latency_threshold_ms = 50.0
        self.high_backlog_threshold = 100
        self.large_payload_threshold = 1024
        self.pipeline = None
        self.preprocessor = None
        self.xgb_model = None
        self.meta = None
        self.model_format = "rule"

        model_path = Path(model_dir) / "xgb_model.joblib"
        meta_path = Path(model_dir) / "xgb_model_meta.json"
        preprocessor_path = Path(model_dir) / "xgb_preprocessor.joblib"
        xgb_json_path = Path(model_dir) / "xgb_model.json"

        if preprocessor_path.exists() and xgb_json_path.exists() and meta_path.exists():
            try:
                import joblib
                from xgboost import XGBRegressor

                self.preprocessor = joblib.load(preprocessor_path)
                self.xgb_model = XGBRegressor()
                self.xgb_model.load_model(xgb_json_path)
                self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.model_format = "save_model"
                logger.info("Loaded APR model from %s and %s", preprocessor_path, xgb_json_path)
            except Exception:
                logger.exception("Failed to load save_model artifacts; trying joblib pipeline fallback")

        if self.xgb_model is None and model_path.exists() and meta_path.exists():
            try:
                import joblib

                self.pipeline = joblib.load(model_path)
                self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self.model_format = "joblib_pipeline"
                logger.info("Loaded ML-based APR model from %s", model_path)
            except Exception:
                logger.exception("Failed to load ML model; using rule-based APR fallback")
        elif self.xgb_model is None and self.pipeline is None:
            logger.info("APR model files not found in %s; using rule-based engine", model_dir)

    @property
    def model_loaded(self) -> bool:
        return self.pipeline is not None or self.xgb_model is not None

    def recommend(
        self,
        payload_size: int,
        network_latency_ms: float,
        queue_depth: int,
        topic: str,
        schema_type: str = "defined_sensor",
        sensitive: bool = False,
    ) -> dict:
        qos = 0
        if queue_depth < self.high_backlog_threshold and self._is_critical(topic):
            qos = 1

        if self.model_loaded:
            try:
                return self._recommend_with_model(
                    qos=qos,
                    payload_size=payload_size,
                    network_latency_ms=network_latency_ms,
                    topic=topic,
                    schema_type=schema_type,
                    sensitive=sensitive,
                )
            except Exception:
                logger.exception("APR model prediction failed; using rule-based fallback")

        return self._recommend_with_rules(
            qos=qos,
            payload_size=payload_size,
            queue_depth=queue_depth,
            schema_type=schema_type,
            sensitive=sensitive,
        )

    def _recommend_with_model(
        self,
        qos: int,
        payload_size: int,
        network_latency_ms: float,
        topic: str,
        schema_type: str,
        sensitive: bool,
    ) -> dict:
        import pandas as pd

        secure = sensitive or self._is_secure_schema(schema_type) or self._is_critical(topic)
        integrity_required = secure or schema_type in {"unknown", "json_undefined_schema", "non_json"}

        enc_candidates = ["aes-gcm"] if secure else ["none", "aes-gcm"]
        comp_candidates = ["none", "gzip", "zlib"]
        hash_candidates = ["hash"] if integrity_required else ["none", "hash"]

        rows = []
        for enc in enc_candidates:
            for comp in comp_candidates:
                for hsh in hash_candidates:
                    row = self._base_feature_row()
                    row.update(
                        {
                            "data_size_pub": float(payload_size),
                            "pub_ping": float(network_latency_ms),
                            "environment": "cpc",
                            "encryption_type": enc,
                            "compress_method": comp,
                            "hash_mode": hsh,
                        }
                    )
                    rows.append(row)

        predictions = self._predict(pd.DataFrame(rows))
        best_row = rows[predictions.argmin()]

        return {
            "qos": qos,
            "compression": {"none": "none", "gzip": "gzip", "zlib": "zlib"}.get(best_row["compress_method"], "none"),
            "encryption": {"none": "none", "aes-gcm": "AES-GCM"}.get(best_row["encryption_type"], "none"),
            "integrity": {"none": "none", "hash": "sha256"}.get(best_row["hash_mode"], "none"),
        }

    def _predict(self, rows_df):
        if self.xgb_model is not None and self.preprocessor is not None:
            features = self.preprocessor.transform(rows_df)
            return self.xgb_model.predict(features)
        return self.pipeline.predict(rows_df)

    def _base_feature_row(self) -> dict:
        meta = self.meta or {}
        row = {}

        for column in meta.get("num_cols", ["data_size_pub", "pub_ping"]):
            row[column] = float(meta.get("feature_defaults", {}).get(column, 0.0))

        for column in meta.get("cat_cols", ["environment", "encryption_type", "compress_method", "hash_mode"]):
            row[column] = "none"

        return row

    def _recommend_with_rules(
        self,
        qos: int,
        payload_size: int,
        queue_depth: int,
        schema_type: str,
        sensitive: bool,
    ) -> dict:
        policy = {"qos": qos, "compression": "none", "encryption": "none", "integrity": "none"}

        if payload_size > self.large_payload_threshold and queue_depth < self.high_backlog_threshold:
            policy["compression"] = "gzip"

        if (sensitive or self._is_secure_schema(schema_type)) and queue_depth < self.high_backlog_threshold * 2:
            policy["encryption"] = "AES-GCM"

        if schema_type in {"unknown", "json_undefined_schema", "non_json"} and queue_depth < self.high_backlog_threshold:
            policy["integrity"] = "sha256"

        return policy

    @staticmethod
    def _is_critical(topic: str) -> bool:
        topic_lower = topic.lower()
        return "emergency" in topic_lower or "critical" in topic_lower or "alarm" in topic_lower

    @staticmethod
    def _is_secure_schema(schema_type: str) -> bool:
        return schema_type in {"sensitive", "auth", "personal"}
