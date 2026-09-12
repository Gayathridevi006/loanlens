"""Formal attribution adapter for validated supervised model artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd


MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "credit_calibrated.joblib"


def explain_supervised_prediction(record: dict[str, Any]) -> dict[str, Any]:
    if not MODEL_PATH.exists():
        return {"status": "UNAVAILABLE", "reason": "A governed, labelled dataset has not produced a validated supervised model."}
    bundle = joblib.load(MODEL_PATH)
    frame = pd.DataFrame([{feature: record.get(feature) for feature in bundle["features"]}])
    probability = float(bundle["pipeline"].predict_proba(frame)[0, 1])
    try:
        import shap
        explainer = shap.Explainer(bundle["pipeline"].predict_proba, frame)
        values = explainer(frame)
        raw_values = values.values[0]
        if getattr(raw_values, "ndim", 1) > 1:
            raw_values = raw_values[:, 1]
        attributions = sorted(
            ({"feature": feature, "value": record.get(feature), "shap_value": round(float(value), 6)} for feature, value in zip(bundle["features"], raw_values)),
            key=lambda item: abs(item["shap_value"]), reverse=True,
        )
        return {"status": "EXPLAINED", "method": "SHAP", "probability": round(probability, 6), "attributions": attributions, "model_metrics": bundle["metrics"]}
    except ImportError:
        return {"status": "MODEL_AVAILABLE_SHAP_MISSING", "probability": round(probability, 6), "reason": "Install backend/requirements-ml.txt to enable SHAP attributions."}
    except Exception as exc:
        return {"status": "EXPLANATION_FAILED", "probability": round(probability, 6), "reason": str(exc)[:500]}
