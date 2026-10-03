"""汇总多 Agent、多模态面试与学习伙伴对照实验。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.csv_contract import (
    METADATA,
    anonymous_id,
    provenance,
    read_rows,
    validate_kind,
    validate_metadata,
)
from evaluation.intervals import mean_interval


def _read_rows(
    path: Path, required: set[str], sample_kind: str = "synthetic"
) -> list[dict[str, str]]:
    validate_kind(path, sample_kind)
    rows = read_rows(
        path, required | (METADATA if sample_kind == "real" else set()), required | METADATA
    )
    validate_metadata(rows, sample_kind)
    seen: set[tuple[str, ...]] = set()
    conditions: dict[str, str] = {}
    record_field = (
        "task_id" if "task_id" in required else "attempt_id" if "attempt_id" in required else None
    )
    for row in rows:
        identifiers = [row["participant_id"], row["condition"]] + (
            [row[record_field]] if record_field else []
        )
        if not all(anonymous_id(value) for value in identifiers):
            raise ValueError("参与者、条件与任务需使用短匿名编号")
        participant = row["participant_id"]
        if participant in conditions and conditions[participant] != row["condition"]:
            raise ValueError("平行对照设计中同一参与者不能跨条件重复计数")
        conditions[participant] = row["condition"]
        identity = tuple(identifiers)
        if identity in seen:
            raise ValueError("重复参与者任务或记录，不能重复计入样本")
        seen.add(identity)
        for field in required - {"participant_id", "condition", "task_id", "attempt_id"}:
            _number(row, field)
        if "hallucination_count" in row and _number(row, "hallucination_count") > _number(
            row, "reviewed_claim_count"
        ):
            raise ValueError("幻觉数量不能超过已审核断言数量")
        if "completed_tasks" in row and (
            _number(row, "completed_tasks") > _number(row, "assigned_tasks")
            or _number(row, "completed_reviews") > _number(row, "due_reviews")
        ):
            raise ValueError("完成数量不能超过分配任务或到期复习数量")
    return rows


def _participant_interval(items: list[dict[str, str]], field: str, unit: str) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in items:
        grouped[row["participant_id"]].append(_number(row, field))
    return mean_interval([fmean(values) for values in grouped.values()], unit)


def _number(row: dict[str, str], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"字段 {field} 必须是数字") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"字段 {field} 必须是有限非负数字")
    if field in {"completed", "returned_next_day"} and value not in {0, 1}:
        raise ValueError(f"字段 {field} 必须为0或1")
    if field in {"system_score", "expert_score_a", "expert_score_b"} and value > 100:
        raise ValueError(f"字段 {field} 不能超过100")
    if (
        field
        in {
            "hallucination_count",
            "reviewed_claim_count",
            "model_calls",
            "long_pause_count",
            "assigned_tasks",
            "completed_tasks",
            "due_reviews",
            "completed_reviews",
        }
        and not value.is_integer()
    ):
        raise ValueError(f"字段 {field} 必须是整数计数")
    return value


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) != len(left):
        return None
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum(
        (first - left_mean) * (second - right_mean)
        for first, second in zip(left, right, strict=True)
    )
    left_scale = math.sqrt(sum((item - left_mean) ** 2 for item in left))
    right_scale = math.sqrt(sum((item - right_mean) ** 2 for item in right))
    if not left_scale or not right_scale:
        return None
    return round(numerator / (left_scale * right_scale), 4)


def _study_status(groups: dict[str, list[dict[str, str]]], sample_kind: str) -> dict[str, Any]:
    counts = {
        condition: len({row["participant_id"] for row in rows})
        for condition, rows in groups.items()
    }
    sufficient = len(groups) >= 2 and all(count >= 15 for count in counts.values())
    return {
        "status": "real_sample_ready_for_review"
        if sufficient and sample_kind == "real"
        else "synthetic_pipeline_only"
        if sufficient
        else "pending_more_samples",
        "sample_kind": sample_kind,
        "participant_count_by_condition": counts,
        "minimum_required": "至少两个条件，每个条件 15 名匿名参与者",
    }


def analyze_agent_trials(path: Path, sample_kind: str = "synthetic") -> dict[str, Any]:
    """比较单 Agent 与按需多 Agent 的任务结果。"""
    required = {
        "participant_id",
        "task_id",
        "condition",
        "completed",
        "hallucination_count",
        "reviewed_claim_count",
        "elapsed_seconds",
        "model_calls",
        "estimated_cost_yuan",
    }
    rows = _read_rows(path, required, sample_kind)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    metrics = {}
    for condition, items in groups.items():
        reviewed = sum(_number(item, "reviewed_claim_count") for item in items)
        hallucinations = sum(_number(item, "hallucination_count") for item in items)
        metrics[condition] = {
            "trial_count": len(items),
            "confidence_intervals": {
                "participant_mean_completion": _participant_interval(
                    items, "completed", "proportion"
                ),
                "participant_mean_elapsed_seconds": _participant_interval(
                    items, "elapsed_seconds", "seconds"
                ),
            },
            "task_completion_rate": round(fmean(_number(item, "completed") for item in items), 4),
            "hallucination_rate": round(hallucinations / reviewed, 4) if reviewed else None,
            "mean_elapsed_seconds": round(
                fmean(_number(item, "elapsed_seconds") for item in items), 2
            ),
            "mean_model_calls": round(fmean(_number(item, "model_calls") for item in items), 2),
            "mean_estimated_cost_yuan": round(
                fmean(_number(item, "estimated_cost_yuan") for item in items), 4
            ),
        }
    return {
        **_study_status(groups, sample_kind),
        "conditions": metrics,
        "provenance": provenance(path, rows, sample_kind),
        "notice": "区间按独立参与者重采样；任务均值与参与者均值权重可能不同，仅供探索，不作效果或因果结论。",
    }


def analyze_interview_trials(path: Path, sample_kind: str = "synthetic") -> dict[str, Any]:
    """比较文字与多模态面试，并检查系统分与导师盲评分相关性。"""
    required = {
        "participant_id",
        "attempt_id",
        "condition",
        "completed",
        "system_score",
        "expert_score_a",
        "expert_score_b",
        "words_per_minute",
        "long_pause_count",
    }
    rows = _read_rows(path, required, sample_kind)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    metrics = {}
    for condition, items in groups.items():
        system_scores = [_number(item, "system_score") for item in items]
        expert_scores = [
            (_number(item, "expert_score_a") + _number(item, "expert_score_b")) / 2
            for item in items
        ]
        metrics[condition] = {
            "trial_count": len(items),
            "confidence_intervals": {
                "participant_mean_completion": _participant_interval(
                    items, "completed", "proportion"
                ),
                "participant_mean_system_score": _participant_interval(
                    items, "system_score", "score_points_0_100"
                ),
            },
            "completion_rate": round(fmean(_number(item, "completed") for item in items), 4),
            "mean_expert_score": round(fmean(expert_scores), 2),
            "system_expert_mae": round(
                fmean(
                    abs(system - expert)
                    for system, expert in zip(system_scores, expert_scores, strict=True)
                ),
                2,
            ),
            "system_expert_correlation": _correlation(system_scores, expert_scores),
            "mean_words_per_minute": round(
                fmean(_number(item, "words_per_minute") for item in items), 2
            ),
            "mean_long_pause_count": round(
                fmean(_number(item, "long_pause_count") for item in items), 2
            ),
        }
    return {
        **_study_status(groups, sample_kind),
        "conditions": metrics,
        "provenance": provenance(path, rows, sample_kind),
        "notice": "区间按独立参与者重采样；任务均值与参与者均值权重可能不同，仅供探索，不作效果或因果结论。",
    }


def analyze_companion_trials(path: Path, sample_kind: str = "synthetic") -> dict[str, Any]:
    """比较普通提醒与学习伙伴反馈的执行和次日返回。"""
    required = {
        "participant_id",
        "condition",
        "assigned_tasks",
        "completed_tasks",
        "due_reviews",
        "completed_reviews",
        "returned_next_day",
    }
    rows = _read_rows(path, required, sample_kind)
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    metrics = {}
    for condition, items in groups.items():
        assigned = sum(_number(item, "assigned_tasks") for item in items)
        completed = sum(_number(item, "completed_tasks") for item in items)
        due = sum(_number(item, "due_reviews") for item in items)
        reviewed = sum(_number(item, "completed_reviews") for item in items)
        metrics[condition] = {
            "participant_count": len({item["participant_id"] for item in items}),
            "confidence_intervals": {
                "next_day_return": _participant_interval(items, "returned_next_day", "proportion")
            },
            "task_completion_rate": round(completed / assigned, 4) if assigned else None,
            "due_review_completion_rate": round(reviewed / due, 4) if due else None,
            "next_day_return_rate": round(
                fmean(_number(item, "returned_next_day") for item in items), 4
            ),
        }
    return {
        **_study_status(groups, sample_kind),
        "conditions": metrics,
        "provenance": provenance(path, rows, sample_kind),
        "notice": "区间按独立参与者重采样；任务均值与参与者均值权重可能不同，仅供探索，不作效果或因果结论。",
    }


def main() -> None:
    """生成机器可读竞赛实验报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--interview", type=Path, required=True)
    parser.add_argument("--companion", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-kind", choices=("synthetic", "real"), default="synthetic")
    parser.add_argument("--consent-confirmed", action="store_true")
    args = parser.parse_args()
    if args.sample_kind == "real":
        if not args.consent_confirmed:
            parser.error("真实对照实验需 --consent-confirmed 确认已完成匿名化与知情同意")
        if any(
            any(marker in path.name.lower() for marker in (".example", ".template", ".synthetic"))
            for path in (args.agent, args.interview, args.companion)
        ):
            parser.error("示例或模板不能标记为真实对照实验")
    report = {
        "data_kind": "real_anonymous_user_trial"
        if args.sample_kind == "real"
        else "synthetic_pipeline_only",
        "sample_kind": args.sample_kind,
        "agent_ab": analyze_agent_trials(args.agent, args.sample_kind),
        "interview_ab": analyze_interview_trials(args.interview, args.sample_kind),
        "companion_ab": analyze_companion_trials(args.companion, args.sample_kind),
        "notice": "样本门槛未达到时只能标记为待评测，不得形成效果结论。",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
