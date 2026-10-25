"""Transparent review rules; observations are not claims of long-term mastery."""

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

RULE_VERSION = "review-interval-v2"
INTERVALS = (1, 3, 7, 15, 30)
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def parse_time(value: Any) -> datetime | None:
    """Interpret historical SQLite timestamps as UTC, rejecting malformed input."""
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def transition(state: dict | None, *, correct: bool | None,
               independent: bool, now: datetime) -> dict:
    """Return an explainable state without reading storage or trusting client time."""
    if now.tzinfo is None or correct is not None and type(correct) is not bool:
        raise ValueError("复习时钟须带时区，判定须为布尔或待核对")
    now = now.astimezone(timezone.utc)
    legacy = bool(state and state.get("scheduler_version") != RULE_VERSION)
    result = {
        "learning_status": "new", "schedule_status": "active", "paused_at": None,
        "scheduler_version": RULE_VERSION, "review_stage": 0,
        "eligible_count": 0, "first_verified_at": None, "last_verified_at": None,
        "correct_streak": 0, "mastered": 0, "interval_days": 0,
        "next_review_at": now.isoformat(timespec="seconds"),
    }
    if state and not legacy:
        result.update(state)
    elif state:
        result["schedule_status"] = state.get("schedule_status", "active")
        result["learning_status"] = "needs_review"
        result["next_review_at"] = state.get("next_review_at")
    result.update(eligible=False, purpose="review" if state else "first_practice", reason="")

    def schedule(days: int) -> None:
        result["interval_days"] = days
        result["next_review_at"] = (now + timedelta(days=days)).isoformat(timespec="seconds")

    if correct is None:
        if not state or legacy:
            result["learning_status"] = "pending_check"
        result["reason"] = "pending_check"
        return result
    if not correct:
        result.update(learning_status="needs_review" if state else "new",
                      review_stage=0, eligible_count=0, first_verified_at=None,
                      last_verified_at=None, mastered=0, correct_streak=0,
                      reason="incorrect")
        schedule(1 if state else 0)
        return result
    if not independent:
        result["reason"] = "answer_revealed"
        return result
    if result["schedule_status"] == "paused":
        result["reason"] = "paused_practice"
        return result
    result["correct_streak"] += 1
    due = parse_time(result.get("next_review_at"))
    if due is None:
        result["reason"] = "invalid_schedule"
        return result
    if now < due:
        result.update(reason="early_practice", purpose="early_practice")
        return result
    if result["learning_status"] in {"new", "needs_review", "pending_check"}:
        result.update(learning_status="provisional", reason="initial_correction")
        schedule(1)
        return result
    last = parse_time(result.get("last_verified_at"))
    first = parse_time(result.get("first_verified_at"))
    if ((result.get("last_verified_at") and (last is None or last > now))
            or (result["eligible_count"] and (first is None or first > now))):
        result["reason"] = "invalid_history"
        return result
    if last is not None and last.astimezone(LOCAL_ZONE).date() == now.astimezone(LOCAL_ZONE).date():
        result["reason"] = "same_local_date"
        return result
    result["eligible_count"] += 1
    result["first_verified_at"] = result["first_verified_at"] or now.isoformat(timespec="seconds")
    result["last_verified_at"] = now.isoformat(timespec="seconds")
    result["review_stage"] = min(4, result["review_stage"] + 1)
    first = parse_time(result["first_verified_at"])
    criterion_met = result["eligible_count"] >= 3 and now - first >= timedelta(days=7)
    result.update(eligible=True, reason="delayed_verification",
                  mastered=int(criterion_met),
                  learning_status="criterion_met" if criterion_met else "provisional")
    schedule(INTERVALS[result["review_stage"]])
    return result
