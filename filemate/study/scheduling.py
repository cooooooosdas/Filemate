"""错题本：艾宾浩斯复习排期纯函数。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

REVIEW_INTERVALS: dict[int, int] = {1: 1, 2: 3, 3: 7, 4: 15, 5: 30}
# 复习排期的"今日"按中国时区计算，不依赖服务器本地时区。
LOCAL_ZONE = timezone(timedelta(hours=8))


def review_stage_after(stage: int) -> int:
    """复习一次后的阶段，最大 5。"""
    return min(max(int(stage or 1), 1) + 1, 5)


def next_review_date_str(stage: int, today: date | None = None) -> str:
    """按阶段返回下次复习日期字符串（YYYY-MM-DD）。"""
    today = today or datetime.now(LOCAL_ZONE).date()
    stage = min(max(int(stage or 1), 1), 5)
    interval = REVIEW_INTERVALS[stage]
    return (today + timedelta(days=interval)).isoformat()


def is_due(next_review_date: str, today: date | None = None) -> bool:
    """今日待复习：未掌握且下次复习日期不晚于今天。"""
    today = today or datetime.now(LOCAL_ZONE).date()
    try:
        return date.fromisoformat(next_review_date) <= today
    except (TypeError, ValueError):
        return False
