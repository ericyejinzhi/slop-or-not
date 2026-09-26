"""One-off SHAP interaction analysis for the Phase 4 README.

Loads a trained model artifact (the `model.joblib` + `metadata.json` pair produced by
`sloppy.models.train.save_model`), re-assembles the evaluation split via the same
`assemble_dataset` used for training/evaluation, and writes the top-N feature-interaction
pairs (by mean absolute SHAP interaction value) to a CSV for manual inspection.

This is deliberately a plain argparse script, not a `slop` CLI subcommand - unlike
`slop model evaluate`/`report`, this is not something that needs routine re-running as
part of the train/evaluate cycle. Run manually, at most a handful of times, against a
final trained "all features" model once real labeled data exists.

Usage:
    uv run python scripts/shap_interaction_report.py path/to/model.joblib \
        --splits-csv data/splits.csv --split test --n 20

Only tree-based estimators (e.g. xgboost) are supported - shap.TreeExplainer does not
work with logistic regression.
"""

import argparse
import csv
import json
from pathlib import Path

import joblib
import numpy as np
import shap

from sloppy.db.session import session_scope
from sloppy.features.dataset import assemble_dataset, load_splits

DEFAULT_SPLITS_CSV = Path("data/splits.csv")
DEFAULT_OUT_CSV = Path("docs/writeups/phase-4/shap-interactions.csv")


def top_interaction_pairs(
    interaction_values: np.ndarray, feature_names: list[str], n: int = 20
) -> list[tuple[str, str, float]]:
    """`interaction_values` is shap's raw per-sample interaction tensor, shape
    (n_samples, n_features, n_features) - symmetric, with the diagonal holding each
    feature's own main effect rather than an interaction. Returns the top-N (feature_i,
    feature_j, mean_abs_interaction) triples over the upper triangle (i < j), sorted by
    mean_abs_interaction descending, averaging the absolute interaction value across all
    samples first.
    """
    mean_abs = np.abs(interaction_values).mean(axis=0)
    n_features = len(feature_names)
    pairs = [
        (feature_names[i], feature_names[j], float(mean_abs[i, j]))
        for i in range(n_features)
        for j in range(i + 1, n_features)
    ]
    pairs.sort(key=lambda pair: pair[2], reverse=True)
    return pairs[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path", type=Path, help="path to a model.joblib artifact")
    parser.add_argument("--splits-csv", type=Path, default=DEFAULT_SPLITS_CSV)
    parser.add_argument("--split", default="test", help="which splits.csv split to explain")
    parser.add_argument("--n", type=int, default=20, help="how many top pairs to report")
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    args = parser.parse_args()

    pipeline = joblib.load(args.model_path)
    metadata = json.loads((args.model_path.parent / "metadata.json").read_text(encoding="utf-8"))
    all_features = metadata["features"]

    splits = load_splits(args.splits_csv)
    with session_scope() as session:
        df = assemble_dataset(session, splits)
    eval_df = df[df["split"] == args.split]
    if eval_df.empty:
        raise SystemExit(f"No rows found for split {args.split!r} in {args.splits_csv}")

    preprocessor = pipeline.named_steps["preprocess"]
    estimator = pipeline.named_steps["estimator"]
    transformed = preprocessor.transform(eval_df[all_features])
    transformed_feature_names = list(preprocessor.get_feature_names_out())

    explainer = shap.TreeExplainer(estimator)
    interaction_values = explainer.shap_interaction_values(transformed)
    if isinstance(interaction_values, list):
        # Some estimators return one array per class - the positive ("down") class is last.
        interaction_values = interaction_values[-1]

    pairs = top_interaction_pairs(interaction_values, transformed_feature_names, n=args.n)

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["feature_i", "feature_j", "mean_abs_interaction"])
        writer.writerows(pairs)

    print(f"Wrote top {len(pairs)} interaction pairs to {args.out_csv}")


if __name__ == "__main__":
    main()
