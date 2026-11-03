# ruff: noqa: F811
"""Atomic joint plan/day writes, replay, compare-and-swap and protected undo."""

import json
import sqlite3
from datetime import timedelta

import pytest

from .conftest import coach_module
from .test_plans import ready
from .test_requests import service_case  # noqa: F401


def test_future_native_group_is_not_scheduled_early_by_existing_today(service_case):
    from filemate.study.orchestrator.models import ScheduleOptions, ScopeRequest
    from filemate.study.orchestrator.scheduler import build_schedule
    from filemate.study.orchestrator.snapshot import SnapshotReader
    from filemate.study.orchestrator.task_views import project_tasks

    case, _, draft = ready(service_case)
    draft.days[0].study_date = "2026-11-01"
    for action in draft.new_actions:
        action.study_date = "2026-11-01"
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    snapshot = SnapshotReader(case["storage"], clock=case["clock"]).read(
        ScopeRequest.model_validate(case["input_data"]["scope"])
    )
    projected = project_tasks(snapshot)
    identifier = f"plan:{receipt.plan_id}:0"
    assert next(t for t in projected.tasks if t.task_id == identifier).eligibility == "not_due"
    assert identifier not in [
        t.task_id
        for t in build_schedule(
            snapshot, projected, ScheduleOptions(available_minutes=1440)
        ).selected
    ]
    future = (
        coach_module("commands")
        .CoachDayReader(case["storage"], clock=case["clock"])
        .read("2026-11-01")
    )
    assert future.status == "confirmed"
    assert next(t for t in future.selected if t.task_id == identifier).eligibility == "eligible"


def test_archived_unused_batch_does_not_block_a_new_proposal(service_case):
    from filemate.study.orchestrator.coach.rules import build_rule_proposal
    from filemate.study.orchestrator.models import UndoConfirmRequest

    from .conftest import read_context

    case, _, draft = ready(service_case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    undo = api.preview_undo(receipt.operation_id)
    api.confirm_undo(
        receipt.operation_id,
        UndoConfirmRequest(
            confirmation_token=undo.confirmation_token,
            request_key="synthetic_archive_then_retry",
            confirmed=True,
        ),
    )
    new = build_rule_proposal(read_context(case))
    assert {a.action_key for a in new.new_actions} == {a.action_key for a in draft.new_actions}


def test_repeated_identical_previews_are_bounded_without_creating_plans(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    for _ in range(100):
        api.preview(draft)
    with pytest.raises(coach_module("models").OrchestratorError) as error:
        api.preview(draft)
    assert error.value.status_code == 429
    assert case["storage"]._conn().execute("SELECT count(*) FROM study_plans").fetchone()[0] == 0


def test_unknown_composite_overlap_is_disclosed_without_automatic_equivalence(service_case):
    store, w = service_case["storage"], service_case["world"]
    data = {
        "title": "旧复合日",
        "exam_date": "2026-11-05",
        "daily_minutes": 10,
        "daily_plan": [
            {"day": 1, "date": "2026-10-31", "duration_minutes": 10, "tasks": ["人工安排"]}
        ],
    }
    aid = store.save_artifact(artifact_type="study_plan", source_id=w["sources"][0], content=data)
    old = store.create_study_plan(artifact_id=aid, source_id=w["sources"][0], plan=data)
    case, _, draft = ready(service_case)
    api = commands(case)
    preview = api.preview(draft)
    assert any(
        item["original_task_id"] == f"plan:{old['plan_id']}:0"
        for item in preview.changes["possible_overlaps"]
    )
    api.confirm(confirm_body(draft, preview))
    assert store.get_study_plan(old["plan_id"]) == old


def commands(case):
    return coach_module("commands").CoachCommands(case["storage"], clock=case["clock"])


def confirm_body(draft, preview, *, key="synthetic_joint_confirm_0001"):
    return coach_module("models").CoachConfirm.model_validate(
        draft.model_dump()
        | {"confirmation_token": preview.confirmation_token, "request_key": key, "confirmed": True}
    )


def fingerprint(store):
    return {
        name: [tuple(row) for row in store._conn().execute(f"SELECT * FROM {name} ORDER BY rowid")]
        for name in (
            "artifacts",
            "study_plans",
            "kg_learning_artifact_sources",
            "data_action_previews",
            "data_action_audit",
        )
    }


def test_preview_creates_no_study_plan(service_case):
    case, _, draft = ready(service_case)
    count = case["storage"]._conn().execute("SELECT count(*) FROM study_plans").fetchone()[0]
    preview = commands(case).preview(draft)
    assert preview.expires_in_seconds == 900
    assert preview.new_plan_id and preview.new_artifact_id
    assert (
        case["storage"]._conn().execute("SELECT count(*) FROM study_plans").fetchone()[0] == count
    )


@pytest.mark.parametrize("point", ["plan", "source", "second_day", "receipt", "audit"])
def test_joint_confirm_rolls_back_every_business_write(service_case, point):
    case, _, draft = ready(service_case, multiday=True)
    api = commands(case)
    preview = api.preview(draft)
    before = fingerprint(case["storage"])
    table, when = {
        "plan": ("study_plans", "1=1"),
        "source": ("kg_learning_artifact_sources", "1=1"),
        "second_day": ("artifacts", "NEW.artifact_id='learning-day-2026-11-01'"),
        "receipt": ("artifacts", "NEW.artifact_type='learning_coach_operation'"),
        "audit": ("data_action_audit", "1=1"),
    }[point]
    case["storage"]._conn().execute(
        f"CREATE TRIGGER fail_joint_write BEFORE INSERT ON {table} WHEN {when} BEGIN SELECT RAISE(ABORT,'synthetic-write-failure'); END"
    )
    case["storage"]._conn().commit()
    with pytest.raises(sqlite3.DatabaseError, match="synthetic-write-failure"):
        api.confirm(confirm_body(draft, preview))
    assert fingerprint(case["storage"]) == before
    case["storage"]._conn().execute("DROP TRIGGER fail_joint_write")
    case["storage"]._conn().commit()
    receipt = api.confirm(confirm_body(draft, preview))
    assert receipt.status == "confirmed"
    assert case["storage"]._conn().execute("SELECT count(*) FROM study_plans").fetchone()[0] == 1


def test_two_tabs_compare_every_affected_day_revision(service_case):
    case, _, draft = ready(service_case, multiday=True)
    api = commands(case)
    first, second = api.preview(draft), api.preview(draft)
    api.confirm(confirm_body(draft, first))
    with pytest.raises(coach_module("models").OrchestratorError):
        api.confirm(confirm_body(draft, second, key="synthetic_joint_confirm_0002"))


def test_replay_before_revalidation_returns_original_receipt(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    body = confirm_body(draft, api.preview(draft))
    original = api.confirm(body)
    case["world"]["now"][0] += timedelta(days=1)
    assert api.confirm(body) == original
    assert api.find(body.request_key) == original
    assert case["storage"]._conn().execute("SELECT count(*) FROM study_plans").fetchone()[0] == 1


def test_human_budget_edit_does_not_need_another_model_or_original_input_hash(service_case):
    case, _, draft = ready(service_case)
    draft.days[0].options.available_minutes = 90
    for action in draft.new_actions:
        action.minutes = 15
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    assert receipt.plan_id and receipt.status == "confirmed"


def test_same_day_actions_share_one_original_completion_unit(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    result = api.confirm(confirm_body(draft, api.preview(draft)))
    plan = case["storage"].get_study_plan(result.plan_id)
    assert len(plan["plan_data"]["daily_plan"]) == 1 and plan["completed_days"] == []
    case["storage"].set_study_plan_day(result.plan_id, 0, True)
    assert case["storage"].get_study_plan(result.plan_id)["completed_days"] == [0]
    from filemate.study.orchestrator.repository import OrchestratorRepository

    day = OrchestratorRepository(case["storage"], clock=case["clock"]).today(case["clock"]().date())
    assert any(t.task_id == f"plan:{result.plan_id}:0" for t in day.completed)
    assert not any(t.task_id in {a.action_key for a in draft.new_actions} for t in day.selected)


@pytest.mark.parametrize("change", ["completion", "attempt", "edit", "day"])
def test_undo_rejects_started_plan_or_changed_day(service_case, change):
    case, _, draft = ready(service_case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    store = case["storage"]
    if change == "completion":
        store.set_study_plan_day(receipt.plan_id, 0, True)
    elif change == "attempt":
        store.record_quiz_attempt(
            artifact_id=case["world"]["artifact"],
            question_index=0,
            user_answer="B",
            is_correct=False,
            score=0,
            feedback="原创合成错误",
        )
    elif change == "edit":
        plan = store.get_study_plan(receipt.plan_id)
        store.update_artifact(plan["artifact_id"], title="已人工修改", content={"edited": True})
    else:
        row = (
            store._conn()
            .execute("SELECT content FROM artifacts WHERE artifact_id='learning-day-2026-10-31'")
            .fetchone()
        )
        content = json.loads(row[0]) | {"revision": 9}
        store._conn().execute(
            "UPDATE artifacts SET content=? WHERE artifact_id='learning-day-2026-10-31'",
            (json.dumps(content),),
        )
        store._conn().commit()
    with pytest.raises(coach_module("models").OrchestratorError):
        api.preview_undo(receipt.operation_id)


def test_undo_archives_only_new_plan_and_replays_after_midnight(service_case):
    case, _, draft = ready(service_case, multiday=True)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    preview = api.preview_undo(receipt.operation_id)
    from filemate.study.orchestrator.models import UndoConfirmRequest

    body = UndoConfirmRequest(
        confirmation_token=preview.confirmation_token,
        request_key="synthetic_joint_undo_0001",
        confirmed=True,
    )
    undone = api.confirm_undo(receipt.operation_id, body)
    assert (
        undone.status == "undone"
        and case["storage"].get_study_plan(receipt.plan_id)["status"] == "archived"
    )
    case["world"]["now"][0] += timedelta(days=1)
    assert api.confirm_undo(receipt.operation_id, body) == undone
    assert api.find("synthetic_joint_confirm_0001").status == "undone"


def test_unused_undo_token_fails_across_shanghai_day(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    preview = api.preview_undo(receipt.operation_id)
    from filemate.study.orchestrator.models import UndoConfirmRequest

    body = UndoConfirmRequest(
        confirmation_token=preview.confirmation_token,
        request_key="synthetic_joint_undo_0001",
        confirmed=True,
    )
    case["world"]["now"][0] += timedelta(days=1)
    with pytest.raises(coach_module("models").OrchestratorError):
        api.confirm_undo(receipt.operation_id, body)


def test_saved_tomorrow_works_when_original_work_date_is_yesterday(service_case):
    case, _, draft = ready(service_case, multiday=True)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    case["world"]["now"][0] += timedelta(days=1)
    day = (
        coach_module("commands")
        .CoachDayReader(case["storage"], clock=case["clock"])
        .read("2026-11-01")
    )
    assert day.status == "confirmed" and day.selected
    assert day.latest_operation.operation_id == receipt.operation_id


def test_completed_then_unchecked_plan_still_has_started_evidence(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    store = case["storage"]
    original = store.get_study_plan(receipt.plan_id)["updated_at"]
    store.set_study_plan_day(receipt.plan_id, 0, True)
    store.set_study_plan_day(receipt.plan_id, 0, False)
    # Fix second-resolution timestamp collisions so the test does not depend on speed.
    store._conn().execute(
        "UPDATE study_plans SET updated_at=? WHERE plan_id=?", (original, receipt.plan_id)
    )
    store._conn().commit()
    with pytest.raises(coach_module("models").OrchestratorError, match="started"):
        api.preview_undo(receipt.operation_id)


def test_progress_audit_failure_rolls_back_original_day_completion(service_case):
    case, _, draft = ready(service_case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    store = case["storage"]
    store._conn().execute(
        "CREATE TRIGGER fail_progress_audit BEFORE INSERT ON data_action_audit WHEN NEW.action='learning_coach_plan_progress' BEGIN SELECT RAISE(ABORT,'synthetic-progress-audit-failure'); END"
    )
    store._conn().commit()
    before = store.get_study_plan(receipt.plan_id)
    with pytest.raises(sqlite3.DatabaseError, match="synthetic-progress-audit-failure"):
        store.set_study_plan_day(receipt.plan_id, 0, True)
    assert store.get_study_plan(receipt.plan_id) == before


def test_commit_failure_can_retry_same_key_without_partial_business_writes(service_case):
    case, _, draft = ready(service_case, multiday=True)
    api = commands(case)
    preview = api.preview(draft)
    store, conn = case["storage"], case["storage"]._conn()
    conn.execute(
        "CREATE TABLE synthetic_commit_failure(value TEXT REFERENCES sources(source_id) DEFERRABLE INITIALLY DEFERRED)"
    )
    conn.execute(
        "CREATE TRIGGER fail_joint_commit AFTER INSERT ON artifacts WHEN NEW.artifact_type='learning_coach_operation' BEGIN INSERT INTO synthetic_commit_failure VALUES ('missing-synthetic-source'); END"
    )
    conn.commit()
    before = fingerprint(store)
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        api.confirm(confirm_body(draft, preview))
    assert fingerprint(store) == before
    conn.execute("DROP TRIGGER fail_joint_commit")
    conn.commit()
    assert api.confirm(confirm_body(draft, preview)).status == "confirmed"


def test_explicit_overlap_choice_keeps_original_plan_data_and_excludes_its_day(service_case):
    store, w = service_case["storage"], service_case["world"]
    data = {
        "title": "旧复合计划",
        "exam_date": "2026-11-05",
        "daily_minutes": 10,
        "daily_plan": [
            {"day": 1, "date": "2026-10-31", "duration_minutes": 10, "tasks": ["旧任务"]}
        ],
    }
    aid = store.save_artifact(artifact_type="study_plan", source_id=w["sources"][0], content=data)
    old = store.create_study_plan(artifact_id=aid, source_id=w["sources"][0], plan=data)
    case, _, draft = ready(service_case)
    choice = coach_module("models").CoachOverlapChoice(
        original_task_id=f"plan:{old['plan_id']}:0", keep="proposed"
    )
    draft.overlap_choices = [choice]
    api = commands(case)
    api.confirm(confirm_body(draft, api.preview(draft)))
    from filemate.study.orchestrator.repository import OrchestratorRepository

    day = OrchestratorRepository(store, clock=case["clock"]).today(case["clock"]().date())
    assert choice.original_task_id not in [t.task_id for t in day.selected]
    assert store.get_study_plan(old["plan_id"]) == old


def test_existing_c_confirmation_and_coach_cannot_win_the_same_day(service_case):
    from filemate.study.orchestrator.commands import OrchestratorCommands
    from filemate.study.orchestrator.models import (
        ConfirmRequest,
        PreviewRequest,
        ScheduleOptions,
        ScopeRequest,
    )
    from filemate.study.orchestrator.snapshot import SnapshotReader

    case, _, draft = ready(service_case)
    store, api = case["storage"], commands(case)
    coach_preview = api.preview(draft)
    snap = SnapshotReader(store, clock=case["clock"]).read(
        ScopeRequest.model_validate(case["input_data"]["scope"])
    )
    old = OrchestratorCommands(store, clock=case["clock"])
    preview_body = PreviewRequest(
        scope=snap.scope,
        expected_evidence_revision=snap.evidence_revision,
        options=ScheduleOptions(available_minutes=40),
    )
    c_preview = old.preview(preview_body)
    c_receipt = old.confirm(
        ConfirmRequest(
            **preview_body.model_dump(),
            confirmation_token=c_preview.confirmation_token,
            request_key="synthetic_existing_c_confirm",
            confirmed=True,
        )
    )
    with pytest.raises(coach_module("models").OrchestratorError):
        api.confirm(confirm_body(draft, coach_preview))
    fresh = api.preview(draft)
    receipt = api.confirm(confirm_body(draft, fresh))
    with pytest.raises(coach_module("models").OrchestratorError):
        old.preview_undo(c_receipt.operation_id)
    assert store.get_study_plan(receipt.plan_id)["status"] == "active"


def test_source_less_accepted_plan_is_visible_only_to_its_explicit_goal(service_case):
    from .conftest import read_context, submission
    from .test_requests import request, service

    store = service_case["storage"]
    sid = submission(store)["submission_id"]
    goal = store.save_artifact(
        artifact_type="reverse_goal_plan",
        content={"title": "无资料编程目标", "goal_type": "skill", "tasks": []},
    )
    case = service_case | {
        "input_data": service_case["input_data"]
        | {"scope": {"goal_id": goal}, "selection": {"submission_ids": [sid]}}
    }
    view = service(case).request(request(case))
    model = coach_module("models")
    draft = model.CoachDraft(
        work_id=view.work_id,
        expected_context_revision=view.context_revision,
        days=[
            model.CoachDayInput.model_validate(d.model_dump(exclude={"schedule"}))
            for d in view.proposal.days
        ],
        new_actions=view.proposal.new_actions,
    )
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    assert store.get_study_plan(receipt.plan_id)["source_id"] is None
    assert [p["plan_id"] for p in read_context(case).snapshot.facts["plans"]] == [receipt.plan_id]
    other = store.save_artifact(
        artifact_type="reverse_goal_plan", content={"goal_type": "custom", "tasks": []}
    )
    assert read_context(case, scope={"goal_id": other}).snapshot.facts["plans"] == []


def test_multisource_accepted_plan_requires_every_dependency_in_scope(service_case):
    from filemate.course_graph.repository import CourseGraphRepository

    from .conftest import read_context

    store, w = service_case["storage"], service_case["world"]
    revision = (
        store._conn()
        .execute("SELECT revision FROM kg_courses WHERE course_id=?", (w["courses"][0],))
        .fetchone()[0]
    )
    CourseGraphRepository(store).attach_sources(w["courses"][0], [w["sources"][1]], None, revision)
    both = service_case | {
        "input_data": service_case["input_data"]
        | {
            "scope": {
                "goal_id": w["goal"],
                "course_id": w["courses"][0],
                "source_ids": w["sources"],
            }
        }
    }
    case, _, draft = ready(both)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    assert store.get_study_plan(receipt.plan_id)["source_id"] is None
    assert [p["plan_id"] for p in read_context(case).snapshot.facts["plans"]] == [receipt.plan_id]
    one = {"goal_id": w["goal"], "course_id": w["courses"][0], "source_ids": [w["sources"][0]]}
    assert read_context(case, scope=one).snapshot.facts["plans"] == []
