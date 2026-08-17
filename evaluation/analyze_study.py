"""分析双人标注一致性与匿名用户前后测。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean, stdev
from typing import Any


def analyze_annotations(path: Path) -> dict[str, Any]:
    """计算两名标注者的原始一致率与 Cohen's Kappa。"""
    grouped: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            label = f"{row['answerable']}:{row['expected_page']}"
            grouped[row["item_id"]].append(label)
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
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    return {
        "paired_item_count": len(pairs),
        "raw_agreement": round(observed, 4),
        "cohen_kappa": round(kappa, 4),
        "disagreement_items": [
            item_id
            for item_id, labels in grouped.items()
            if len(labels) == 2 and labels[0] != labels[1]
        ],
    }


def _effect_size(differences: list[float]) -> float:
    if len(differences) < 2:
        return 0.0
    deviation = stdev(differences)
    return fmean(differences) / deviation if deviation else 0.0


def analyze_user_study(path: Path) -> dict[str, Any]:
    """计算正确率、用时、配对效应量与 SUS。"""
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("用户研究数据为空")
    score_deltas = [float(row["post_correct"]) - float(row["pre_correct"]) for row in rows]
    time_deltas = [float(row["pre_minutes"]) - float(row["post_minutes"]) for row in rows]
    sus_scores = []
    for row in rows:
        adjusted = []
        for index in range(1, 11):
            response = float(row[f"sus_q{index}"])
            adjusted.append(response - 1 if index % 2 else 5 - response)
        sus_scores.append(sum(adjusted) * 2.5)
    return {
        "participant_count": len(rows),
        "mean_pre_correct": round(fmean(float(row["pre_correct"]) for row in rows), 3),
        "mean_post_correct": round(fmean(float(row["post_correct"]) for row in rows), 3),
        "mean_score_gain": round(fmean(score_deltas), 3),
        "score_gain_cohen_dz": round(_effect_size(score_deltas), 3),
        "mean_minutes_saved": round(fmean(time_deltas), 3),
        "time_saved_cohen_dz": round(_effect_size(time_deltas), 3),
        "mean_sus": round(fmean(sus_scores), 3),
    }


def main() -> None:
    """输出机器可读用户研究统计。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "annotations": analyze_annotations(args.annotations),
        "user_study": analyze_user_study(args.study),
        "notice": "输入为合成示例时，结果仅用于验证分析流程。",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
