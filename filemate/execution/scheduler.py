"""日历 .ics 生成。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    summary: str
    start: str  # ISO 8601  (YYYY-MM-DD / YYYY-MM-DDTHH:MM / YYYY-MM-DDTHH:MM:SS)
    end: str | None = None
    location: str = ""
    description: str = ""


class CalendarBuilder:
    """生成 RFC 5545 兼容 .ics 日历文件。底层使用 icalendar 库。"""

    def build(self, events: Sequence[CalendarEvent]) -> bytes:
        """将事件列表序列化为 .ics 字节串。"""
        try:
            from icalendar import Calendar, Event
        except ImportError as exc:
            raise RuntimeError(
                "icalendar 未安装。运行: pip install icalendar"
            ) from exc

        cal = Calendar()
        cal.add("prodid", "-//FileMate//CN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")

        for ev in events:
            evt = Event()
            evt.add("summary", ev.summary)
            evt.add("dtstart", self._parse_dt(ev.start))
            end_dt = self._parse_dt(ev.end) if ev.end else None
            if end_dt is None:
                end_dt = self._parse_dt(ev.start) + timedelta(hours=1)
            evt.add("dtend", end_dt)
            if ev.location:
                evt.add("location", ev.location)
            if ev.description:
                evt.add("description", ev.description)
            evt.add("dtstamp", datetime.now(timezone.utc))
            cal.add_component(evt)

        return cal.to_ical()

    def save(self, events: Sequence[CalendarEvent], out_path: str | Path) -> Path:
        """写入 .ics 文件，返回输出路径。"""
        data = self.build(events)
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        logger.info("已生成 .ics: %s (%d 个事件)", p, len(events))
        return p

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        """将 ISO 8601 日期时间字符串解析为 datetime。

        支持三种格式（按优先级尝试）：
        - YYYY-MM-DDTHH:MM:SS（含秒）
        - YYYY-MM-DDTHH:MM（含分钟）
        - YYYY-MM-DD（仅日期）
        """
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        raise ValueError(
            f"无法解析日期时间: {value!r}，"
            f"支持格式: YYYY-MM-DD / YYYY-MM-DDTHH:MM / YYYY-MM-DDTHH:MM:SS"
        )
