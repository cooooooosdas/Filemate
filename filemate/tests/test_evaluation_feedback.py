"""匿名产品反馈统计测试。"""

from __future__ import annotations

import pytest

from evaluation.analyze_feedback import analyze


def test_analyze_feedback_reports_sample_kind_and_interval() -> None:
    report = analyze(
        [
            {"area": "retrieval", "target_hash": "a", "rating": "1"},
            {"area": "retrieval", "target_hash": "b", "rating": "-1"},
            {"area": "tutor", "target_hash": "c", "rating": "1"},
        ],
        sample_kind="real",
    )

    assert report["sample_kind"] == "real"
    assert report["unique_targets"] == 3
    assert report["overall"]["positive_rate"] == 0.6667
    low, high = report["overall"]["wilson_95"]
    assert 0 < low < high < 1


def test_analyze_feedback_rejects_invalid_rating() -> None:
    with pytest.raises(ValueError, match="-1 或 1"):
        analyze([{"area": "retrieval", "target_hash": "a", "rating": "0"}])
