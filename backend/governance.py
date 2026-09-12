"""Fairness, drift and model-governance utilities for officer oversight."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

from .local_models import fraud_anomaly_model
from .policy_engine import POLICY_VERSION


PROTECTED_ATTRIBUTE_ALLOWLIST = {"gender", "sex", "age_band", "disability", "religion", "caste", "marital_status"}


def fairness_report(applications: Iterable[Any], attribute: str) -> dict[str, Any]:
    if attribute not in PROTECTED_ATTRIBUTE_ALLOWLIST:
        raise ValueError(f"Unsupported protected attribute. Allowed: {', '.join(sorted(PROTECTED_ATTRIBUTE_ALLOWLIST))}")
    groups: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "approved": 0})
    excluded = 0
    for application in applications:
        value = (application.raw_data or {}).get(attribute)
        if value in (None, ""):
            excluded += 1
            continue
        group = str(value).strip()
        groups[group]["total"] += 1
        groups[group]["approved"] += int(application.status == "APPROVE")
    rates = {
        group: {
            **counts,
            "selection_rate": round(counts["approved"] / counts["total"], 4) if counts["total"] else 0,
        }
        for group, counts in groups.items()
    }
    reference_rate = max((item["selection_rate"] for item in rates.values()), default=0)
    for item in rates.values():
        item["disparate_impact_ratio"] = round(item["selection_rate"] / reference_rate, 4) if reference_rate else None
        item["requires_review"] = item["total"] >= 20 and item["disparate_impact_ratio"] is not None and item["disparate_impact_ratio"] < 0.8
    return {
        "attribute": attribute,
        "groups": rates,
        "excluded_missing_attribute": excluded,
        "minimum_group_size": 20,
        "review_threshold": 0.8,
        "warning": "Descriptive monitoring only. Small samples and historical labels require governance review.",
    }


def drift_report(applications: list[Any]) -> dict[str, Any]:
    ordered = sorted(applications, key=lambda item: item.created_at)
    midpoint = len(ordered) // 2
    baseline, current = ordered[:midpoint], ordered[midpoint:]
    features = ("income", "loan_amount", "credit_score", "dti", "risk_score", "fraud_score")
    results = {}
    for feature in features:
        older = [float(getattr(item, feature) or 0) for item in baseline]
        newer = [float(getattr(item, feature) or 0) for item in current]
        if not older or not newer:
            results[feature] = {"status": "INSUFFICIENT_DATA"}
            continue
        baseline_mean, current_mean = mean(older), mean(newer)
        scale = pstdev(older) or max(abs(baseline_mean) * 0.1, 1)
        standardized_shift = abs(current_mean - baseline_mean) / scale
        results[feature] = {
            "baseline_mean": round(baseline_mean, 3),
            "current_mean": round(current_mean, 3),
            "standardized_shift": round(standardized_shift, 3),
            "status": "DRIFT_ALERT" if standardized_shift >= 1 else "STABLE",
        }
    return {
        "sample_size": len(ordered),
        "baseline_size": len(baseline),
        "current_size": len(current),
        "features": results,
        "method": "standardized mean shift; alert threshold 1.0",
    }


def model_registry() -> list[dict[str, Any]]:
    anomaly = fraud_anomaly_model.predict({})
    supervised = Path(__file__).resolve().parents[1] / "models" / "credit_calibrated.joblib"
    return [
        {"name": "credit-risk-scorecard", "version": "scorecard-2026.09", "stage": "production", "explainability": "native reasons"},
        {"name": "fraud-rule-scorecard", "version": "scorecard-2026.09", "stage": "production", "explainability": "native reasons"},
        {"name": "fraud-isolation-forest", "version": anomaly.model_version, "stage": "production" if anomaly.available else "unavailable", "explainability": "anomaly margin + feature coverage"},
        {"name": "sentiment-tfidf-logistic", "version": "sentiment-2026.09", "stage": "production", "explainability": "matched vocabulary"},
        {"name": "supervised-credit-model", "version": f"calibrated-{supervised.stat().st_mtime_ns:x}" if supervised.exists() else None, "stage": "validation" if supervised.exists() else "blocked_pending_governed_labels", "explainability": "SHAP required before promotion"},
        {"name": "lending-policy", "version": POLICY_VERSION, "stage": "production", "explainability": "versioned policy citations"},
    ]
