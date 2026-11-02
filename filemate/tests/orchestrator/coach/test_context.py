"""Read real stored evidence without sending or persisting model requests."""

import copy
import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from filemate.execution.data_actions import digest
from filemate.interview_coach.models import SubmitAnswer
from filemate.interview_coach.repository import CoachRepository
from filemate.interview_review.models import CONTENT_AREAS
from filemate.tests.orchestrator.conftest import wrong

from .conftest import coach_module, graph_evidence, read_context, short_plan, submission


def test_selected_context_is_one_snapshot_and_minimal(coach_case):
    store = coach_case["storage"]
    store.save_artifact(
        artifact_type="notes",
        content={"code": "synthetic-secret-code", "resume": "synthetic-secret-resume"},
    )
    before = store._conn().total_changes
    value = read_context(coach_case)
    body = json.dumps(value.external_payload, ensure_ascii=False)
    assert value.input.scope.goal_id == coach_case["world"]["goal"]
    assert value.as_of == coach_case["clock"]()
    assert "synthetic-secret-code" not in body and "synthetic-secret-resume" not in body
    assert len(body) <= 24000 and len(body.encode()) <= 65536
    assert store._conn().total_changes == before
    assert len(value.context_revision) == len(value.external_digest) == 64


def test_context_uses_one_snapshot_during_concurrent_source_change(coach_case, monkeypatch):
    module = coach_module("context")
    original = module.SnapshotReader.read_in_transaction
    store = coach_case["storage"]

    def changed(reader, read, *args, **kwargs):
        result = original(reader, read, *args, **kwargs)
        store._conn().execute(
            "UPDATE sources SET original_name='修改后的资料' WHERE source_id=?",
            (coach_case["world"]["sources"][0],),
        )
        store._conn().commit()
        return result

    monkeypatch.setattr(module.SnapshotReader, "read_in_transaction", changed)
    value = read_context(coach_case)
    assert value.snapshot.facts["sources"][0]["original_name"] == "数据结构"
    assert next(f.data.title for f in value.facts if f.kind == "source") == "数据结构"


@pytest.mark.parametrize("field,value", [("source_ids", ["missing"]), ("course_id", "missing")])
def test_selected_foreign_or_missing_scope_is_rejected(coach_case, field, value):
    error = coach_module("models").OrchestratorError
    scope = coach_case["input_data"]["scope"] | {field: value}
    with pytest.raises(error):
        read_context(coach_case, scope=scope)


def test_empty_scope_reads_only_linked_goal_plans(coach_case):
    store = coach_case["storage"]
    goal = store.save_artifact(
        artifact_type="reverse_goal_plan", content={"goal_type": "custom", "tasks": []}
    )
    other = store.save_artifact(artifact_type="reverse_goal_plan", content={"tasks": []})
    own = short_plan(store, goal)
    short_plan(store, other)
    short_plan(store, goal, dependencies=[coach_case["world"]["sources"][1]])
    result = read_context(coach_case, scope={"goal_id": goal})
    assert [p["plan_id"] for p in result.snapshot.facts["plans"]] == [own]


def test_linked_plan_requires_every_source_and_matching_goal(coach_case):
    store, w = coach_case["storage"], coach_case["world"]
    own = short_plan(store, w["goal"], source=w["sources"][0], dependencies=[w["sources"][0]])
    short_plan(store, w["goal"], source=w["sources"][0], dependencies=w["sources"])
    other = store.save_artifact(artifact_type="reverse_goal_plan", content={"tasks": []})
    short_plan(store, other, source=w["sources"][0])
    result = read_context(coach_case)
    assert [p["plan_id"] for p in result.snapshot.facts["plans"]] == [own]


def test_wrong_answer_excerpt_and_full_revision_are_both_checked(coach_case):
    w, store = coach_case["world"], coach_case["storage"]
    wid = wrong(w)
    store._conn().execute("UPDATE quiz_attempts SET user_answer=?", ("甲" * 600,))
    store._conn().commit()
    first = read_context(coach_case, selection={"wrong_ids": [wid]})
    answers = [f for f in first.facts if f.kind == "attempt"]
    assert len(answers) == 1 and len(answers[0].data.answer_excerpt) == 500
    store._conn().execute("UPDATE quiz_attempts SET user_answer=?", ("甲" * 599 + "乙",))
    store._conn().commit()
    second = read_context(coach_case, selection={"wrong_ids": [wid]})
    assert first.context_revision != second.context_revision
    assert first.external_digest != second.external_digest
    assert not any(f.kind == "cause" for f in second.facts)


def feedback(store, source):
    run = store.create_agent_run(
        task_type="interview_session",
        goal="合成答辩",
        selected_agents=[],
        context_refs={"source_id": source},
    )
    sid = store.create_interview(
        target_role="合成答辩",
        scenario="竞赛答辩",
        difficulty="标准",
        questions=["介绍项目"],
        agent_run_id=run["run_id"],
    )["interview_id"]
    repo = CoachRepository(store)
    attempt = repo.submit(
        sid,
        SubmitAnswer(
            answer="我验证了队列边界。",
            question_index=0,
            request_key="coach_evidence_answer_01",
            expected_revision=0,
        ),
    ).snapshot.current_attempt
    analysis = {
        "content_analysis": {
            "source": "llm_reference",
            "keywords": [],
            "dimension_evidence": dict.fromkeys(["内容", "结构", "表达", "岗位匹配"], "队列边界"),
            "areas": {
                area: {"status": "partial", "evidence": "队列边界", "suggestion": "补充验证条件"}
                for area in CONTENT_AREAS
            },
        }
    }
    store._conn().execute(
        """INSERT INTO interview_coach_analysis_runs
        (run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,review_revision,
         provider_identity,model,prompt_version,rubric_version,status,evaluation,created_at)
        VALUES ('synthetic-analysis',?,?,1,'synthetic-analysis-key','hash',1,1,'fixture','fixture','v1','v1','succeeded',?,?)""",
        (sid, attempt.attempt_id, json.dumps(analysis), attempt.created_at),
    )
    store._conn().commit()
    return sid, repo, attempt


def test_feedback_needs_selected_current_attempt(coach_case):
    w, store = coach_case["world"], coach_case["storage"]
    content = store.get_artifact(w["goal"])["content"] | {"goal_type": "competition"}
    store._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps(content), w["goal"])
    )
    store._conn().commit()
    sid, repo, attempt = feedback(store, w["sources"][0])
    selection = {
        "interview_ids": [sid],
        "feedback_refs": [
            {
                "interview_id": sid,
                "attempt_id": attempt.attempt_id,
                "feedback_item_id": "logic",
                "expected_revision": "synthetic-analysis",
            }
        ],
    }
    first = read_context(coach_case, selection=selection)
    facts = [f for f in first.facts if f.kind == "interview_feedback"]
    assert len(facts) == 1 and facts[0].data.quote == "队列边界"
    assert "score" not in json.dumps(first.external_payload)
    state = repo.snapshot(sid)
    repo.submit(
        sid,
        SubmitAnswer(
            answer="这是我的重答。",
            question_index=0,
            expected_attempt_id=attempt.attempt_id,
            expected_revision=state.revision,
            request_key="coach_evidence_answer_02",
        ),
    )
    with pytest.raises(coach_module("models").OrchestratorError):
        read_context(coach_case, selection=selection)


def test_old_dates_and_identity_do_not_reuse_revision(coach_case):
    first = read_context(coach_case)
    coach_case["world"]["now"][0] += timedelta(seconds=1)
    second = read_context(coach_case)
    assert first.context_revision == second.context_revision
    assert first.external_digest == second.external_digest
    coach_case["world"]["now"][0] += timedelta(days=1)
    with pytest.raises(coach_module("models").OrchestratorError):
        read_context(coach_case)


@pytest.mark.parametrize(
    "change",
    [
        {"selection": {"wrong_ids": ["same", "same"]}},
        {"selection": {"submission_ids": ["a"] * 11}},
        {"days": [{"study_date": "2026-10-31", "options": {"available_minutes": True}}]},
        {"workspace": "another-user"},
        {"selection": {"position_id": "p", "requirement_indices": [True]}},
    ],
)
def test_strict_input_rejects_overflow_duplicates_and_extra_fields(coach_case, change):
    model = coach_module("models").CoachInput
    with pytest.raises(ValidationError):
        model.model_validate(coach_case["input_data"] | copy.deepcopy(change))


def test_skill_goal_round_trip_and_legacy_goal_types(coach_case):
    from datetime import date

    from filemate.study.goal_planner import build_reverse_goal_plan
    from filemate.study.orchestrator.context import read_goal_options
    from filemate.study.orchestrator.models import GoalOptionsRequest

    store = coach_case["storage"]
    original = digest(store.get_artifact(coach_case["world"]["goal"])["content"])
    for kind in ("skill", "exam", "competition", "job", "postgraduate", "custom"):
        value = build_reverse_goal_plan(
            title="合成目标-" + kind,
            goal_type=kind,
            deadline=date(2026, 11, 30),
            target_score=None,
            analytics={},
        )
        store.save_artifact(artifact_type="reverse_goal_plan", title=value["title"], content=value)
    choices = read_goal_options(store, GoalOptionsRequest(q="合成目标-")).items
    assert len(choices) == 6 and all(item.valid for item in choices)
    assert {item.goal_type for item in choices} == {
        "skill",
        "exam",
        "competition",
        "job",
        "postgraduate",
        "custom",
    }
    assert digest(store.get_artifact(coach_case["world"]["goal"])["content"]) == original
    assert store.get_schema_version() == 36


def test_linked_plan_cannot_hide_another_course_in_coach_metadata(coach_case):
    store, w = coach_case["storage"], coach_case["world"]
    pid = short_plan(store, w["goal"], source=w["sources"][0])
    aid = store.get_study_plan(pid)["artifact_id"]
    metadata = {"learning_coach": {"goal_id": w["goal"], "course_id": w["courses"][1]}}
    store._conn().execute(
        "UPDATE artifacts SET metadata=? WHERE artifact_id=?", (json.dumps(metadata), aid)
    )
    store._conn().commit()
    assert not read_context(coach_case).snapshot.facts["plans"]


@pytest.mark.parametrize("provider", ["linux-gvisor-gcc", "windows-appcontainer-msvc"])
def test_compiler_evidence_excludes_code_and_ai_score(coach_case, provider):
    row = submission(coach_case["storage"], provider=provider)
    value = read_context(coach_case, selection={"submission_ids": [row["submission_id"]]})
    evidence = [item for item in value.facts if item.kind == "compiler_result"]
    assert len(evidence) == 1 and evidence[0].data.verdict == "CE"
    body = json.dumps(value.external_payload)
    assert "synthetic-secret-code" not in body and "score" not in body


@pytest.mark.parametrize("provider", ["llm", "host-gcc", "unknown"])
def test_model_or_untrusted_judge_is_not_compiler_evidence(coach_case, provider):
    row = submission(coach_case["storage"], provider=provider)
    with pytest.raises(
        coach_module("models").OrchestratorError, match="compiler_evidence_unavailable"
    ):
        read_context(coach_case, selection={"submission_ids": [row["submission_id"]]})


def test_changed_or_retired_problem_invalidates_selected_submission(coach_case):
    store = coach_case["storage"]
    row = submission(store)
    store._conn().execute(
        "UPDATE coding_submissions SET problem_version=999 WHERE submission_id=?",
        (row["submission_id"],),
    )
    store._conn().commit()
    with pytest.raises(coach_module("models").OrchestratorError):
        read_context(coach_case, selection={"submission_ids": [row["submission_id"]]})


def test_position_uses_selected_requirements_and_tracks_full_revision(coach_case):
    from filemate.career.repository import CareerRepository
    from filemate.tests.test_career import imported

    store, goal = coach_case["storage"], coach_case["world"]["goal"]
    current = store.get_artifact(goal)["content"] | {"goal_type": "job"}
    store.update_artifact(goal, title=current["title"], content=current)
    repo = CareerRepository(store)
    position = repo.create(imported(), "coach_job_test_key_01")
    selection = {"position_id": position["position_id"], "requirement_indices": [0]}
    first = read_context(coach_case, selection=selection)
    selected = [item for item in first.facts if item.kind == "position_requirement"]
    assert len(selected) == 1
    assert selected[0].data.quote == position["position"]["requirements"][0]["evidence"]
    assert "description" not in json.dumps(first.external_payload)
    repo.edit(
        position["position_id"],
        position["position"] | {"title": "修订后的合成岗位"},
        position["revision"],
    )
    assert read_context(coach_case, selection=selection).context_revision != first.context_revision
    repo.transition(position["position_id"], "undo")
    with pytest.raises(coach_module("models").OrchestratorError):
        read_context(coach_case, selection=selection)


def test_payload_clipping_has_explicit_coverage_and_both_size_bounds(coach_case):
    from filemate.study.orchestrator.coach.context import external_payload
    from filemate.study.orchestrator.coach.evidence import fact

    value = read_context(coach_case)
    facts = [fact("source", str(i), {"i": i}, {"title": "𠀀" * 240}) for i in range(80)]
    payload = external_payload(value.input, value.snapshot, value.projection, facts)
    encoded = json.dumps(payload, ensure_ascii=False)
    assert len(encoded) <= 24000 and len(encoded.encode("utf-8")) <= 65536
    assert payload["coverage"]["truncated"] and payload["coverage"]["omitted_facts"] > 0


def test_duplicate_keys_in_saved_evidence_are_rejected():
    with pytest.raises(coach_module("models").OrchestratorError):
        coach_module("evidence").decode('{"result":{},"result":{"verdict":"AC"}}')


def test_selected_concepts_include_confirmed_scoped_relation(coach_case):
    ids = graph_evidence(coach_case)
    value = read_context(coach_case, selection={"concept_ids": ids})
    assert len([f for f in value.facts if f.kind == "concept"]) == 2
    edges = [f for f in value.facts if f.kind == "relation"]
    assert len(edges) == 1 and edges[0].data.relation_type == "prerequisite"
    assert edges[0].data.source_ids == [coach_case["world"]["sources"][0]]


def test_stale_source_invalidates_concept_selection(coach_case):
    ids = graph_evidence(coach_case)
    store = coach_case["storage"]
    store._conn().execute(
        "UPDATE sources SET raw_text=? WHERE source_id=?",
        ("变更后的原文", coach_case["world"]["sources"][0]),
    )
    store._conn().commit()
    with pytest.raises(coach_module("models").OrchestratorError):
        read_context(coach_case, selection={"concept_ids": ids})


def test_plan_progress_counts_all_actual_days_not_only_projected_page(coach_case):
    store, w = coach_case["storage"], coach_case["world"]
    pid = short_plan(store, w["goal"], source=w["sources"][0])
    row = store.get_study_plan(pid)
    plan = row["plan_data"] | {"daily_plan": row["plan_data"]["daily_plan"] * 300}
    store._conn().execute(
        "UPDATE study_plans SET plan_data=?,completed_days=? WHERE plan_id=?",
        (json.dumps(plan), "[299]", pid),
    )
    store._conn().commit()
    value = read_context(coach_case)
    evidence = next(f for f in value.facts if f.kind == "plan")
    assert evidence.data.day_count == 300
    assert evidence.data.completed_day_count == 1
    assert value.snapshot.coverage["plans"]["days_truncated"]
