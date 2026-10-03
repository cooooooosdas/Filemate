"""防止合成数据、无效分数与重复参与者形成真实效果结论。"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evaluation.analyze_competition_trials import _number
from evaluation.analyze_study import analyze_annotations, analyze_user_study


def study(path: Path, changes: dict[str, str] | None = None, duplicate: bool = False) -> Path:
    """写入明确标记为合成输入的验证夹具。"""
    row = {"participant_id": "P001", "condition": "filemate", "pre_correct": "6", "post_correct": "9",
           "pre_minutes": "40", "post_minutes": "30", "score_max": "10", "sample_kind": "synthetic"}
    row.update({f"sus_q{i}": "5" if i % 2 else "1" for i in range(1, 11)})
    row.update(changes or {})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
        if duplicate:
            writer.writerow(row)
    return path


def test_synthetic_pipeline_exposes_units_and_undefined_effect_size(tmp_path: Path) -> None:
    report = analyze_user_study(study(tmp_path / "study.csv"))
    assert report["status"] == "synthetic_pipeline_only"
    assert report["relative_score_gain_percent"] == 50
    assert report["score_gain_percentage_points"] == 30
    assert report["minutes_saved_percent"] == 25
    assert report["mean_sus"] == 100
    assert report["score_gain_cohen_dz"] is None


@pytest.mark.parametrize("changes", [
    {"pre_correct": "NaN"}, {"post_correct": "11"}, {"post_minutes": "-1"},
    {"pre_minutes": "0"}, {"sus_q3": "6"}, {"sus_q7": "3.5"},
    {"score_max": "inf"}, {"sample_kind": "real"}, {"participant_id": "张三"},
    {"email": "private@example.invalid"},
])
def test_invalid_study_records_fail_closed(tmp_path: Path, changes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        analyze_user_study(study(tmp_path / "study.csv", changes))


def test_duplicate_students_do_not_inflate_sample_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="重复"):
        analyze_user_study(study(tmp_path / "study.csv", duplicate=True))


def test_example_file_cannot_be_relabelled_real(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="示例"):
        analyze_user_study(study(tmp_path / "study.example.csv"), sample_kind="real")


@pytest.mark.parametrize("changes", [
    {}, {"consent_confirmed": "0"}, {"study_date": (datetime.now(timezone.utc).astimezone().date() + timedelta(days=1)).isoformat()},
])
def test_real_label_requires_consent_actual_date_and_maximum(tmp_path: Path, changes: dict[str, str]) -> None:
    row = {"sample_kind": "real", "study_date": datetime.now(timezone.utc).astimezone().date().isoformat(), "consent_confirmed": "1", "discipline_code": "M01"}
    row.update(changes)
    if not changes:
        row["consent_confirmed"] = ""
    with pytest.raises(ValueError):
        analyze_user_study(study(tmp_path / "study.csv", row), sample_kind="real")


def test_small_explicit_real_label_remains_pending_without_identity_export(tmp_path: Path) -> None:
    # 仅检验标签合同；这条测试夹具不是研究数据。
    row = {"sample_kind": "real", "study_date": datetime.now(timezone.utc).astimezone().date().isoformat(), "consent_confirmed": "1", "discipline_code": "M01"}
    report = analyze_user_study(study(tmp_path / "study.csv", row), sample_kind="real")
    assert report["status"] == "pending_more_samples"
    assert report["participant_count"] == 1
    assert "P001" not in str(report)


def test_multiple_conditions_are_reported_separately(tmp_path: Path) -> None:
    target = study(tmp_path / "study.csv")
    with target.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = reader.fieldnames
    rows.append({**rows[0], "participant_id": "P002", "condition": "baseline", "post_correct": "6"})
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or [])
        writer.writeheader()
        writer.writerows(rows)
    report = analyze_user_study(target)
    assert set(report["by_condition"]) == {"baseline", "filemate"}
    assert "mean_score_gain" not in report


@pytest.mark.parametrize("body", ["q1,A,2,1\nq1,A,2,1\n", "q1,A,2,1\n", "q1,A,2,1\nq1,B,2,1\nq1,C,2,1\n"])
def test_annotations_require_exactly_two_independent_raters(tmp_path: Path, body: str) -> None:
    target = tmp_path / "annotations.csv"
    target.write_text("item_id,annotator,expected_page,answerable\n" + body, encoding="utf-8")
    with pytest.raises(ValueError):
        analyze_annotations(target)


def test_constant_annotation_labels_do_not_fabricate_kappa(tmp_path: Path) -> None:
    target = tmp_path / "annotations.csv"
    target.write_text("item_id,annotator,expected_page,answerable\nq1,A,2,1\nq1,B,2,1\n", encoding="utf-8")
    report = analyze_annotations(target)
    assert report["raw_agreement"] == 1
    assert report["cohen_kappa"] is None


@pytest.mark.parametrize("field,value", [("completed", "2"), ("system_score", "101"), ("model_calls", "NaN"), ("elapsed_seconds", "-1")])
def test_competition_metrics_reject_impossible_or_nonfinite_values(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _number({field: value}, field)
