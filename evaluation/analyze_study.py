"""分析双人标注一致性与匿名用户前后测。"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, stdev
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.csv_contract import (
    METADATA,
    provenance,
    read_rows,
    validate_kind,
    validate_metadata,
)
from evaluation.intervals import mean_interval


def analyze_annotations(path: Path, sample_kind: str = "synthetic") -> dict[str, Any]:
    """计算两名标注者的原始一致率与 Cohen's Kappa。"""
    grouped: dict[str, list[str]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    validate_kind(path, sample_kind)
    required = {"item_id", "annotator", "answerable", "expected_page"}
    rows = read_rows(path, required - {"expected_page"}, required | METADATA)
    if any("expected_page" not in row for row in rows):
        raise ValueError("标注表缺少 expected_page")
    validate_metadata(rows, sample_kind)
    for row in rows:
        identity = (row["item_id"], row["annotator"])
        if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value or "") for value in identity):
            raise ValueError("题目和标注者需使用短匿名编号")
        if identity in seen:
            raise ValueError("同一标注者重复标注同一题，不能视为独立双人标注")
        seen.add(identity)
        if row["answerable"] not in {"0", "1"}:
            raise ValueError("answerable 必须为0或1")
        if row["answerable"] == "1" and not re.fullmatch(
            r"[1-9][0-9]*", row["expected_page"] or ""
        ):
            raise ValueError("可回答题目需提供有效引用页码")
        if row["answerable"] == "0" and row["expected_page"] not in {"", "NA", "0"}:
            raise ValueError("不可回答题目的页码只接受空值、NA或0，不能加入原文")
        label = f"1:{row['expected_page']}" if row["answerable"] == "1" else "0:NA"
        grouped[row["item_id"]].append(label)
    if any(len(labels) != 2 for labels in grouped.values()):
        raise ValueError("每题必须恰有两名独立标注者")
    pairs = [labels for labels in grouped.values() if len(labels) == 2]
    if not pairs:
        raise ValueError("没有找到每题两名标注者的数据")
    observed = sum(first == second for first, second in pairs) / len(pairs)
    first_counts = Counter(first for first, _ in pairs)
    second_counts = Counter(second for _, second in pairs)
    expected = sum(
        first_counts[label] / len(pairs) * second_counts[label] / len(pairs)
        for label in set(first_counts) | set(second_counts)
    )
    kappa = (observed - expected) / (1 - expected) if expected < 1 else None
    return {
        "sample_kind": sample_kind,
        "provenance": provenance(path, rows, sample_kind),
        "paired_item_count": len(pairs),
        "raw_agreement": round(observed, 4),
        "cohen_kappa": round(kappa, 4) if kappa is not None else None,
        "disagreement_items": [
            item_id
            for item_id, labels in grouped.items()
            if len(labels) == 2 and labels[0] != labels[1]
        ],
    }


def _effect_size(differences: list[float]) -> float | None:
    if len(differences) < 2:
        return None
    deviation = stdev(differences)
    return round(fmean(differences) / deviation, 3) if deviation else None


def analyze_user_study(path: Path, sample_kind: str = "synthetic") -> dict[str, Any]:
    """验证匿名前后测并按条件报告观察性统计，不推断因果效果。"""
    validate_kind(path, sample_kind)
    required = {
        "participant_id",
        "condition",
        "pre_correct",
        "post_correct",
        "pre_minutes",
        "post_minutes",
    } | {f"sus_q{i}" for i in range(1, 11)}
    allowed = required | {"score_max", "discipline_code"} | METADATA
    if sample_kind == "real":
        required |= {
            "score_max",
            "study_date",
            "consent_confirmed",
            "discipline_code",
            "sample_kind",
        }
    rows = read_rows(path, required, allowed)
    validate_metadata(rows, sample_kind)
    seen: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        participant, condition = row["participant_id"], row["condition"]
        if not all(
            re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value or "") for value in (participant, condition)
        ):
            raise ValueError("需提供匿名参与者编号和实验条件")
        if participant in seen:
            raise ValueError("参与者编号重复，不能重复计入独立样本量")
        seen.add(participant)
        if row.get("sample_kind") and row["sample_kind"] != sample_kind:
            raise ValueError("不能混合真实与合成数据")
        numeric = {
            field: float(row[field])
            for field in ["pre_correct", "post_correct", "pre_minutes", "post_minutes"]
        }
        if (
            not all(math.isfinite(value) and value >= 0 for value in numeric.values())
            or numeric["pre_minutes"] <= 0
        ):
            raise ValueError("得分和用时需为有限非负数字，前测用时须大于0")
        maximum = float(row["score_max"]) if row.get("score_max") else None
        if maximum is not None and (
            not math.isfinite(maximum)
            or maximum <= 0
            or max(numeric["pre_correct"], numeric["post_correct"]) > maximum
        ):
            raise ValueError("前后测得分不得超出 score_max")
        if (sample_kind == "real" or row.get("discipline_code")) and not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", row.get("discipline_code") or ""
        ):
            raise ValueError("专业代码需使用短匿名编号")
        adjusted: list[float] = []
        for index in range(1, 11):
            response = float(row[f"sus_q{index}"])
            if not math.isfinite(response) or not response.is_integer() or not 1 <= response <= 5:
                raise ValueError("SUS 各题需为1到5的整数")
            adjusted.append(response - 1 if index % 2 else 5 - response)
        groups[condition].append({**numeric, "score_max": maximum, "sus": sum(adjusted) * 2.5})

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        score_deltas = [row["post_correct"] - row["pre_correct"] for row in items]
        time_deltas = [row["pre_minutes"] - row["post_minutes"] for row in items]
        normalized = all(row["score_max"] is not None for row in items)
        pre = fmean(row["pre_correct"] / row["score_max"] for row in items) if normalized else None
        post = (
            fmean(row["post_correct"] / row["score_max"] for row in items) if normalized else None
        )
        gain = (post - pre) / pre * 100 if pre else None
        saved = fmean(time_deltas) / fmean(row["pre_minutes"] for row in items) * 100
        same_scale = len({row["score_max"] for row in items}) == 1
        intervals = {
            "minutes_saved": mean_interval(time_deltas, "minutes"),
            "sus": mean_interval([row["sus"] for row in items], "SUS_points_0_100"),
        }
        if normalized:
            intervals["score_gain"] = mean_interval(
                [
                    (row["post_correct"] - row["pre_correct"]) / row["score_max"] * 100
                    for row in items
                ],
                "percentage_points",
            )
        elif same_scale:
            intervals["score_gain"] = mean_interval(score_deltas, "raw_score_points")
        return {
            "participant_count": len(items),
            "confidence_intervals": intervals,
            "mean_pre_correct": round(fmean(row["pre_correct"] for row in items), 3)
            if same_scale
            else None,
            "mean_post_correct": round(fmean(row["post_correct"] for row in items), 3)
            if same_scale
            else None,
            "mean_score_gain": round(fmean(score_deltas), 3) if same_scale else None,
            "score_gain_cohen_dz": _effect_size(
                [(row["post_correct"] - row["pre_correct"]) / row["score_max"] for row in items]
            )
            if normalized
            else _effect_size(score_deltas)
            if same_scale
            else None,
            "mean_minutes_saved": round(fmean(time_deltas), 3),
            "time_saved_cohen_dz": _effect_size(time_deltas),
            "mean_sus": round(fmean(row["sus"] for row in items), 3),
            "mean_pre_correct_rate": round(pre, 4) if pre is not None else None,
            "mean_post_correct_rate": round(post, 4) if post is not None else None,
            "score_gain_percentage_points": round((post - pre) * 100, 3) if normalized else None,
            "relative_score_gain_percent": round(gain, 3) if gain is not None else None,
            "minutes_saved_percent": round(saved, 3),
        }

    metrics = {condition: summarize(items) for condition, items in sorted(groups.items())}
    disciplines = {row.get("discipline_code") for row in rows if row.get("discipline_code")}
    sufficient = (
        sample_kind == "real"
        and len(rows) >= 30
        and len(disciplines) >= 3
        and (len(groups) == 1 or all(len(items) >= 15 for items in groups.values()))
    )
    result = {
        "sample_kind": sample_kind,
        "participant_count": len(rows),
        "discipline_count": len(disciplines),
        "status": "real_sample_ready_for_review"
        if sufficient
        else "pending_more_samples"
        if sample_kind == "real"
        else "synthetic_pipeline_only",
        "provenance": provenance(path, rows, sample_kind),
        "by_condition": metrics,
        "notice": "前后测是观察性统计；样本达标不等于有效，更不能证明因果关系。无满分不报告正确率，零方差效应量为null。区间以参与者配对变化重采样，小样本与零方差区间仅供探索，不作显著性或因果结论。",
    }
    if len(metrics) == 1:
        result.update(next(iter(metrics.values())))
    return result


def main() -> None:
    """输出机器可读用户研究统计。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-kind", choices=("synthetic", "real"), default="synthetic")
    args = parser.parse_args()
    report = {
        "annotations": analyze_annotations(args.annotations, args.sample_kind),
        "user_study": analyze_user_study(args.study, args.sample_kind),
        "sample_kind": args.sample_kind,
        "notice": "输入为合成示例时，结果仅用于验证分析流程。",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
