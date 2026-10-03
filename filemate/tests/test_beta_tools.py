"""验证 B3 匿名采集、区间与 RC 证据；夹具均为工程合成数据。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evaluation.analyze_competition_trials import analyze_agent_trials, analyze_companion_trials
from evaluation.analyze_study import analyze_annotations, analyze_user_study
from evaluation.calibrate_interview import calibrate
from evaluation.csv_contract import read_rows
from evaluation.intervals import mean_interval
from evaluation.prepare_beta import prepare
from scripts.acceptance import release_readiness as rc

ROOT = Path(__file__).resolve().parents[2]


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    """写入严格匿名、明确合成的数值夹具。"""
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def task(**changes: str) -> dict[str, str]:
    """构造匿名任务合同夹具，不作为实际用户实验。"""
    return {
        "participant_id": "P001",
        "task_id": "T01",
        "condition": "filemate",
        "completed": "1",
        "hallucination_count": "0",
        "reviewed_claim_count": "10",
        "elapsed_seconds": "90",
        "model_calls": "4",
        "estimated_cost_yuan": "0.08",
        "sample_kind": "synthetic",
        **changes,
    }


@pytest.mark.parametrize(
    "body",
    [
        "a,a\n1,2\n",
        "a,\n1,2\n",
        "a,b\n1\n",
        "a,b\n1,2,3\n",
        "a,b\n,2\n",
        'a,b\n"unfinished,2\n',
        "a,b,email\n1,2,hidden\n",
    ],
)
def test_csv_rejects_ambiguous_missing_or_private_inputs(tmp_path: Path, body: str) -> None:
    path = tmp_path / "invalid.csv"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        read_rows(path, {"a", "b"}, {"a", "b"})


@pytest.mark.parametrize(
    "changes",
    [
        {"model_calls": "1.5"},
        {"completed": "2"},
        {"elapsed_seconds": "inf"},
        {"hallucination_count": "11"},
        {"participant_id": "张三"},
        {"email": "private"},
        {"sample_kind": "real"},
        {"study_date": "9999-01-01"},
        {"task_id": ""},
    ],
)
def test_task_range_identity_and_kind_fail_closed(tmp_path: Path, changes: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        analyze_agent_trials(write_csv(tmp_path / "tasks.csv", [task(**changes)]))


@pytest.mark.parametrize("second", [task(), task(task_id="T02", condition="baseline")])
def test_duplicate_task_or_cross_condition_participant_rejected(
    tmp_path: Path, second: dict[str, str]
) -> None:
    with pytest.raises(ValueError, match="重复|跨条件"):
        analyze_agent_trials(write_csv(tmp_path / "tasks.csv", [task(), second]))


def test_repeated_distinct_tasks_keep_one_independent_participant(tmp_path: Path) -> None:
    result = analyze_agent_trials(write_csv(tmp_path / "tasks.csv", [task(), task(task_id="T02")]))
    assert result["participant_count_by_condition"] == {"filemate": 1}
    assert result["conditions"]["filemate"]["trial_count"] == 2
    assert (
        result["conditions"]["filemate"]["confidence_intervals"]["participant_mean_completion"][
            "lower"
        ]
        is None
    )


def test_real_tasks_require_each_row_consent_kind_and_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        analyze_agent_trials(write_csv(tmp_path / "tasks.csv", [task(sample_kind="real")]), "real")


def test_companion_does_not_accept_overcompletion(tmp_path: Path) -> None:
    row = {
        "participant_id": "P001",
        "condition": "a",
        "assigned_tasks": "2",
        "completed_tasks": "3",
        "due_reviews": "1",
        "completed_reviews": "1",
        "returned_next_day": "1",
    }
    with pytest.raises(ValueError):
        analyze_companion_trials(write_csv(tmp_path / "tasks.csv", [row]))


def test_intervals_reproducible_units_and_small_samples() -> None:
    assert mean_interval([10, 20, 30], "minutes") == mean_interval([10, 20, 30], "minutes")
    assert mean_interval([10], "minutes")["lower"] is None
    constant = mean_interval([10, 10], "minutes")
    assert constant["lower"] == constant["upper"] == 10
    assert constant["status"] == "zero_observed_variance"
    varying = mean_interval([10, 20, 30], "minutes")
    assert 10 <= varying["lower"] <= 20 <= varying["upper"] <= 30
    assert varying["sample_unit"] == "independent_participant"
    with pytest.raises(ValueError):
        mean_interval([float("nan")], "minutes")


def test_study_report_has_actual_date_provenance_and_per_condition_intervals(
    tmp_path: Path,
) -> None:
    example = ROOT / "evaluation/datasets/user_study.example.csv"
    with example.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row.update(score_max="10", sample_kind="synthetic", study_date="2026-08-01")
    rows[-1]["condition"] = "baseline"
    report = analyze_user_study(write_csv(tmp_path / "study.csv", rows))
    assert report["provenance"]["measurement_date_range"] == {
        "start": "2026-08-01",
        "end": "2026-08-01",
    }
    assert len(report["provenance"]["source_sha256"]) == 64
    assert "confidence_intervals" not in report
    assert (
        report["by_condition"]["filemate"]["confidence_intervals"]["score_gain"]["unit"]
        == "percentage_points"
    )
    assert report["by_condition"]["baseline"]["confidence_intervals"]["sus"]["lower"] is None
    assert "P001" not in json.dumps(report)


def test_export_is_synthetic_roundtrips_and_never_overwrites(tmp_path: Path) -> None:
    example = ROOT / "evaluation/datasets/user_study.example.csv"
    tasks = write_csv(tmp_path / "tasks.csv", [task()])
    output = tmp_path / "bundle"
    report = prepare(example, output, tasks)
    assert report["sample_kind"] == "synthetic"
    assert (output / "user_study.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert (
        analyze_user_study(output / "user_study.csv")["participant_count"]
        == report["user_study"]["participant_count"]
    )
    assert analyze_agent_trials(output / "anonymous_tasks.csv")["provenance"]["record_count"] == 1
    assert "P001" not in (output / "report.json").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="覆盖"):
        prepare(example, output)


def test_failed_export_creates_no_partial_directory(tmp_path: Path) -> None:
    tasks = write_csv(tmp_path / "tasks.csv", [task(participant_id="UNKNOWN")])
    output = tmp_path / "bundle"
    with pytest.raises(ValueError, match="对应"):
        prepare(ROOT / "evaluation/datasets/user_study.example.csv", output, tasks)
    assert not output.exists()
    with pytest.raises(ValueError, match="示例"):
        prepare(ROOT / "evaluation/datasets/user_study.example.csv", output, sample_kind="real")
    assert not output.exists()


def test_annotation_and_expert_csv_share_strict_shape_contract(tmp_path: Path) -> None:
    annotations = tmp_path / "annotations.csv"
    annotations.write_text(
        "item_id,annotator,answerable,expected_page\nq,A,1,1,extra\nq,B,1,1\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        analyze_annotations(annotations)
    expert = tmp_path / "expert.csv"
    expert.write_text(
        "case_id,dimension,model_score,expert_score,scoring_mode,sample_kind\nq,内容,80,80,llm,synthetic,extra\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        calibrate(expert)


def test_unanswerable_annotations_reject_free_text_and_normalize_missing_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "annotations.csv"
    path.write_text(
        "item_id,annotator,answerable,expected_page\nq,A,0,private text\nq,B,0,NA\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="原文"):
        analyze_annotations(path)
    path.write_text(
        "item_id,annotator,answerable,expected_page\nq,A,0,\nq,B,0,NA\n", encoding="utf-8"
    )
    assert analyze_annotations(path)["raw_agreement"] == 1


def test_synthetic_export_also_rejects_identity_in_discipline_field(tmp_path: Path) -> None:
    with (ROOT / "evaluation/datasets/user_study.example.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["discipline_code"] = "张三"
    path = write_csv(tmp_path / "study.csv", rows)
    with pytest.raises(ValueError, match="匿名"):
        prepare(path, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_snapshot_changes_with_source_but_excludes_runtime_secrets(tmp_path: Path) -> None:
    source = tmp_path / "filemate"
    source.mkdir()
    (source / "probe.py").write_text("value = 1\n", encoding="utf-8")
    first = rc.snapshot(tmp_path)
    (source / ".env").write_text("SYNTHETIC_TEST_SECRET=hidden", encoding="utf-8")
    (source / "private.db").write_bytes(b"synthetic-not-real")
    assert rc.snapshot(tmp_path)["source_fingerprint"] == first["source_fingerprint"]
    (source / "probe.py").write_text("value = 2\n", encoding="utf-8")
    assert rc.snapshot(tmp_path)["source_fingerprint"] != first["source_fingerprint"]


def test_rc_engineering_pass_never_promotes_synthetic_to_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rc, "snapshot", lambda: {"source_fingerprint": "code"})
    baseline, gate, browser, synthetic = [
        tmp_path / name for name in ("baseline.json", "gate.log", "browser.json", "synthetic.json")
    ]
    baseline.write_text('{"source_fingerprint":"code"}', encoding="utf-8")
    gate.write_text(
        "All checks passed!\n700 passed, 18 skipped, 5 deselected\npass 15\nfail 0\nbuilt in 30s",
        encoding="utf-8",
    )
    browser.write_text(
        '{"passed":true,"cases":[{"name":"b2","passed":true,"exit_code":0}]}', encoding="utf-8"
    )
    synthetic.write_text(
        '{"sample_kind":"synthetic","status":"passed","model_calls":20,"checks":[{"passed":true}]}',
        encoding="utf-8",
    )
    report = rc.readiness(baseline, gate, browser, synthetic)
    assert report["engineering_status"] == "passed"
    assert report["real_study"]["participant_count"] == 0
    assert report["expert_calibration"]["real_expert_pairs"] == 0
    assert report["status"] == "pending_team_release_review"
    assert report["gate"]["frontend_passed"] == 15
    baseline.write_text('{"source_fingerprint":"stale"}', encoding="utf-8")
    assert (
        rc.readiness(baseline, gate, browser, synthetic)["engineering_status"]
        == "pending_or_failed"
    )
