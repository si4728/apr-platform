import os
import json
import logging
import warnings

# Set up simple logging
logger = logging.getLogger(__name__)


def _suppress_model_compatibility_warnings():
    warnings.filterwarnings("ignore", message="Trying to unpickle estimator .*")
    warnings.filterwarnings("ignore", message=".*If you are loading a serialized model.*")


def _patch_sklearn_pipeline_compatibility(pipeline):
    """
    Repair small sklearn private-attribute differences seen when a model saved
    with sklearn 1.7.x is loaded under newer sklearn versions.
    """
    patched = 0

    def visit(obj):
        nonlocal patched
        if obj is None:
            return
        if obj.__class__.__name__ == "SimpleImputer" and not hasattr(obj, "_fill_dtype"):
            setattr(obj, "_fill_dtype", getattr(obj, "_fit_dtype", None))
            patched += 1
        if hasattr(obj, "named_steps"):
            for step in obj.named_steps.values():
                visit(step)
        if hasattr(obj, "transformers_"):
            for transformer in obj.transformers_:
                if len(transformer) >= 2:
                    visit(transformer[1])
        if hasattr(obj, "transformers"):
            for transformer in obj.transformers:
                if len(transformer) >= 2:
                    visit(transformer[1])

    visit(pipeline)
    return patched

class APREngine:
    def __init__(self):
        # Configuration thresholds for the fallback rule-based APR
        self.high_latency_threshold_ms = 50.0  # ms
        self.high_backlog_threshold = 100      # messages in queue
        self.large_payload_threshold = 1024    # bytes
        
        self.pipeline = None
        self.preprocessor = None
        self.xgb_model = None
        self.meta = None
        self.model_format = "rule_based"
        
        # Load ML model if possible
        model_path = os.path.join("apr", "xgb_model.joblib")
        meta_path = os.path.join("apr", "xgb_model_meta.json")
        runtime_meta_path = os.path.join("apr", "xgb_runtime_meta.json")
        
        if os.path.exists(runtime_meta_path) and os.path.exists(meta_path):
            try:
                _suppress_model_compatibility_warnings()
                import joblib
                from xgboost import XGBRegressor

                with open(runtime_meta_path, "r", encoding="utf-8") as f:
                    runtime_meta = json.load(f)
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)

                model_dir = os.path.dirname(runtime_meta_path)
                preprocessor_path = os.path.join(model_dir, runtime_meta.get("preprocessor", "xgb_preprocessor.joblib"))
                xgb_model_path = os.path.join(model_dir, runtime_meta.get("xgboost_model", "xgb_model.json"))

                self.preprocessor = joblib.load(preprocessor_path)
                patched_count = _patch_sklearn_pipeline_compatibility(self.preprocessor)
                self.xgb_model = XGBRegressor()
                self.xgb_model.load_model(xgb_model_path)
                self.model_format = runtime_meta.get("format", "xgboost_save_model")
                logger.info(
                    "Successfully loaded APR runtime model (%s) with %s compatibility patch(es).",
                    self.model_format,
                    patched_count,
                )
            except Exception as e:
                self.preprocessor = None
                self.xgb_model = None
                logger.warning(f"Failed to load APR runtime model, trying legacy pipeline. Error: {e}")

        if self.xgb_model is None and os.path.exists(model_path) and os.path.exists(meta_path):
            try:
                _suppress_model_compatibility_warnings()
                import joblib
                self.pipeline = joblib.load(model_path)
                patched_count = _patch_sklearn_pipeline_compatibility(self.pipeline)
                with open(meta_path, "r") as f:
                    self.meta = json.load(f)
                self.model_format = "legacy_joblib_pipeline"
                if patched_count:
                    logger.info("Successfully loaded ML-based APR model with %s compatibility patch(es).", patched_count)
                else:
                    logger.info("Successfully loaded ML-based APR model.")
            except Exception as e:
                logger.warning(f"Failed to load ML model, using rule-based fallback. Error: {e}")
        else:
            logger.info("ML model files not found, using rule-based engine.")

    def recommend(self, payload_size: int, network_latency_ms: float, queue_depth: int, topic: str, schema_type: str) -> dict:
        """
        Recommend QoS, compression, encryption, and integrity policies.
        Uses the trained XGBoost model if available, otherwise falls back to rule-based logic.
        """
        # QoS logic is purely rule-based as it is not in the ML model features
        qos = 0
        if queue_depth < self.high_backlog_threshold:
            if "emergency" in topic or "critical" in topic:
                qos = 1

        # Check if we can use the ML model
        if self.xgb_model is not None and self.preprocessor is not None:
            try:
                import pandas as pd
                df, rows = self._candidate_dataframe(payload_size, network_latency_ms, topic, schema_type)
                transformed = self.preprocessor.transform(df)
                predictions = self.xgb_model.predict(transformed)
                return self._policy_from_best_prediction(rows, predictions, qos)
            except Exception as e:
                logger.warning(f"Error during runtime ML prediction, using rule-based fallback: {e}")
                self.preprocessor = None
                self.xgb_model = None

        if self.pipeline is not None:
            try:
                df, rows = self._candidate_dataframe(payload_size, network_latency_ms, topic, schema_type)
                predictions = self.pipeline.predict(df)
                return self._policy_from_best_prediction(rows, predictions, qos)
                
            except Exception as e:
                logger.warning(f"Error during ML prediction, using rule-based fallback: {e}")
                self.pipeline = None
                
        # Rule-based fallback
        policy = {
            "qos": qos,
            "compression": "none",
            "encryption": "none",
            "integrity": "none"
        }

        # Compression
        if payload_size > self.large_payload_threshold and queue_depth < self.high_backlog_threshold:
            policy["compression"] = "gzip"

        # Encryption
        if schema_type in ["sensitive", "auth", "personal"] and queue_depth < self.high_backlog_threshold * 2:
            policy["encryption"] = "AES-GCM"
            
        # Integrity
        if schema_type in ["unknown", "json_undefined_schema", "non_json"] and queue_depth < self.high_backlog_threshold:
            policy["integrity"] = "sha256"

        return policy

    def _candidate_dataframe(self, payload_size, network_latency_ms, topic, schema_type):
        import pandas as pd

        is_secure = (schema_type in ["sensitive", "auth", "personal"]) or \
                    ("emergency" in topic) or ("critical" in topic)
        is_integrity_req = is_secure or (schema_type in ["unknown", "json_undefined_schema", "non_json"])

        enc_candidates = ["aes-gcm"] if is_secure else ["none", "aes-gcm"]
        comp_candidates = ["none", "gzip", "zlib"]
        hash_candidates = ["hash"] if is_integrity_req else ["none", "hash"]

        rows = []
        for enc in enc_candidates:
            for comp in comp_candidates:
                for hsh in hash_candidates:
                    rows.append({
                        "data_size_pub": float(payload_size),
                        "pub_ping": float(network_latency_ms),
                        "environment": "cpc",
                        "encryption_type": enc,
                        "compress_method": comp,
                        "hash_mode": hsh
                    })

        df = pd.DataFrame(rows)
        if self.meta:
            feature_defaults = self.meta.get("feature_defaults", {})
            for col in self.meta.get("num_cols", []):
                if col not in df.columns:
                    df[col] = feature_defaults.get(col, 0.0)
            for col in self.meta.get("cat_cols", []):
                if col not in df.columns:
                    df[col] = feature_defaults.get(col, "none")
            ordered_cols = self.meta.get("num_cols", []) + self.meta.get("cat_cols", [])
            if ordered_cols:
                df = df[ordered_cols]
        return df, rows

    def _policy_from_best_prediction(self, rows, predictions, qos):
        min_idx = predictions.argmin()
        best_row = rows[min_idx]
        enc_map = {"none": "none", "aes-gcm": "AES-GCM"}
        comp_map = {"none": "none", "gzip": "gzip", "zlib": "zlib"}
        hash_map = {"none": "none", "hash": "sha256"}
        return {
            "qos": qos,
            "compression": comp_map.get(best_row["compress_method"], "none"),
            "encryption": enc_map.get(best_row["encryption_type"], "none"),
            "integrity": hash_map.get(best_row["hash_mode"], "none")
        }

# Global instance for easy import
apr_engine = APREngine()
