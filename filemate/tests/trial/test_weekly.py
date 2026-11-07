"""Weekly review uses confirmed scoped arrangements and current original states."""

import json
from datetime import datetime, timezone

import pytest

from filemate.study.orchestrator.models import ScopeRequest
from filemate.study.orchestrator.repository import DAY_TYPE, atomic, day_id, put


def reader(world):
    from filemate.study.trial.weekly import WeeklyReader

    return WeeklyReader(world["store"], clock=lambda: world["now"][0])


def scope(world):
    return ScopeRequest(
        goal_id=world["goal"], course_id=world["courses"][0], source_ids=[world["sources"][0]]
    )


def save_day(world, day, ids, *, other_course=False):
    selected_scope = scope(world).model_dump()
    if other_course:
        selected_scope["course_id"] = world["courses"][1]
    with atomic(world["store"]) as conn:
        put(
            conn,
            day_id(day),
            DAY_TYPE,
            {"revision": 1, "config": {"scope": selected_scope, "selected_ids": ids}},
        )


def test_shanghai_week_crosses_utc_day_and_calendar_year(world):
    world["now"][0] = datetime(2026, 12, 27, 16, 30, tzinfo=timezone.utc)
    result = reader(world).read(scope(world))
    assert result.week_start == "2026-12-28"
    assert result.week_end == "2027-01-03"
    assert result.study_date == "2026-12-28"
    assert result.summary.total_tasks == 0
    assert result.coverage["meaning"] == "current_state_of_saved_week_arrangements"


def test_same_task_across_confirmed_days_is_counted_once(world):
    identifier = f"goal:{world['goal']}:review-source"
    save_day(world, "2026-10-26", [identifier])
    save_day(world, "2026-10-31", [identifier, identifier, "missing-original-task"])
    save_day(world, "2026-11-01", ["future-task"])
    save_day(world, "2026-10-25", ["previous-week-task"])
    result = reader(world).read(scope(world))
    assert result.summary.planned_days == 2
    assert result.summary.total_tasks == 2
    assert result.summary.pending_tasks == 1
    assert result.summary.unresolved_tasks == 1
    assert result.summary.completed_tasks == 0
    item = next(item for item in result.items if item.task_id == identifier)
    assert item.dates == ["2026-10-26", "2026-10-31"]
    assert item.task.title == "读懂资料"


def test_other_course_is_excluded_and_reference_damage_is_visible(world):
    save_day(world, "2026-10-26", ["wrong-course-task"], other_course=True)
    with atomic(world["store"]) as conn:
        put(
            conn,
            day_id("2026-10-27"),
            DAY_TYPE,
            {
                "revision": 1,
                "config": {"scope": scope(world).model_dump(), "selected_ids": "broken"},
            },
        )
    result = reader(world).read(scope(world))
    assert result.summary.total_tasks == 0
    assert result.coverage["excluded_days"] == 1
    assert result.coverage["invalid_days"] == 1


def test_current_original_completion_changes_bound_revision(world):
    identifier = f"goal:{world['goal']}:review-source"
    save_day(world, "2026-10-30", [identifier])
    before = reader(world).read(scope(world))
    with atomic(world["store"]) as conn:
        row = conn.execute(
            "SELECT content FROM artifacts WHERE artifact_id=?", (world["goal"],)
        ).fetchone()
        goal = json.loads(row["content"])
        goal["tasks"][0]["status"] = "completed"
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps(goal), world["goal"])
        )
    after = reader(world).read(scope(world))
    assert after.summary.completed_tasks == 1
    assert after.summary.pending_tasks == 0
    assert before.revision != after.revision


def test_large_saved_week_reports_unresolved_and_explicit_truncation(world):
    save_day(world, "2026-10-29", [f"missing-{i}" for i in range(150)])
    save_day(world, "2026-10-30", [f"missing-{i}" for i in range(150, 300)])
    result = reader(world).read(scope(world))
    assert result.summary.total_tasks == 300
    assert result.summary.unresolved_tasks == 300
    assert len(result.items) == 200
    assert result.coverage["omitted_items"] == 100
    assert result.coverage["truncated"] is True


@pytest.mark.parametrize("due,overdue", [
    ("2026-10-30T16:30:00Z", 0),
    ("2026-10-30T15:59:59+00:00", 1),
    ("2026-10-31", 0),
    ("2026-10-30", 1),
])
def test_overdue_uses_shanghai_calendar_date(world, due, overdue):
    with atomic(world["store"]) as conn:
        row = conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (world["goal"],)).fetchone()
        goal = json.loads(row["content"])
        goal["tasks"][0]["due_date"] = due
        conn.execute("UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps(goal), world["goal"]))
    save_day(world, "2026-10-31", [f"goal:{world['goal']}:review-source"])
    assert reader(world).read(scope(world)).summary.overdue_tasks == overdue
