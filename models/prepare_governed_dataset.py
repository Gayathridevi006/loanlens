"""De-identify and split a labelled lending dataset with a reproducible manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split


DIRECT_IDENTIFIERS = {"name", "applicant_name", "email", "phone", "mobile", "pan", "pan_number", "aadhaar", "address", "account_number"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", default="models/governed")
    parser.add_argument("--protected", nargs="*", default=[])
    args = parser.parse_args()
    source, output = Path(args.input), Path(args.output_dir)
    data = pd.read_csv(source)
    if args.target not in data:
        raise SystemExit(f"Target column {args.target!r} is missing")
    removed = sorted(column for column in data if column.lower() in DIRECT_IDENTIFIERS)
    governed = data.drop(columns=removed)
    train, remainder = train_test_split(governed, test_size=0.4, random_state=42, stratify=governed[args.target])
    validation, test = train_test_split(remainder, test_size=0.5, random_state=42, stratify=remainder[args.target])
    output.mkdir(parents=True, exist_ok=True)
    for name, frame in (("train", train), ("validation", validation), ("test", test)):
        frame.to_csv(output / f"{name}.csv", index=False)
    manifest = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "target": args.target,
        "protected_attributes_for_evaluation_only": args.protected,
        "direct_identifiers_removed": removed,
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "columns": list(governed.columns),
        "random_state": 42,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
