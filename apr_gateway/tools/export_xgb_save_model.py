import json
from pathlib import Path

import joblib


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

PIPELINE_PATH = MODELS / "xgb_model.joblib"
BASE_META_PATH = MODELS / "xgb_model_meta.json"
PREPROCESSOR_PATH = MODELS / "xgb_preprocessor.joblib"
XGB_MODEL_PATH = MODELS / "xgb_model.json"
RUNTIME_META_PATH = MODELS / "xgb_runtime_meta.json"


def main():
    if not PIPELINE_PATH.exists():
        raise FileNotFoundError(f"Missing pipeline model: {PIPELINE_PATH}")
    if not BASE_META_PATH.exists():
        raise FileNotFoundError(f"Missing model metadata: {BASE_META_PATH}")

    pipeline = joblib.load(PIPELINE_PATH)
    if not hasattr(pipeline, "named_steps"):
        raise TypeError("Expected sklearn Pipeline with named_steps")

    preprocessor = pipeline.named_steps.get("preprocess")
    model = pipeline.named_steps.get("model")
    if preprocessor is None:
        raise KeyError("Pipeline step 'preprocess' not found")
    if model is None:
        raise KeyError("Pipeline step 'model' not found")
    if not hasattr(model, "save_model"):
        raise TypeError(f"Pipeline model step does not support save_model: {type(model)!r}")

    joblib.dump(preprocessor, PREPROCESSOR_PATH)
    model.save_model(XGB_MODEL_PATH)

    runtime_meta = {
        "format": "sklearn_preprocessor_plus_xgboost_save_model",
        "source_pipeline": PIPELINE_PATH.name,
        "base_meta": BASE_META_PATH.name,
        "preprocessor": PREPROCESSOR_PATH.name,
        "xgboost_model": XGB_MODEL_PATH.name,
    }
    RUNTIME_META_PATH.write_text(
        json.dumps(runtime_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "saved_preprocessor": str(PREPROCESSOR_PATH),
        "saved_xgboost_model": str(XGB_MODEL_PATH),
        "saved_runtime_meta": str(RUNTIME_META_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
