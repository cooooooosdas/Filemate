"""日历 .ics 生成测试。TODO(徐书和 + 胡希)"""
from __future__ import annotations

import pytest

pytest.importorskip("icalendar")  # icalendar 为可选依赖，缺失则整文件 skip

from filemate.execution.scheduler import CalendarBuilder, CalendarEvent


@pytest.fixture()
def builder() -> CalendarBuilder:
    return CalendarBuilder()


class TestCalendarBuilder:
    def test_single_event(self, builder: CalendarBuilder, tmp_path: Path) -> None:
        events = [CalendarEvent(summary="实验三截止", start="2026-04-15", location="线上")]
        out = builder.save(events, tmp_path / "test.ics")
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "实验三截止" in content

    def test_multi_event(self, builder: CalendarBuilder, tmp_path: Path) -> None:
        events = [
            CalendarEvent(summary="初赛", start="2026-05-01"),
            CalendarEvent(summary="决赛", start="2026-06-01"),
        ]
        out = builder.save(events, tmp_path / "multi.ics")
        content = out.read_text(encoding="utf-8")
        assert content.count("BEGIN:VEVENT") == 2
        assert "初赛" in content
        assert "决赛" in content

    def test_datetime_format(self, builder: CalendarBuilder, tmp_path: Path) -> None:
        events = [CalendarEvent(summary="测试", start="2026-04-15T14:30")]
        out = builder.save(events, tmp_path / "dt.ics")
        content = out.read_text(encoding="utf-8")
        # DTSTART 应为 20260415T143000
        assert "20260415T143000" in content

    def test_default_end_is_one_hour(self, builder: CalendarBuilder, tmp_path: Path) -> None:
        events = [CalendarEvent(summary="测试", start="2026-04-15T09:00")]
        out = builder.save(events, tmp_path / "end.ics")
        content = out.read_text(encoding="utf-8")
        assert "20260415T100000" in content

    def test_location_and_description(self, builder: CalendarBuilder, tmp_path: Path) -> None:
        events = [CalendarEvent(
            summary="考试", start="2026-07-20", location="教三楼 301", description="闭卷",
        )]
        out = builder.save(events, tmp_path / "loc.ics")
        content = out.read_text(encoding="utf-8")
        assert "教三楼 301" in content
        assert "闭卷" in content

    def test_build_returns_bytes(self, builder: CalendarBuilder) -> None:
        data = builder.build([CalendarEvent("x", "2026-01-01")])
        assert isinstance(data, bytes)
        assert b"BEGIN:VCALENDAR" in data

    def test_icalendar_required(self) -> None:
        """icalendar 未安装时 build() 会 RuntimeError（测试环境可能缺依赖，skip 即可）。"""
        pytest.importorskip("icalendar")
