"""Explain a queue heuristic without inventing mastery or learning outcomes."""

from datetime import datetime
from typing import Any

from filemate.wrongbook.engine import LOCAL_ZONE, parse_time

PRIORITY_RULE_VERSION = 'review2-priority-v1'
MAX_OVERDUE_DAYS = 30
OVERDUE_WEIGHT = 3
MAX_ERRORS = 10
ERROR_WEIGHT = 4
USER_CAUSE_WEIGHT = 4


def review_day(value: str) -> int | None:
    """Return the Shanghai calendar ordinal or no usable date."""
    parsed = parse_time(value)
    if parsed is None:
        return None
    try:
        return parsed.astimezone(LOCAL_ZONE).date().toordinal()
    except (ValueError, OverflowError):
        return None


def priority_details(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Explain only a valid, already-due record at a server-owned instant."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('推荐时钟缺少时区')
    due = parse_time(row.get('next_review_at'))
    day, today = review_day(row.get('next_review_at')), review_day(now.isoformat())
    errors = row.get('error_count')
    if due is None or day is None or today is None or due > now:
        raise ValueError('复习时间无效或尚未到期')
    if type(errors) is not int or errors < 0:
        raise ValueError('错答次数缺少有效记录')
    overdue = max(0, today - day)
    annotated = row.get('error_cause_source') == 'user'
    score = (min(overdue, MAX_OVERDUE_DAYS) * OVERDUE_WEIGHT
             + min(errors, MAX_ERRORS) * ERROR_WEIGHT
             + (USER_CAUSE_WEIGHT if annotated else 0))
    reasons = [f'逾期{overdue}天' if overdue else '今日到期', f'历史错答{errors}次']
    if annotated:
        reasons.append('错因由本人标注')
    return {'priority_score': score, 'overdue_days': overdue,
            'reason': ' · '.join(reasons), 'rule_version': PRIORITY_RULE_VERSION}
