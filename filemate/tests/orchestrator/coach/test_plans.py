# ruff: noqa: F811
"""One native self-reported learning day per date, with bounded child actions."""

import pytest

from .conftest import coach_module, graph_evidence, read_context, submission
from .test_requests import request, service, service_case  # noqa: F401


def test_coach_group_absorbs_same_pending_review_cycle_without_a_second_todo(service_case):
    from filemate.study.orchestrator.task_views import project_tasks
    from filemate.tests.orchestrator.conftest import wrong

    identifier = wrong(service_case["world"])
    context = read_context(service_case)
    snapshot = context.snapshot.model_copy(deep=True)
    review = next(t for t in context.projection.tasks if t.kind == "review")
    snapshot.facts["plans"] = [
        {
            "plan_id": "synthetic-restored-review-group",
            "source_id": service_case["world"]["sources"][0],
            "status": "active",
            "exam_date": "2026-11-01",
            "days": [
                {
                    "day_index": 0,
                    "day": 1,
                    "date": "2026-11-01",
                    "duration_minutes": 10,
                    "completed": False,
                    "coach_group": True,
                    "coach_action_keys": [review.action_key],
                }
            ],
        }
    ]
    projected = project_tasks(snapshot)
    assert review.task_id not in [t.task_id for t in projected.tasks]
    grouped = next(t for t in projected.tasks if t.kind == "plan")
    assert any(
        ref.get("kind") == "review" and ref.get("id") == identifier for ref in grouped.origin_refs
    )


def test_archived_group_never_absorbs_an_active_review_cycle(service_case):
    from filemate.study.orchestrator.task_views import project_tasks
    from filemate.tests.orchestrator.conftest import wrong

    wrong(service_case["world"])
    context = read_context(service_case)
    snapshot = context.snapshot.model_copy(deep=True)
    review = next(t for t in context.projection.tasks if t.kind == "review")
    snapshot.facts["plans"] = [
        {
            "plan_id": "synthetic-archived-review-group",
            "source_id": service_case["world"]["sources"][0],
            "status": "archived",
            "exam_date": "2026-11-01",
            "days": [
                {
                    "day_index": 0,
                    "day": 1,
                    "date": "2026-11-01",
                    "duration_minutes": 10,
                    "completed": False,
                    "coach_group": True,
                    "coach_action_keys": [review.action_key],
                }
            ],
        }
    ]
    assert review.task_id in [t.task_id for t in project_tasks(snapshot).tasks]


def ready(case, *, multiday=False):
    row = submission(case["storage"])
    nodes = graph_evidence(case)
    data = case["input_data"] | {
        "selection": {"submission_ids": [row["submission_id"]], "concept_ids": nodes}
    }
    data["days"] = [{"study_date": "2026-10-31", "options": {"available_minutes": 80}}]
    if multiday:
        data["days"] = [
            {"study_date": day, "options": {"available_minutes": 25 if i == 0 else 40}}
            for i, day in enumerate(("2026-10-31", "2026-11-01"))
        ]
    current = case | {"input_data": data}
    view = service(current).request(request(current))
    draft = coach_module("models").CoachDraft.model_validate(
        {
            "work_id": view.work_id,
            "expected_context_revision": view.context_revision,
            "days": [d.model_dump(exclude={"schedule"}) for d in view.proposal.days],
            "new_actions": [a.model_dump() for a in view.proposal.new_actions],
            "overlap_choices": [],
        }
    )
    return current, view, draft


def test_plan_day_grouping_and_goal_link(service_case):
    case, _, draft = ready(service_case)
    plan = coach_module("plans").build_short_plan(
        read_context(case),
        draft,
        plan_id="synthetic-short-plan",
        artifact_id="synthetic-short-artifact",
    )
    days = plan["plan_data"]["daily_plan"]
    assert len(days) == len({a.study_date for a in draft.new_actions}) == 1
    assert len(days[0]["training_actions"]) == len(draft.new_actions) >= 2
    assert days[0]["duration_minutes"] == sum(a.minutes for a in draft.new_actions)
    assert plan["metadata"]["learning_coach"]["goal_id"] == case["world"]["goal"]


def test_native_coach_group_can_exceed_240_without_splitting_same_date(service_case):
    case, _, draft = ready(service_case)
    draft.days[0].options.available_minutes = 1440
    for action in draft.new_actions:
        action.minutes = 120
    plan = coach_module("plans").build_short_plan(
        read_context(case),
        draft,
        plan_id="synthetic-long-day",
        artifact_id="synthetic-long-day-artifact",
    )
    assert len(plan["plan_data"]["daily_plan"]) == 1
    assert plan["plan_data"]["daily_plan"][0]["duration_minutes"] == 360


def test_large_coach_group_keeps_minutes_and_child_origins_in_native_projection(service_case):
    from filemate.study.orchestrator.models import ScopeRequest
    from filemate.study.orchestrator.snapshot import SnapshotReader
    from filemate.study.orchestrator.task_views import project_tasks

    case, _, draft = ready(service_case)
    draft.days[0].options.available_minutes = 1440
    for action in draft.new_actions:
        action.minutes = 120
    plan = coach_module("plans").build_short_plan(
        read_context(case),
        draft,
        plan_id="synthetic-native-group",
        artifact_id="synthetic-native-group-artifact",
    )
    plan["metadata"]["learning_coach"]["operation_id"] = "synthetic-native-group-operation"
    conn = case["storage"]._conn()
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        coach_module("plans").write_short_plan(conn, plan)
    snapshot = SnapshotReader(case["storage"], clock=case["clock"]).read(
        ScopeRequest.model_validate(case["input_data"]["scope"])
    )
    task = next(
        t for t in project_tasks(snapshot).tasks if t.task_id == "plan:synthetic-native-group:0"
    )
    assert task.estimated_minutes == 360
    assert {r["id"] for r in task.origin_refs if r["kind"] == "coach_action"} == {
        a.action_key for a in draft.new_actions
    }


def test_write_short_plan_requires_existing_transaction_and_does_not_commit(service_case):
    case, _, draft = ready(service_case)
    plan = coach_module("plans").build_short_plan(
        read_context(case),
        draft,
        plan_id="synthetic-transaction-plan",
        artifact_id="synthetic-transaction-artifact",
    )
    writer = coach_module("plans").write_short_plan
    conn = case["storage"]._conn()
    with pytest.raises(RuntimeError):
        writer(conn, plan)
    conn.execute("BEGIN IMMEDIATE")
    try:
        writer(conn, plan)
        assert conn.in_transaction
    finally:
        conn.rollback()
    assert (
        conn.execute("SELECT 1 FROM study_plans WHERE plan_id=?", (plan["plan_id"],)).fetchone()
        is None
    )
