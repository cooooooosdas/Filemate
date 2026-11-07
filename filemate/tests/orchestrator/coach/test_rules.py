"""Local proposals preserve real clocks, budgets and original task identities."""

import copy
from datetime import timedelta

import pytest

from filemate.tests.orchestrator.conftest import wrong

from .conftest import coach_module, graph_evidence, read_context, submission


def proposal(case, **changes):
    return coach_module("rules").build_rule_proposal(read_context(case, **changes))


@pytest.mark.parametrize("intent", ["budget", "exam", "error_cause", "tomorrow", "next_step"])
@pytest.mark.parametrize("minutes", [0, 40, 1440])
def test_five_intents_keep_evidence_and_budget(coach_case, intent, minutes):
    result = proposal(
        coach_case,
        intent=intent,
        days=[{"study_date": "2026-10-31", "options": {"available_minutes": minutes}}],
    )
    assert result.rule_version == "learning-coach-rules-v1"
    assert result.prompt_version == "learning-coach-v2"
    assert len(result.new_actions) <= 7
    assert all(d.schedule.estimated_minutes <= d.options.available_minutes for d in result.days)
    assert len({a.action_key for a in result.new_actions}) == len(result.new_actions)
    if minutes == 0:
        assert not result.days[0].schedule.selected and not result.new_actions
    if intent == "error_cause":
        assert "confirmed_cause_unavailable" in result.limitations


def test_future_date_keeps_real_as_of_and_review_due_state(coach_case):
    store, w = coach_case["storage"], coach_case["world"]
    wid = wrong(w)
    due = (w["now"][0] + timedelta(days=6, microseconds=1)).isoformat()
    store._conn().execute(
        "UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?", (due, wid)
    )
    store._conn().commit()
    context = read_context(
        coach_case, days=[{"study_date": "2026-11-06", "options": {"available_minutes": 40}}]
    )
    assert context.as_of == w["now"][0]
    assert next(t for t in context.projection.tasks if t.kind == "review").eligibility == "not_due"
    result = coach_module("rules").build_rule_proposal(context)
    task = next(t for t in result.days[0].schedule.selected if t.kind == "review")
    assert "到期" in task.reason and result.days[0].study_date == "2026-11-06"
    assert context.projection.tasks[0].eligibility == "not_due"
    for day in ("2026-10-30", "2026-11-07"):
        with pytest.raises(coach_module("models").OrchestratorError):
            proposal(coach_case, days=[{"study_date": day, "options": {"available_minutes": 40}}])


def test_multiday_never_repeats_same_pending_task(coach_case):
    result = proposal(
        coach_case,
        days=[
            {"study_date": d, "options": {"available_minutes": 40}}
            for d in ("2026-10-31", "2026-11-01", "2026-11-02")
        ],
    )
    tasks = [t.task_id for day in result.days for t in day.schedule.selected]
    assert len(tasks) == len(set(tasks))


def test_pinned_overbudget_is_a_conflict(coach_case):
    task_id = f"goal:{coach_case['world']['goal']}:review-source"
    with pytest.raises(coach_module("models").OrchestratorError, match="pinned_task_conflict"):
        proposal(
            coach_case,
            days=[
                {
                    "study_date": "2026-10-31",
                    "options": {
                        "available_minutes": 5,
                        "item_order": [task_id],
                        "pinned_ids": [task_id],
                    },
                }
            ],
        )


def test_completed_unknown_estimate_and_pinned_order_are_preserved(coach_case):
    context = read_context(coach_case)
    original = context.projection.tasks[0]
    context.projection.completed = [original.model_copy(update={"status": "completed"})]
    context.projection.tasks = [
        original.model_copy(update={"task_id": "unknown", "estimated_minutes": None})
    ]
    result = coach_module("rules").build_rule_proposal(context)
    assert original.task_id not in [t.task_id for t in result.days[0].schedule.selected]
    assert "unknown" not in [t.task_id for t in result.days[0].schedule.selected]
    assert any(t.task_id == original.task_id for t in result.days[0].schedule.completed)


def test_completed_pinned_task_does_not_block_or_reopen_a_new_zero_budget_plan(coach_case):
    context = read_context(coach_case)
    task = context.projection.tasks.pop(0)
    task.status = "completed"
    context.projection.completed = [task]
    options = context.input.days[0].options
    options.available_minutes = 0
    options.item_order = [task.task_id]
    options.pinned_ids = [task.task_id]
    result = coach_module("rules").build_rule_proposal(context)
    assert not result.days[0].schedule.selected
    assert [t.task_id for t in result.days[0].schedule.completed] == [task.task_id]


def test_duplicate_action_ignores_display_name_and_new_cycle_has_new_identity(coach_case):
    store, w = coach_case["storage"], coach_case["world"]
    wid = wrong(w)
    store._conn().execute(
        "UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?",
        (w["now"][0].isoformat(), wid),
    )
    store._conn().commit()
    first = read_context(coach_case, selection={"wrong_ids": [wid]})
    first_result = coach_module("rules").build_rule_proposal(first)
    assert len([t for t in first_result.days[0].schedule.selected if t.kind == "review"]) == 1
    assert not any(a.action == "review_question" for a in first_result.new_actions)
    registry = coach_module("rules").action_candidates(first)
    before = next(a for a in registry if a.action == "review_question").action_key
    first.projection.tasks[0].title = "改个名称"
    assert (
        next(
            a
            for a in coach_module("rules").action_candidates(first)
            if a.action == "review_question"
        ).action_key
        == before
    )
    store._conn().execute(
        "UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?",
        ((w["now"][0] + timedelta(days=1)).isoformat(), wid),
    )
    store._conn().commit()
    second = read_context(coach_case, selection={"wrong_ids": [wid]})
    assert (
        next(
            a
            for a in coach_module("rules").action_candidates(second)
            if a.action == "review_question"
        ).action_key
        != before
    )


def test_compiler_practice_is_bounded_and_does_not_change_originals(coach_case):
    row = submission(coach_case["storage"])
    context = read_context(coach_case, selection={"submission_ids": [row["submission_id"]]})
    before = copy.deepcopy(context.model_dump())
    result = coach_module("rules").build_rule_proposal(context)
    assert any(a.action == "practice_problem" for a in result.new_actions)
    assert all(a.minutes >= 1 for a in result.new_actions)
    assert "score" not in result.model_dump_json()
    assert context.model_dump() == before


def test_shanghai_midnight_and_microsecond_due_do_not_fabricate_completion(coach_case):
    from datetime import datetime, timezone

    w, store = coach_case["world"], coach_case["storage"]
    w["now"][0] = datetime(2026, 10, 31, 15, 59, 59, 999999, tzinfo=timezone.utc)
    wid = wrong(w)
    due = (w["now"][0] + timedelta(microseconds=1)).isoformat()
    store._conn().execute(
        "UPDATE wrong_questions SET next_review_at=? WHERE wrong_id=?", (due, wid)
    )
    store._conn().commit()
    before = read_context(
        coach_case,
        days=[
            {"study_date": d, "options": {"available_minutes": 40}}
            for d in ("2026-10-31", "2026-11-01")
        ],
    )
    result = coach_module("rules").build_rule_proposal(before)
    assert not any(t.kind == "review" for t in result.days[0].schedule.selected)
    assert any(t.kind == "review" for t in result.days[1].schedule.selected)
    assert not any(t.kind == "review" for t in result.days[1].schedule.completed)
    w["now"][0] += timedelta(microseconds=1)
    after = read_context(
        coach_case, days=[{"study_date": "2026-11-01", "options": {"available_minutes": 40}}]
    )
    assert before.context_revision != after.context_revision
    assert any(
        t.kind == "review"
        for t in coach_module("rules").build_rule_proposal(after).days[0].schedule.selected
    )


def test_confirmed_graph_prerequisites_precede_new_concept_practice(coach_case):
    ids = graph_evidence(coach_case)
    context = read_context(coach_case, selection={"concept_ids": ids})
    result = coach_module("rules").build_rule_proposal(context)
    by_node = {
        a.target_ref.id: a.action_key for a in result.new_actions if a.action == "train_concept"
    }
    chosen = [t.task_id for t in result.days[0].schedule.selected]
    assert chosen.index(by_node["coach-stack"]) < chosen.index(by_node["coach-dfs"])


def test_depends_on_explanation_uses_the_dependent_endpoint(coach_case):
    ids = graph_evidence(coach_case)
    store = coach_case["storage"]
    store._conn().execute(
        "UPDATE kg_relations SET from_id='coach-dfs',to_id='coach-stack',type='depends_on' WHERE relation_id='coach-edge'"
    )
    store._conn().commit()
    result = proposal(coach_case, selection={"concept_ids": ids})
    action = next(a for a in result.new_actions if a.target_ref.id == "coach-dfs")
    assert (
        next(e for e in result.explanations if e.task_id == action.action_key).reason_code
        == "confirmed_dependency"
    )


def test_selected_feedback_is_an_expression_exercise_not_an_ability_score(coach_case):
    import json

    from .test_context import feedback

    store, w = coach_case["storage"], coach_case["world"]
    value = store.get_artifact(w["goal"])["content"] | {"goal_type": "competition"}
    store._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps(value), w["goal"])
    )
    store._conn().commit()
    sid, _, attempt = feedback(store, w["sources"][0])
    context = read_context(
        coach_case,
        selection={
            "interview_ids": [sid],
            "feedback_refs": [
                {
                    "interview_id": sid,
                    "attempt_id": attempt.attempt_id,
                    "feedback_item_id": "logic",
                    "expected_revision": "synthetic-analysis",
                }
            ],
        },
    )
    changes = store._conn().total_changes
    result = coach_module("rules").build_rule_proposal(context)
    assert any(a.action == "rehearse_interview" for a in result.new_actions)
    assert "score" not in result.model_dump_json()
    assert store._conn().total_changes == changes
