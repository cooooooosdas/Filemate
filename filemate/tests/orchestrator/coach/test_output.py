"""Model output is finite, evidence-bound and unable to invent tasks or scores."""

import copy
import json

import pytest

from .conftest import coach_module, read_context, submission


@pytest.mark.parametrize("character", ["𠀀", '"', "\n"])
def test_model_message_limit_includes_wrapping_and_full_system_prompt(coach_context, character):
    from filemate.study.orchestrator.coach.context import external_payload
    from filemate.study.orchestrator.coach.evidence import fact

    facts = [fact("source", str(i), {"i": i}, {"title": character * 240}) for i in range(80)]
    coach_context.external_payload = external_payload(
        coach_context.input, coach_context.snapshot, coach_context.projection, facts
    )
    messages = coach_module("prompts").build_model_messages(coach_context)
    assert len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) <= 65536


def prepared(case):
    row = submission(case["storage"])
    context = read_context(case, selection={"submission_ids": [row["submission_id"]]})
    baseline = coach_module("rules").build_rule_proposal(context)
    candidate = baseline.new_actions[0].model_dump(mode="json")
    candidate.pop("action_key")
    return context, baseline, {"explanations": [], "task_order": [], "new_actions": [candidate]}


def test_valid_enhancement_reuses_server_identity(coach_case):
    context, baseline, raw = prepared(coach_case)
    raw["new_actions"][0]["method_code"] = "compare_cases"
    raw["new_actions"][0]["minutes"] = 10
    enhanced = coach_module("output").validate_enhancement(context, baseline, raw)
    assert enhanced.new_actions[0].action_key == baseline.new_actions[0].action_key
    assert enhanced.new_actions[0].minutes == 10
    assert enhanced.days[0].schedule.estimated_minutes <= 40


def test_explanation_only_enhancement_keeps_the_rule_actions(coach_case):
    context, baseline, _ = prepared(coach_case)
    enhanced = coach_module("output").validate_enhancement(
        context, baseline, {"explanations": [], "task_order": [], "new_actions": []}
    )
    assert enhanced.new_actions == baseline.new_actions


@pytest.mark.parametrize(
    "kind",
    [
        "unknown_fact",
        "unknown_target",
        "cross_course",
        "unconfirmed_cause",
        "score",
        "url",
        "extra",
        "duplicate",
        "eighth",
        "unknown_task",
        "wrong_method",
    ],
)
def test_invalid_enhancement_preserves_rule_result(coach_case, kind):
    context, baseline, raw = prepared(coach_case)
    before = copy.deepcopy(baseline.model_dump())
    item = raw["new_actions"][0]
    if kind == "unknown_fact":
        item["fact_ids"] = ["invented-fact"]
    elif kind == "unknown_target":
        item["target_ref"]["id"] = "invented-problem"
    elif kind == "cross_course":
        item["target_ref"]["course_id"] = "another-course"
    elif kind == "unconfirmed_cause":
        raw["explanations"] = [
            {
                "task_id": None,
                "reason_code": "confirmed_cause",
                "method_code": "trace_error",
                "fact_ids": [next(f.fact_id for f in context.facts if f.kind == "compiler_result")],
            }
        ]
    elif kind == "score":
        raw["score"] = 99
    elif kind == "url":
        item["route"] = "https://example.invalid/execute"
    elif kind == "extra":
        item["action_key"] = "model-created-identity"
    elif kind == "duplicate":
        raw["new_actions"] *= 2
    elif kind == "eighth":
        raw["new_actions"] *= 8
    elif kind == "unknown_task":
        raw["task_order"] = ["invented-task"]
    else:
        item["method_code"] = "rehearse"
    with pytest.raises(coach_module("models").OrchestratorError):
        coach_module("output").validate_enhancement(context, baseline, raw)
    assert baseline.model_dump() == before


def test_model_messages_use_only_previewed_payload_and_enforce_byte_limit(coach_context):
    messages = coach_module("prompts").build_model_messages(coach_context)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert json.loads(messages[1]["content"]) == coach_context.external_payload
    assert len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) <= 65536
    assert "synthetic-secret-question" not in messages[1]["content"]


def test_model_cannot_omit_pinned_task(coach_case):
    context, baseline, raw = prepared(coach_case)
    task = context.projection.tasks[0].task_id
    context.input.days[0].options.item_order = [task]
    context.input.days[0].options.pinned_ids = [task]
    raw["task_order"] = []
    # Empty order means no requested change, so pins must remain selected.
    enhanced = coach_module("output").validate_enhancement(context, baseline, raw)
    assert task in [t.task_id for t in enhanced.days[0].schedule.selected]


def test_enhancement_cannot_sneak_an_overbudget_action(coach_case):
    context, baseline, raw = prepared(coach_case)
    raw["new_actions"][0]["minutes"] = 240
    with pytest.raises(
        coach_module("models").OrchestratorError, match="model_actions_unschedulable"
    ):
        coach_module("output").validate_enhancement(context, baseline, raw)


def test_model_order_cannot_move_a_pinned_position(coach_case):
    context, baseline, raw = prepared(coach_case)
    first = context.projection.tasks[0]
    other = first.model_copy(update={"task_id": "second-existing-task"})
    context.projection.tasks.append(other)
    options = context.input.days[0].options
    options.item_order = [first.task_id, other.task_id]
    options.pinned_ids = [first.task_id]
    raw["task_order"] = [other.task_id, first.task_id]
    with pytest.raises(coach_module("models").OrchestratorError, match="pinned_task_conflict"):
        coach_module("output").validate_enhancement(context, baseline, raw)


def test_model_cannot_bind_unrelated_compiler_fact_to_original_reading_task(coach_case):
    context, baseline, raw = prepared(coach_case)
    raw["explanations"] = [
        {
            "task_id": context.projection.tasks[0].task_id,
            "fact_ids": [f.fact_id for f in context.facts if f.kind in {"goal", "compiler_result"}],
            "reason_code": "compiler_result",
            "method_code": "trace_error",
        }
    ]
    with pytest.raises(
        coach_module("models").OrchestratorError, match="enhancement_evidence_mismatch"
    ):
        coach_module("output").validate_enhancement(context, baseline, raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"explanations":[],"task_order":[],"new_actions":[],"new_actions":[]}',
        "[]",
        '{"explanations":[],"task_order":[],"new_actions":[],"score":NaN}',
    ],
)
def test_malformed_json_is_rejected_without_changing_baseline(coach_context, raw):
    baseline = coach_module("rules").build_rule_proposal(coach_context)
    original = baseline.model_dump()
    with pytest.raises(coach_module("models").OrchestratorError):
        coach_module("output").validate_enhancement(coach_context, baseline, raw)
    assert baseline.model_dump() == original
