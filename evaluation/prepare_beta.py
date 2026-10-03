"""先完整校验匿名 Beta 数据，再导出可追溯采集包。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.analyze_competition_trials import analyze_agent_trials
from evaluation.analyze_study import analyze_user_study
from evaluation.csv_contract import read_rows


def prepare(
    study: Path, output: Path, tasks: Path | None = None, sample_kind: str = "synthetic"
) -> dict[str, Any]:
    """拒绝不完整、混合或不一致输入，保留来源字节指纹。"""
    if output.exists():
        raise ValueError("输出目录已存在；请使用新目录，禁止覆盖采集包")
    paths = [study] + ([tasks] if tasks else [])
    fingerprints = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    study_report = analyze_user_study(study, sample_kind)
    study_fields = {
        "participant_id",
        "condition",
        "pre_correct",
        "post_correct",
        "score_max",
        "pre_minutes",
        "post_minutes",
        "study_date",
        "consent_confirmed",
        "discipline_code",
        "sample_kind",
    } | {f"sus_q{i}" for i in range(1, 11)}
    study_rows = read_rows(study, {"participant_id", "condition"}, study_fields)
    task_report, task_rows = None, []
    task_fields = {
        "participant_id",
        "task_id",
        "condition",
        "completed",
        "hallucination_count",
        "reviewed_claim_count",
        "elapsed_seconds",
        "model_calls",
        "estimated_cost_yuan",
        "study_date",
        "consent_confirmed",
        "sample_kind",
    }
    if tasks:
        task_report = analyze_agent_trials(tasks, sample_kind)
        task_rows = read_rows(tasks, {"participant_id", "task_id", "condition"}, task_fields)
        participants = {(row["participant_id"], row["condition"]) for row in study_rows}
        if any((row["participant_id"], row["condition"]) not in participants for row in task_rows):
            raise ValueError("任务参与者和条件必须能对应前后测采集表")
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != fingerprints[path] for path in paths):
        raise ValueError("输入在验证期间变化，停止导出")
    for row in study_rows + task_rows:
        row["sample_kind"] = sample_kind
    report = {
        "sample_kind": sample_kind,
        "user_study": study_report,
        "anonymous_tasks": task_report,
        "notice": "匿名编号格式和同意声明校验不能替代团队核实招募、知情同意与真实性。合成输入只验证流水线。",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)

    def export(name: str, rows: list[dict[str, str]]) -> None:
        fields = sorted({field for row in rows for field in row})
        with (output / name).open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(
                sorted(rows, key=lambda row: (row["participant_id"], row.get("task_id", "")))
            )

    export("user_study.csv", study_rows)
    if tasks:
        export("anonymous_tasks.csv", task_rows)
    (output / "report.json").write_text(rendered, encoding="utf-8")
    return report


def main() -> None:
    """默认合成，输出目录已存在时停止。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-kind", choices=("synthetic", "real"), default="synthetic")
    args = parser.parse_args()
    try:
        report = prepare(args.study, args.output, args.tasks, args.sample_kind)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "sample_kind": report["sample_kind"],
                "participant_count": report["user_study"]["participant_count"],
                "status": report["user_study"]["status"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
