"""日历 .ics 生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CalendarEvent:
    summary: str
    start: str  # ISO 8601
    end: str | None = None
    location: str = ""
    description: str = ""


class CalendarBuilder:
    """生成 .ics 日历文件。"""

    def build(self, events: list[CalendarEvent]) -> bytes:
        """TODO(徐书和): 使用 icalendar 库实现。"""
        raise NotImplementedError("TODO(徐书和): .ics 生成")

    def save(self, events: list[CalendarEvent], out_path: str | Path) -> Path:
        """TODO(徐书和): 写入 .ics 文件。"""
        raise NotImplementedError("TODO(徐书和)")
