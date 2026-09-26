"""Pure formatting for the ablation comparison table. Training itself is orchestrated by
the CLI, reusing train.py's parameterized train_model/evaluate as-is - no duplicated
training or evaluation logic lives here.
"""

import pandas as pd

from sloppy.models.evaluate import EvaluationReport


def format_ablation_table(reports: dict[str, EvaluationReport]) -> pd.DataFrame:
    rows = [
        {
            "feature_group": group_name,
            "n": report.overall.n,
            "pr_auc": report.overall.pr_auc,
            "f1": report.overall.f1,
            "baseline_f1": report.majority_baseline.f1,
        }
        for group_name, report in reports.items()
    ]
    return pd.DataFrame(rows)
