"""多里程碑识别模块单元测试。

全部用 _Stub 假 LLM，不产生真实 API 调用，CI 可直接跑。
"""
from __future__ import annotations

import pytest

from filemate.understanding.milestone_detector import MilestoneDetector


class _Stub:
    """可配置的假 LLM 客户端。"""

    def __init__(self, payload=None, raises: Exception | None = None) -> None:
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def call_structured(self, prompt="", messages=None, **kw):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.payload

    def call(self, prompt="", messages=None, **kw):
        return ""


class TestMilestoneDetectorEmptyText:
    """空文本直接返回空列表，不调用 LLM。"""

    @pytest.mark.parametrize("text", ["", "   ", "\n"])
    def test_empty_text_returns_empty_list(self, text: str) -> None:
        stub = _Stub(payload=[{"event": "报名截止", "date": "2026-08-01", "order": 1}])
        result = MilestoneDetector(stub).detect(text)

        assert result == []
        assert stub.calls == 0, "空文本不该触发 LLM 调用"


class TestMilestoneDetectorNormal:
    """正常识别。"""

    def test_returns_event_list(self) -> None:
        payload = [
            {"event": "报名截止", "date": "2026-08-01", "order": 1},
            {"event": "初赛", "date": "2026-08-15", "order": 2},
            {"event": "决赛", "date": "2026-09-10", "order": 3},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("竞赛通知正文")

        assert len(result) == 3
        assert [m["event"] for m in result] == ["报名截止", "初赛", "决赛"]
        for m in result:
            assert set(m) == {"event", "date", "order"}

    def test_sorted_and_renumbered(self) -> None:
        """乱序 order 应排序后强制重排为连续序号。"""
        payload = [
            {"event": "决赛", "date": "2026-09-10", "order": 7},
            {"event": "报名截止", "date": "2026-08-01", "order": 2},
            {"event": "初赛", "date": "2026-08-15", "order": 5},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert [m["order"] for m in result] == [1, 2, 3]
        assert [m["event"] for m in result] == ["报名截止", "初赛", "决赛"]

    def test_whitespace_stripped(self) -> None:
        payload = [{"event": "  报名截止  ", "date": " 2026-08-01 ", "order": 1}]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert result[0]["event"] == "报名截止"
        assert result[0]["date"] == "2026-08-01"


class TestMilestoneDetectorDedup:
    """去重键是 (event, date)，不是单独的 date。"""

    def test_same_date_different_events_both_kept(self) -> None:
        """同一天的多个不同节点都要保留 —— 竞赛通知里很常见。"""
        payload = [
            {"event": "报名截止", "date": "2026-08-01", "order": 1},
            {"event": "初赛开始", "date": "2026-08-01", "order": 2},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert len(result) == 2, "同日不同事件不应被去重"
        assert {m["event"] for m in result} == {"报名截止", "初赛开始"}

    def test_exact_duplicate_removed(self) -> None:
        payload = [
            {"event": "报名截止", "date": "2026-08-01", "order": 1},
            {"event": "报名截止", "date": "2026-08-01", "order": 2},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert len(result) == 1, "完全重复的条目应去重"


class TestMilestoneDetectorFiltering:
    """无效条目被丢弃。"""

    @pytest.mark.parametrize(
        "bad_date",
        ["下周五", "2026/08/01", "8月1日", "2026-8-1", "待定", ""],
    )
    def test_invalid_date_dropped(self, bad_date: str) -> None:
        payload = [{"event": "报名截止", "date": bad_date, "order": 1}]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")
        assert result == [], f"非法日期 {bad_date!r} 的条目应被丢弃"

    def test_empty_event_dropped(self) -> None:
        payload = [
            {"event": "", "date": "2026-08-01", "order": 1},
            {"event": "初赛", "date": "2026-08-15", "order": 2},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert len(result) == 1
        assert result[0]["event"] == "初赛"

    def test_mixed_valid_invalid(self) -> None:
        payload = [
            {"event": "报名截止", "date": "2026-08-01", "order": 1},
            {"event": "初赛", "date": "待定", "order": 2},
            {"event": "决赛", "date": "2026-09-10", "order": 3},
        ]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert [m["event"] for m in result] == ["报名截止", "决赛"]
        assert [m["order"] for m in result] == [1, 2], "过滤后 order 应重排连续"

    @pytest.mark.parametrize("bad_order", ["第一", None, "", {}])
    def test_invalid_order_falls_back_to_index(self, bad_order) -> None:
        """order 非数字时退回下标，不应让整批里程碑丢失。"""
        payload = [{"event": "报名截止", "date": "2026-08-01", "order": bad_order}]
        result = MilestoneDetector(_Stub(payload=payload)).detect("正文")

        assert len(result) == 1, f"order={bad_order!r} 不该导致整批丢弃"
        assert result[0]["order"] == 1


class TestMilestoneDetectorFailure:
    """LLM 异常/返回非数组时的兜底。"""

    @pytest.mark.parametrize("bad_payload", [{"event": "报名"}, None, "字符串", 42])
    def test_non_list_payload_returns_empty(self, bad_payload) -> None:
        stub = _Stub(payload=bad_payload)
        result = MilestoneDetector(stub).detect("正文")

        assert result == []
        assert stub.calls == 2, "非数组返回应触发重试"

    def test_exception_returns_empty_after_retry(self) -> None:
        stub = _Stub(raises=RuntimeError("API 超时"))
        result = MilestoneDetector(stub).detect("正文")

        assert result == []
        assert stub.calls == 2, "应重试一次（共 2 次尝试）"
