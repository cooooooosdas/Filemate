"""Literal clock cases pin the approved rule, without simulated learning claims."""

import importlib
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest


def engine():
    assert importlib.util.find_spec("filemate.wrongbook.engine") is not None
    return importlib.import_module("filemate.wrongbook.engine")


def at(value):
    return datetime.fromisoformat(value)


START = at("2026-10-26T08:00:00+00:00")


def test_first_error_correction_and_three_delayed_verifications():
    rule = engine()
    wrong = rule.transition(None, correct=False, independent=True, now=START)
    assert wrong["learning_status"] == "new" and wrong["next_review_at"] == "2026-10-26T08:00:00+00:00"
    assert wrong["eligible_count"] == 0 and wrong["purpose"] == "first_practice"
    fixed = rule.transition(wrong, correct=True, independent=True, now=START)
    assert fixed["next_review_at"] == "2026-10-27T08:00:00+00:00"
    assert fixed["eligible_count"] == 0 and not fixed["mastered"]
    first = rule.transition(fixed, correct=True, independent=True, now=START + timedelta(days=1))
    assert first["eligible_count"] == 1 and first["next_review_at"] == "2026-10-30T08:00:00+00:00"
    second = rule.transition(first, correct=True, independent=True, now=START + timedelta(days=4))
    assert second["eligible_count"] == 2 and second["next_review_at"] == "2026-11-06T08:00:00+00:00"
    third = rule.transition(second, correct=True, independent=True, now=START + timedelta(days=11))
    assert third["eligible_count"] == 3 and third["learning_status"] == "criterion_met"
    assert third["mastered"] == 1 and third["next_review_at"] == "2026-11-21T08:00:00+00:00"
    fourth = rule.transition(third, correct=True, independent=True, now=START + timedelta(days=26))
    assert fourth["interval_days"] == 30
    fifth = rule.transition(fourth, correct=True, independent=True, now=START + timedelta(days=56))
    assert fifth["interval_days"] == 30
    failed = rule.transition(fifth, correct=False, independent=True, now=START + timedelta(days=57))
    assert failed["learning_status"] == "needs_review" and failed["eligible_count"] == 0
    assert failed["first_verified_at"] is None and failed["next_review_at"] == "2026-12-23T08:00:00+00:00"


@pytest.mark.parametrize("independent,correct,reason", [
    (True, True, "early_practice"), (False, True, "answer_revealed"), (True, None, "pending_check"),
])
def test_early_revealed_and_unjudged_never_advance_or_postpone(independent, correct, reason):
    rule = engine()
    state = rule.transition(rule.transition(None, correct=False, independent=True, now=START),
                            correct=True, independent=True, now=START)
    result = rule.transition(state, correct=correct, independent=independent, now=START + timedelta(hours=1))
    assert result["eligible_count"] == 0 and result["next_review_at"] == state["next_review_at"]
    assert result["reason"] == reason and result["eligible"] is False


def test_same_shanghai_date_is_not_another_delayed_verification():
    rule = engine()
    state = {"scheduler_version": rule.RULE_VERSION, "learning_status": "provisional",
             "next_review_at": "2026-10-26T16:01:00+00:00", "review_stage": 1,
             "eligible_count": 1, "first_verified_at": "2026-10-26T16:00:00+00:00",
             "last_verified_at": "2026-10-26T16:00:00+00:00"}
    result = rule.transition(state, correct=True, independent=True, now=at("2026-10-27T01:00:00+00:00"))
    assert result["eligible_count"] == 1 and result["reason"] == "same_local_date"
    assert not result["eligible"]


def test_invalid_or_future_verification_dates_do_not_create_evidence():
    rule = engine()
    state = {"scheduler_version": rule.RULE_VERSION, "learning_status": "provisional",
             "next_review_at": "not-a-date", "eligible_count": 0}
    result = rule.transition(state, correct=True, independent=True, now=START)
    assert result["reason"] == "invalid_schedule" and result["next_review_at"] == "not-a-date"
    state.update(next_review_at=START.isoformat(), last_verified_at=(START + timedelta(days=1)).isoformat())
    result = rule.transition(state, correct=True, independent=True, now=START)
    assert result["reason"] == "invalid_history" and not result["eligible"]


def test_utc_legacy_time_leap_day_and_naive_clock():
    rule = engine()
    assert rule.parse_time("2024-02-29T23:00:00") == at("2024-02-29T23:00:00+00:00")
    assert rule.parse_time("2024-02-30") is None
    result = rule.transition({"learning_status": "new", "scheduler_version": rule.RULE_VERSION},
                             correct=True, independent=True, now=at("2024-02-29T23:00:00+00:00"))
    assert result["next_review_at"] == "2024-03-01T23:00:00+00:00"
    with pytest.raises(ValueError):
        rule.transition(None, correct=False, independent=True, now=datetime(2026, 10, 26))


def test_paused_and_legacy_counts_do_not_silently_upgrade():
    rule = engine()
    paused = {"scheduler_version": rule.RULE_VERSION, "learning_status": "provisional",
              "schedule_status": "paused", "next_review_at": START.isoformat(), "eligible_count": 1}
    result = rule.transition(paused, correct=True, independent=True, now=START)
    assert result["eligible_count"] == 1 and result["reason"] == "paused_practice"
    legacy = {"scheduler_version": "legacy-v1", "review_count": 900, "correct_streak": 900,
              "next_review_at": START.isoformat(), "mastered": 0}
    result = rule.transition(legacy, correct=True, independent=True, now=START)
    assert result["eligible_count"] == 0 and result["learning_status"] == "provisional"


@pytest.mark.parametrize("status,version", [("needs_review", "review-interval-v2"), ("legacy", "legacy-v1")])
def test_early_correction_of_due_later_record_keeps_its_original_schedule(status, version):
    rule = engine()
    state = {"scheduler_version": version, "learning_status": status,
             "next_review_at": "2026-10-27T08:00:00+00:00", "mastered": 0}
    result = rule.transition(state, correct=True, independent=True, now=START)
    assert result["reason"] == "early_practice"
    assert result["next_review_at"] == state["next_review_at"]
    assert result["learning_status"] == "needs_review"
