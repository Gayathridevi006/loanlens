"""Train and calibrate a supervised credit baseline on governed data splits."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="models/governed")
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", default="models/credit_calibrated.joblib")
    args = parser.parse_args()
    root = Path(args.data_dir)
    train, validation, test = (pd.read_csv(root / f"{name}.csv") for name in ("train", "validation", "test"))
    manifest = json.loads((root / "manifest.json").read_text())
    protected = set(manifest.get("protected_attributes_for_evaluation_only", []))
    features = [column for column in train.columns if column != args.target and column not in protected]
    numeric = [column for column in features if pd.api.types.is_numeric_dtype(train[column])]
    categorical = [column for column in features if column not in numeric]
    transformer = ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
        ("categorical", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), categorical),
    ])
    base = Pipeline([("features", transformer), ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))])
    model = CalibratedClassifierCV(base, method="sigmoid", cv=5)
    model.fit(train[features], train[args.target])
    metrics = {}
    for name, frame in (("validation", validation), ("test", test)):
        probability = model.predict_proba(frame[features])[:, 1]
        prediction = (probability >= 0.5).astype(int)
        metrics[name] = {
            "roc_auc": round(roc_auc_score(frame[args.target], probability), 4),
            "brier_score": round(brier_score_loss(frame[args.target], probability), 4),
            "accuracy": round(accuracy_score(frame[args.target], prediction), 4),
            "rows": len(frame),
        }
    output = Path(args.output)
    joblib.dump({"pipeline": model, "features": features, "target": args.target, "metrics": metrics, "dataset_manifest": manifest}, output)
    output.with_suffix(".metrics.json").write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
