import os
import json
import logging

# Set up simple logging
logger = logging.getLogger(__name__)

class APREngine:
    def __init__(self):
        # Configuration thresholds for the fallback rule-based APR
        self.high_latency_threshold_ms = 50.0  # ms
        self.high_backlog_threshold = 100      # messages in queue
        self.large_payload_threshold = 1024    # bytes
        
        self.pipeline = None
        self.meta = None
        
        # Load ML model if possible
        model_path = os.path.join("apr", "xgb_model.joblib")
        meta_path = os.path.join("apr", "xgb_model_meta.json")
        
        if os.path.exists(model_path) and os.path.exists(meta_path):
            try:
                import joblib
                self.pipeline = joblib.load(model_path)
                with open(meta_path, "r") as f:
                    self.meta = json.load(f)
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
        if self.pipeline is not None:
            try:
                import pandas as pd
                
                # Determine constraints based on topic / schema
                is_secure = (schema_type in ["sensitive", "auth", "personal"]) or \
                            ("emergency" in topic) or ("critical" in topic)
                            
                is_integrity_req = is_secure or (schema_type in ["unknown", "json_undefined_schema", "non_json"])

                # Allowed candidates (restricted to what is supported by the codebase)
                enc_candidates = ["aes-gcm"] if is_secure else ["none", "aes-gcm"]
                comp_candidates = ["none", "gzip", "zlib"]
                hash_candidates = ["hash"] if is_integrity_req else ["none", "hash"]
                
                # Generate all valid candidate feature rows
                rows = []
                for enc in enc_candidates:
                    for comp in comp_candidates:
                        for hsh in hash_candidates:
                            rows.append({
                                "data_size_pub": float(payload_size),
                                "pub_ping": float(network_latency_ms),
                                "environment": "cpc",  # Default environment
                                "encryption_type": enc,
                                "compress_method": comp,
                                "hash_mode": hsh
                            })
                
                # Convert to DataFrame
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
                
                # Predict latency (total_time)
                predictions = self.pipeline.predict(df)
                
                # Find the option that minimizes predicted latency
                min_idx = predictions.argmin()
                best_row = rows[min_idx]
                
                # Map back to simulation-supported strings
                enc_map = {"none": "none", "aes-gcm": "AES-GCM"}
                comp_map = {"none": "none", "gzip": "gzip", "zlib": "zlib"}
                hash_map = {"none": "none", "hash": "sha256"}
                
                return {
                    "qos": qos,
                    "compression": comp_map.get(best_row["compress_method"], "none"),
                    "encryption": enc_map.get(best_row["encryption_type"], "none"),
                    "integrity": hash_map.get(best_row["hash_mode"], "none")
                }
                
            except Exception as e:
                logger.error(f"Error during ML prediction, using rule-based fallback: {e}")
                
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

# Global instance for easy import
apr_engine = APREngine()
