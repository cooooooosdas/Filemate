"""分析 FileMate 导出的匿名产品反馈 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def wilson_interval(positive: int, total: int) -> tuple[float, float]:
    """计算 95% Wilson 置信区间。"""
    if total == 0:
        return 0.0, 0.0
    z = 1.96
    rate = positive / total
    denominator = 1 + z**2 / total
    centre = rate + z**2 / (2 * total)
    margin = z * math.sqrt((rate * (1 - rate) + z**2 / (4 * total)) / total)
    return (centre - margin) / denominator, (centre + margin) / denominator


def analyze(
    rows: list[dict[str, str]],
    sample_kind: str = "synthetic",
) -> dict[str, Any]:
    """汇总总体与分功能区反馈。"""
    grouped: dict[str, list[int]] = defaultdict(list)
    unique_targets: set[str] = set()
    for row in rows:
        rating = int(row["rating"])
        if rating not in {-1, 1}:
            raise ValueError("rating 必须为 -1 或 1")
        grouped[row["area"]].append(rating)
        unique_targets.add(row["target_hash"])

    def summarize(ratings: list[int]) -> dict[str, Any]:
        total = len(ratings)
        positive = sum(rating == 1 for rating in ratings)
        low, high = wilson_interval(positive, total)
        return {
            "total": total,
            "positive": positive,
            "positive_rate": round(positive / total, 4) if total else 0.0,
            "wilson_95": [round(low, 4), round(high, 4)],
        }

    all_ratings = [rating for ratings in grouped.values() for rating in ratings]
    return {
        "sample_type": "anonymous_product_feedback",
        "sample_kind": sample_kind,
        "unique_targets": len(unique_targets),
        "overall": summarize(all_ratings),
        "by_area": {area: summarize(ratings) for area, ratings in sorted(grouped.items())},
    }


def main() -> None:
    """读取匿名 CSV 并输出 JSON 报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--sample-kind",
        choices=("synthetic", "real"),
        default="synthetic",
    )
    args = parser.parse_args()
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        report = analyze(list(csv.DictReader(handle)), sample_kind=args.sample_kind)
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content + "\n", encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
