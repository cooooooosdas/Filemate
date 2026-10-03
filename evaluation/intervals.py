"""对独立参与者的配对变化给出可复现的探索性置信区间。"""

from __future__ import annotations

import math
import random
from statistics import fmean
from typing import Any


def mean_interval(values: list[float], unit: str) -> dict[str, Any]:
    """计算固定种子的 95% percentile bootstrap 均值区间。"""
    if any(not math.isfinite(value) for value in values):
        raise ValueError("区间输入必须是有限数字")
    result: dict[str, Any] = {
        "sample_count": len(values),
        "sample_unit": "independent_participant",
        "unit": unit,
        "confidence_level": 0.95,
        "method": "percentile_bootstrap_mean",
        "resamples": 2000,
        "seed": 42,
        "lower": None,
        "upper": None,
        "status": "insufficient_samples",
    }
    if len(values) < 2:
        return result
    rng = random.Random(42)
    means = sorted(fmean(rng.choices(values, k=len(values))) for _ in range(2000))

    def quantile(fraction: float) -> float:
        position = fraction * (len(means) - 1)
        left = int(position)
        return means[left] + (means[min(left + 1, len(means) - 1)] - means[left]) * (
            position - left
        )

    result.update(
        lower=round(quantile(0.025), 6),
        upper=round(quantile(0.975), 6),
        status="zero_observed_variance" if len(set(values)) == 1 else "exploratory_only",
    )
    return result
