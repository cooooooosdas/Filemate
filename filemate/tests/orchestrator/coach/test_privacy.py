# ruff: noqa: F811
"""Erase actual dependent advice while retaining non-replayable request tombstones."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from filemate.study.orchestrator.repository import atomic

from .conftest import coach_module, submission
from .test_requests import CountingRunner, request, service, service_case  # noqa: F401


@pytest.mark.parametrize("index", [0, 1])
def test_delete_either_source_purges_body_but_keeps_tombstone(service_case, index):
    case = service_case
    goal = case["storage"].save_artifact(
        artifact_type="reverse_goal_plan", content={"goal_type": "custom", "tasks": []}
    )
    from filemate.course_graph.repository import CourseGraphRepository

    cid = case["world"]["courses"][0]
    revision = (
        case["storage"]
        ._conn()
        .execute("SELECT revision FROM kg_courses WHERE course_id=?", (cid,))
        .fetchone()[0]
    )
    CourseGraphRepository(case["storage"]).attach_sources(
        cid, [case["world"]["sources"][1]], None, revision
    )
    scope = {"goal_id": goal, "course_id": cid, "source_ids": case["world"]["sources"]}
    case = case | {
        "input_data": case["input_data"] | {"scope": scope, "question": "合成私密问题不可残留"}
    }
    api, body = service(case), request(case)
    result = api.request(body)
    storage = case["storage"]
    preview = storage.preview_source_deletion(scope["source_ids"][index])
    assert preview["affected"]["learning_coach_results"] == 1
    storage.delete_source(scope["source_ids"][index])
    tombstone = api.get(body.request_key)
    assert tombstone.status == "stale" and tombstone.proposal is None
    assert api.request(body).work_id == result.work_id
    assert "合成私密问题不可残留" not in json.dumps(
        [dict(r) for r in storage._conn().execute("SELECT * FROM artifacts")], ensure_ascii=False
    )
    assert not storage._conn().execute("PRAGMA foreign_key_check").fetchall()


def test_running_delete_cannot_publish_a_late_result(service_case):
    runner = CountingRunner(block=True)
    api, body = service(service_case, runner), request(service_case, mode="llm")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api.request, body)
        assert runner.started.wait(5)
        service_case["storage"].delete_source(service_case["world"]["sources"][0])
        runner.release.set()
        assert future.result(timeout=5).status == "stale"
    assert api.get(body.request_key).proposal is None and runner.calls == 1


def test_coding_delete_erases_only_dependent_advice(service_case):
    from filemate.programming.privacy import CodingPrivacy

    storage = service_case["storage"]
    sid = submission(storage)["submission_id"]
    case = service_case | {
        "input_data": service_case["input_data"] | {"selection": {"submission_ids": [sid]}}
    }
    api, body = service(case), request(case)
    api.request(body)
    unrelated = request(service_case, key="synthetic_unrelated_coach")
    service(service_case).request(unrelated)
    privacy = CodingPrivacy(storage)
    p = privacy.preview(sid)
    assert p["learning_coach_results"] == 1
    privacy.delete(sid, p["confirmation_token"])
    assert api.get(body.request_key).status == "stale"
    assert service(service_case).get(unrelated.request_key).status == "ready"


@pytest.mark.parametrize("delete", [False, True])
def test_interview_clear_and_delete_invalidate_derivatives(service_case, delete):
    from filemate.interview_review.repository import ReviewRepository

    from .test_context import feedback

    storage, world = service_case["storage"], service_case["world"]
    goal = storage.get_artifact(world["goal"])
    storage.update_artifact(
        world["goal"], title="", content=goal["content"] | {"goal_type": "competition"}
    )
    sid, _, _ = feedback(storage, world["sources"][0])
    case = service_case | {
        "input_data": service_case["input_data"] | {"selection": {"interview_ids": [sid]}}
    }
    api, body = service(case), request(case)
    api.request(body)
    privacy = ReviewRepository(storage)
    if delete:
        p = privacy.delete_preview(sid)
        assert p["learning_coach_results"] == 1
        privacy.delete(sid, p["confirmation_token"])
    else:
        privacy.clear(sid)
        assert storage.get_interview(sid) is not None
    assert api.get(body.request_key).status == "stale"


@pytest.mark.parametrize("kind", ["attempt", "position", "goal"])
def test_explicit_dependency_erasure_is_transactional_and_keeps_key(service_case, kind):
    privacy = coach_module("privacy")
    storage = service_case["storage"]
    api, body = service(service_case), request(service_case)
    result = api.request(body)
    rid = coach_module("repository").result_id(result.work_id)
    row = storage.get_artifact(rid)
    record = row["content"]
    if kind == "attempt":
        record["proposal"]["facts"].append({"kind": "attempt", "record_id": "synthetic-attempt"})
        identifier = "synthetic-attempt"
    elif kind == "position":
        row["metadata"]["dependencies"]["position_id"] = "synthetic-position"
        identifier = "synthetic-position"
    else:
        identifier = service_case["world"]["goal"]
    with storage._conn() as conn:
        conn.execute(
            "UPDATE artifacts SET content=?,metadata=? WHERE artifact_id=?",
            (json.dumps(record), json.dumps(row["metadata"]), rid),
        )
    with pytest.raises(RuntimeError, match="rollback"), atomic(storage) as conn:
        assert (
            privacy.coach_dependency_impact(conn, kind=kind, record_ids=[identifier])[
                "learning_coach_results"
            ]
            == 1
        )
        privacy.invalidate_coach_dependencies(conn, kind=kind, record_ids=[identifier])
        raise RuntimeError("rollback")
    assert storage.get_artifact(rid) is not None
    with atomic(storage) as conn:
        privacy.invalidate_coach_dependencies(conn, kind=kind, record_ids=[identifier])
    assert storage.get_artifact(rid) is None
    assert api.get(body.request_key).status == "stale"


def test_generic_artifact_paths_cannot_forge_coach_authority(service_case):
    storage = service_case["storage"]
    for kind in (
        "learning_coach_request",
        "learning_coach_result",
        "learning_coach_operation",
        "learning_coach_runtime",
    ):
        with pytest.raises(ValueError):
            storage.save_artifact(artifact_type=kind, content={})
    with pytest.raises(ValueError):
        storage.save_artifact(
            artifact_type="study_plan",
            content={},
            metadata={
                "learning_coach": {"goal_id": "goal", "operation_id": "forged", "version": 1}
            },
        )
    api, body = service(service_case), request(service_case)
    result = api.request(body)
    with pytest.raises(ValueError):
        storage.update_artifact(result.work_id, title="forged", content={})


def test_dependency_erasure_covers_accepted_plan_after_advice_is_gone(service_case):
    from .test_commands import commands, confirm_body
    from .test_plans import ready

    storage = service_case["storage"]
    sid = submission(storage)["submission_id"]
    case = service_case | {
        "input_data": service_case["input_data"] | {"selection": {"submission_ids": [sid]}}
    }
    case, _, draft = ready(case)
    api = commands(case)
    receipt = api.confirm(confirm_body(draft, api.preview(draft)))
    with atomic(storage) as conn:
        conn.execute(
            "DELETE FROM artifacts WHERE artifact_id=?",
            (coach_module("repository").result_id(draft.work_id),),
        )
        impact = coach_module("privacy").invalidate_coach_dependencies(
            conn, kind="submission", record_ids=[sid]
        )
        assert impact["learning_coach_plans"] == 1
    assert storage.get_study_plan(receipt.plan_id) is None
    assert api.find(receipt.request_key).operation_id == receipt.operation_id
    with pytest.raises(coach_module("models").OrchestratorError):
        api.preview_undo(receipt.operation_id)


def test_erasure_handles_all_matching_results_without_page_limit(service_case):
    from filemate.study.orchestrator.repository import put

    storage = service_case["storage"]
    source = service_case["world"]["sources"][0]
    with atomic(storage) as conn:
        for i in range(205):
            put(
                conn,
                f"learning-coach-result-synthetic-{i}",
                "learning_coach_result",
                {"input": {"scope": {"source_ids": [source]}}, "question": "合成清理证据"},
            )
        result = coach_module("privacy").invalidate_coach_dependencies(
            conn, kind="source", record_ids=[source]
        )
        assert result["learning_coach_results"] == 205
    assert (
        not storage._conn()
        .execute("SELECT 1 FROM artifacts WHERE artifact_type='learning_coach_result'")
        .fetchone()
    )


def test_reanswer_marks_saved_advice_stale_without_touching_answer_history(service_case):
    from filemate.interview_coach.models import SubmitAnswer

    from .test_context import feedback

    storage, w = service_case["storage"], service_case["world"]
    goal = storage.get_artifact(w["goal"])
    storage.update_artifact(
        w["goal"], title="", content=goal["content"] | {"goal_type": "competition"}
    )
    sid, repo, attempt = feedback(storage, w["sources"][0])
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
    case = service_case | {"input_data": service_case["input_data"] | {"selection": selection}}
    api, body = service(case), request(case)
    api.request(body)
    state = repo.snapshot(sid)
    repo.submit(
        sid,
        SubmitAnswer(
            answer="这是保留的重答。",
            question_index=0,
            expected_attempt_id=attempt.attempt_id,
            expected_revision=state.revision,
            request_key="synthetic_coach_new_answer",
        ),
    )
    assert api.get(body.request_key).status == "stale"
    assert (
        storage._conn()
        .execute("SELECT count(*) FROM interview_answer_attempts WHERE interview_id=?", (sid,))
        .fetchone()[0]
        == 2
    )


def test_moving_source_out_of_course_marks_advice_stale_but_preserves_source(service_case):
    from filemate.course_graph.privacy import preview_remove_source, remove_source

    storage, w = service_case["storage"], service_case["world"]
    api, body = service(service_case), request(service_case)
    api.request(body)
    preview = preview_remove_source(storage, w["courses"][0], w["sources"][0])
    remove_source(
        storage,
        w["courses"][0],
        w["sources"][0],
        preview["confirmation_token"],
        "synthetic_coach_remove_source",
        True,
    )
    assert api.get(body.request_key).status == "stale"
    assert storage.get_source(w["sources"][0]) is not None


@pytest.mark.parametrize("dependencies", [{"feedback_refs": None}, {"feedback_refs": "broken"}])
def test_malformed_unrelated_coach_metadata_cannot_block_source_erasure(service_case, dependencies):
    from filemate.study.orchestrator.repository import put

    storage = service_case["storage"]
    with atomic(storage) as conn:
        put(
            conn,
            "learning-coach-result-corrupt",
            "learning_coach_result",
            {"proposal": {"facts": [{"kind": [], "record_id": []}]}},
        )
        conn.execute(
            "UPDATE artifacts SET metadata=? WHERE artifact_id=?",
            (json.dumps({"dependencies": dependencies}), "learning-coach-result-corrupt"),
        )
        result = coach_module("privacy").invalidate_coach_dependencies(
            conn, kind="source", record_ids=[service_case["world"]["sources"][0]]
        )
        assert result["learning_coach_results"] == 0
