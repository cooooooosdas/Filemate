"""The consented payload contains every exact choice required by strict validation."""

import copy
import json

import pytest

from filemate.execution.data_actions import digest

from .conftest import coach_module, graph_evidence, read_context, submission


def test_previewed_registry_supports_nonempty_valid_model_changes(coach_case):
    nodes = graph_evidence(coach_case)
    context = read_context(coach_case, selection={"concept_ids": nodes})
    payload = context.external_payload
    assert payload["prompt_version"] == "learning-coach-v2"
    baseline = payload["baseline"]
    assert baseline["new_actions"]
    action = copy.deepcopy(baseline["new_actions"][0])
    allowed = next(
        row for row in payload["allowed_actions"] if row["target_ref"] == action["target_ref"]
    )
    action["method_code"] = next(
        method for method in allowed["method_codes"] if method != action["method_code"]
    )
    task = next(row for row in payload["tasks"] if row["allowed_explanations"])
    explanation = copy.deepcopy(task["allowed_explanations"][0])
    explanation["task_id"] = task["task_id"]
    explanation["method_code"] = explanation.pop("method_codes")[0]
    raw = {"explanations": [explanation], "task_order": [], "new_actions": [action]}
    proposal = coach_module("rules").build_rule_proposal(context)
    enhanced = coach_module("output").validate_enhancement(context, proposal, raw)
    changed = next(
        row for row in enhanced.new_actions if row.target_ref.id == action["target_ref"]["id"]
    )
    assert changed.method_code == action["method_code"]
    assert enhanced.days[0].schedule.estimated_minutes <= 40
    assert digest(payload) == context.external_digest
    messages = coach_module("prompts").build_model_messages(context)
    assert json.loads(messages[1]["content"]) == payload
    for day in baseline["days"]:
        actions = [row for row in baseline["new_actions"] if row["study_date"] == day["study_date"]]
        assert (
            day["reserved_minutes"] + sum(row["minutes"] for row in actions)
            == day["estimated_minutes"]
        )
        assert day["estimated_minutes"] <= day["available_minutes"]


def test_clipping_keeps_baseline_and_allowed_references_closed(coach_case):
    from filemate.study.orchestrator.coach.context import external_payload
    from filemate.study.orchestrator.coach.evidence import fact

    nodes = graph_evidence(coach_case)
    context = read_context(coach_case, selection={"concept_ids": nodes})
    facts = context.facts + [
        fact("source", f"large-source-{index}", {"i": index}, {"title": "𠀀" * 240})
        for index in range(80)
    ]
    payload = external_payload(context.input, context.snapshot, context.projection, facts)
    assert payload["coverage"]["truncated"]
    visible = {row["fact_id"] for row in payload["facts"]}
    tasks = {row["task_id"] for row in payload["tasks"]}
    for action in payload["allowed_actions"] + payload["baseline"]["new_actions"]:
        assert set(action["fact_ids"]) <= visible
    for task in payload["tasks"]:
        for option in task["allowed_explanations"]:
            assert set(option["fact_ids"]) <= visible
    for day in payload["baseline"]["days"]:
        assert set(day["selected_task_ids"]) <= tasks
    context.external_payload = payload
    from filemate.study.orchestrator.coach.output import CoachModelOutput

    instruction = "请仅返回符合以下 JSON Schema 的内容，不要额外解释：\n" + json.dumps(
        CoachModelOutput.model_json_schema(), ensure_ascii=False
    )
    full = [
        {"role": "system", "content": instruction},
        *coach_module("prompts").build_model_messages(context),
    ]
    assert len(json.dumps(full, ensure_ascii=False).encode("utf-8")) <= 65536


def test_every_advertised_method_roundtrips_through_actual_validation(coach_case):
    nodes = graph_evidence(coach_case)
    compiled = submission(coach_case["storage"])
    context = read_context(
        coach_case,
        selection={"concept_ids": nodes, "submission_ids": [compiled["submission_id"]]},
        days=[{"study_date": "2026-10-31", "options": {"available_minutes": 180}}],
    )
    baseline = coach_module("rules").build_rule_proposal(context)
    for option in context.external_payload["allowed_actions"]:
        if option["action"] == "train_concept":
            assert option["method_codes"] == ["practice", "reread"]
        for method in option["method_codes"]:
            action = {
                "action": option["action"],
                "target_ref": option["target_ref"],
                "fact_ids": option["fact_ids"],
                "method_code": method,
                "minutes": option["default_minutes"],
                "study_date": "2026-10-31",
            }
            enhanced = coach_module("output").validate_enhancement(
                context, baseline, {"explanations": [], "task_order": [], "new_actions": [action]}
            )
            assert any(
                row.target_ref.model_dump(mode="json") == option["target_ref"]
                and row.method_code == method
                for row in enhanced.new_actions
            )


@pytest.mark.parametrize("mistake", ["short_fact_id", "extra_source_support", "hidden_task"])
def test_inferred_or_unexposed_references_still_fail(coach_case, mistake):
    nodes = graph_evidence(coach_case)
    context = read_context(coach_case, selection={"concept_ids": nodes})
    baseline = coach_module("rules").build_rule_proposal(context)
    action = copy.deepcopy(context.external_payload["baseline"]["new_actions"][0])
    raw = {"explanations": [], "task_order": [], "new_actions": [action]}
    if mistake == "short_fact_id":
        action["fact_ids"][0] = action["fact_ids"][0].rsplit(":", 1)[0]
    elif mistake == "extra_source_support":
        action["fact_ids"].append(
            next(row.fact_id for row in context.facts if row.kind == "source")
        )
    else:
        raw["task_order"] = [context.projection.tasks[0].task_id]
        context.external_payload["tasks"] = []
    with pytest.raises(coach_module("models").OrchestratorError):
        coach_module("output").validate_enhancement(context, baseline, raw)


def test_same_key_after_prompt_upgrade_keeps_history_without_reusing_old_enhancement(
    coach_case, monkeypatch
):
    from .test_requests import CountingRunner, request, service

    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    runner = CountingRunner()
    api = service(coach_case, runner=runner)
    body = request(coach_case, mode="llm")
    original = api.request(body)
    assert original.model_status == "succeeded"
    monkeypatch.setattr(
        coach_module("repository"), "PROMPT_VERSION", "learning-coach-next", raising=False
    )
    with pytest.raises(coach_module("models").OrchestratorError, match="request_conflict"):
        api.request(body)
    assert runner.calls == 1
    reread = api.get(body.request_key)
    assert reread.prompt_version == original.prompt_version == "learning-coach-v2"
    assert reread.proposal == original.proposal


def test_legacy_record_without_prompt_metadata_keeps_its_original_version(coach_case, monkeypatch):
    from .test_requests import request, service

    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    api = service(coach_case)
    body = request(coach_case, mode="llm")
    original = api.request(body)
    repository = coach_module("repository")
    conn = coach_case["storage"]._conn()
    record = json.loads(
        conn.execute(
            "SELECT content FROM artifacts WHERE artifact_id=?", (original.work_id,)
        ).fetchone()[0]
    )
    record.pop("prompt_version")
    record["input_digest"] = digest(body.model_dump(mode="json"))
    result_id = repository.result_id(original.work_id)
    result = json.loads(
        conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (result_id,)).fetchone()[
            0
        ]
    )
    result["proposal"]["prompt_version"] = "learning-coach-v1"
    with conn:
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?",
            (json.dumps(record), original.work_id),
        )
        conn.execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps(result), result_id)
        )
    reread = api.get(body.request_key)
    assert reread.status == "ready"
    assert reread.prompt_version == reread.proposal.prompt_version == "learning-coach-v1"
    with pytest.raises(coach_module("models").OrchestratorError, match="request_conflict"):
        api.request(body)
