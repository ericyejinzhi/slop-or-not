from sloppy.models.ablation import format_ablation_table
from sloppy.models.evaluate import BinaryMetrics, EvaluationReport


def _fake_report(n: int, pr_auc: float, f1: float, baseline_f1: float) -> EvaluationReport:
    overall = BinaryMetrics(n=n, pr_auc=pr_auc, f1=f1, tp=1, fp=1, tn=1, fn=1)
    baseline = BinaryMetrics(n=n, pr_auc=0.5, f1=baseline_f1, tp=0, fp=0, tn=0, fn=0)
    return EvaluationReport(overall=overall, majority_baseline=baseline, per_channel={})


def test_format_ablation_table_has_one_row_per_group():
    reports = {
        "metadata": _fake_report(n=50, pr_auc=0.6, f1=0.5, baseline_f1=0.3),
        "metadata_text": _fake_report(n=50, pr_auc=0.7, f1=0.6, baseline_f1=0.3),
        "all": _fake_report(n=50, pr_auc=0.75, f1=0.65, baseline_f1=0.3),
    }

    table = format_ablation_table(reports)

    assert list(table["feature_group"]) == ["metadata", "metadata_text", "all"]
    assert list(table["pr_auc"]) == [0.6, 0.7, 0.75]
    assert list(table["f1"]) == [0.5, 0.6, 0.65]
    assert list(table["baseline_f1"]) == [0.3, 0.3, 0.3]
    assert list(table["n"]) == [50, 50, 50]


def test_format_ablation_table_empty_reports_produces_empty_table():
    table = format_ablation_table({})
    assert table.empty
