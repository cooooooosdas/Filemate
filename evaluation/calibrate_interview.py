"""校验匿名配对评分并计算Spearman相关，不生成导师样本。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.csv_contract import anonymous_id, read_rows, validate_kind

DIMENSIONS = {"内容", "结构", "表达", "岗位匹配"}
FIELDS = {"case_id", "dimension", "model_score", "expert_score", "scoring_mode", "sample_kind"}


def ranks(values: list[float]) -> list[float]:
    """返回处理并列值的平均名次。"""
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    index = 0
    while index < len(values):
        end = index + 1
        while end < len(values) and values[ordered[end]] == values[ordered[index]]:
            end += 1
        rank = (index + 1 + end) / 2
        for position in ordered[index:end]:
            result[position] = rank
        index = end
    return result


def spearman(left: list[float], right: list[float]) -> float | None:
    """计算配对名次相关；常数评分不能得出相关性。"""
    x, y = ranks(left), ranks(right)
    mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
    denominator = math.sqrt(sum((v - mean_x) ** 2 for v in x) * sum((v - mean_y) ** 2 for v in y))
    return (
        round(sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / denominator, 4)
        if denominator
        else None
    )


def calibrate(path: Path) -> dict:
    """只读验证CSV，按明确样本类型分别计算参考相关。"""
    rows = read_rows(path, FIELDS, FIELDS, allow_empty=True)
    seen, groups = set(), {}
    for row in rows:
        if not anonymous_id(row["case_id"]):
            raise ValueError("case_id需为不含身份的短匿名编号")
        if row["dimension"] not in DIMENSIONS or row["scoring_mode"] != "llm":
            raise ValueError("只接受内容/结构/表达/岗位匹配的实际模型评分")
        if row["sample_kind"] not in {"expert_real", "synthetic"}:
            raise ValueError("样本类型需明确标为expert_real或synthetic")
        if row["sample_kind"] == "expert_real":
            validate_kind(path, "real")
        identity = (row["case_id"], row["dimension"], row["sample_kind"])
        if identity in seen:
            raise ValueError("匿名案例维度重复")
        seen.add(identity)
        model, expert = float(row["model_score"]), float(row["expert_score"])
        if not all(math.isfinite(v) and 0 <= v <= 100 for v in (model, expert)):
            raise ValueError("评分需为0到100的有限数字")
        groups.setdefault((row["sample_kind"], row["dimension"]), []).append((model, expert))
    comparisons = []
    for (kind, dimension), pairs in sorted(groups.items()):
        correlation = (
            spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 5 else None
        )
        comparisons.append(
            {
                "sample_kind": kind,
                "dimension": dimension,
                "paired_count": len(pairs),
                "spearman": correlation,
                "status": "参考相关" if correlation is not None else "待校准",
            }
        )
    return {
        "real_expert_pairs": sum(r["sample_kind"] == "expert_real" for r in rows),
        "synthetic_pairs": sum(r["sample_kind"] == "synthetic" for r in rows),
        "status": "存在实际专家配对，按维度查看样本量"
        if any(r["sample_kind"] == "expert_real" for r in rows)
        else "真实专家校准待评测",
        "comparisons": comparisons,
        "note": "相关性不等于评分准确率；每维度至少5个配对才计算，合成数据独立标记。",
    }


def main():
    """从用户提供的匿名CSV输出校准报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(calibrate(args.input), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
