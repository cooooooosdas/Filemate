"""用已有学习证据安排可解释的今日队列。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

_CAUSE_ACTIONS = {
    "concept_gap": ("概念缺口", "先核对定义，再遮住答案解释一遍", 12),
    "memory_gap": ("记忆遗漏", "先主动回忆，再对照原资料", 10),
    "reasoning_break": ("推理断点", "把条件、步骤和结论分别说清", 15),
    "expression_gap": ("表达困难", "按结论、依据、例子口头复述", 12),
    "option_confusion": ("选项混淆", "逐项解释正确条件与干扰点", 10),
    "careless": ("审题疏漏", "先圈出限制条件，再检查回答", 10),
    "unconfirmed": ("待确认", "先确认错因，再独立作答", 10),
}


def wrong_review_guidance(wrong: dict[str, Any], today: date) -> dict[str, Any]:
    """从到期、重复错误和已确认错因生成保守建议。"""
    cause = str(wrong.get("error_cause") or "unconfirmed")
    label, action, duration = _CAUSE_ACTIONS.get(cause, _CAUSE_ACTIONS["unconfirmed"])
    confirmed = wrong.get("error_cause_source") == "user"
    errors = max(1, int(wrong.get("error_count") or 1))
    try:
        due_at = datetime.fromisoformat(str(wrong.get("next_review_at") or ""))
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        overdue_days = max(0, (today - due_at.astimezone().date()).days)
    except (TypeError, ValueError):
        overdue_days = 0
    score = 76 + min(errors, 5) * 3 + min(overdue_days, 7)
    if confirmed and cause in {"concept_gap", "reasoning_break"}:
        score += 4
    reason = (
        f"已到复习时间；答错 {errors} 次"
        + (f"，逾期 {overdue_days} 天" if overdue_days else "")
        + f"。{'已确认' if confirmed else '待核对的建议'}错因：{label}；{action}。"
    )
    return {
        "score": score,
        "priority": "high" if errors >= 2 or overdue_days > 0 else "normal",
        "duration_minutes": duration,
        "reason": reason,
        "error_cause": cause,
        "error_cause_source": wrong.get("error_cause_source") or "unconfirmed",
    }


def select_daily_queue(
    candidates: list[dict[str, Any]],
    *,
    available_minutes: int,
    item_order: list[str],
    limit: int = 8,
) -> tuple[list[dict[str, Any]], int]:
    """先尊重用户排序，再按证据分数填入时间预算。"""
    order = {item_id: index for index, item_id in enumerate(item_order)}
    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if item["item_id"] in order else 1,
            order.get(item["item_id"], 0),
            -int(item["score"]),
            str(item["item_id"]),
        ),
    )
    selected: list[dict[str, Any]] = []
    used_minutes = 0
    for item in ranked:
        duration = max(1, int(item["duration_minutes"]))
        if len(selected) >= limit or used_minutes + duration > available_minutes:
            continue
        selected.append(item)
        used_minutes += duration
    return selected, len(candidates) - len(selected)
