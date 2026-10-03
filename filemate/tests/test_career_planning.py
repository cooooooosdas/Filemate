"""岗位证据到学习计划的合成回归，不代表真实学习效果。"""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from filemate.career.planning import CareerPlans
from filemate.programming.problems import get_problem
from filemate.programming.repository import CodingRepository
from filemate.study.knowledge_graph import extract_local, validate_graph
from filemate.tests.test_career import answers, api, imported, position, repo, start, storage

__all__ = ["api", "repo", "storage"]


def test_preview_is_deterministic_read_only_and_pending_without_answers(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    before = storage._conn().total_changes
    preview = plans.preview(row["position_id"])
    assert preview == plans.preview(row["position_id"])
    assert 1 <= len(preview["steps"]) <= 7
    assert all(step["status"] == "待评测" for step in preview["steps"])
    assert all(
        step["requirement_quote"] in row["position"]["description"] for step in preview["steps"]
    )
    assert storage._conn().total_changes == before
    assert plans.list(row["position_id"]) == []


def test_latest_written_answer_updates_suggestion_and_stale_preview_rejected(repo):
    row = position(repo)
    plans = CareerPlans(repo)
    old = plans.preview(row["position_id"])
    training = start(repo, row)
    actual = answers(training) | {"network": 0}
    repo.answer_written(training["training_id"], actual)
    preview = plans.preview(row["position_id"])
    assert preview["steps"][0]["label"] == "计算机网络"
    assert preview["steps"][0]["status"] == "建议复练"
    assert training["training_id"] in preview["steps"][0]["reason"]
    with pytest.raises(ValueError, match="证据已变化"):
        plans.save(row["position_id"], old["evidence_revision"])
    newer = start(repo, row, key="newest_career_answers_12345678")
    repo.answer_written(newer["training_id"], answers(newer))
    refreshed = plans.preview(row["position_id"])
    network = next(step for step in refreshed["steps"] if step["label"] == "计算机网络")
    assert network["status"] == "继续验证"
    assert newer["training_id"] in network["reason"]


def test_save_once_is_atomic_and_retry_preserves_progress_and_archived_state(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    preview = plans.preview(row["position_id"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(
            pool.map(
                lambda _: plans.save(row["position_id"], preview["evidence_revision"]), range(4)
            )
        )
    assert len({plan["plan_id"] for plan in saved}) == 1
    plan = saved[0]
    assert storage.get_study_plan(plan["plan_id"])["plan_data"] == preview["plan"]
    storage.set_study_plan_day(plan["plan_id"], 0, True)
    archived = plans.transition(row["position_id"], plan["plan_id"], "undo")
    assert archived["status"] == "archived" and archived["completed_days"] == [0]
    assert plans.save(row["position_id"], preview["evidence_revision"])["status"] == "archived"
    assert plans.transition(row["position_id"], plan["plan_id"], "undo") == archived
    restored = plans.transition(row["position_id"], plan["plan_id"], "restore")
    assert restored["completed_days"] == [0] and restored["status"] == "active"
    assert len(plans.list(row["position_id"])) == 1


def test_failed_plan_insert_rolls_back_artifact_and_event(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    preview = plans.preview(row["position_id"])
    conn = storage._conn()
    before = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    conn.execute(
        "CREATE TRIGGER career_plan_failure BEFORE INSERT ON study_plans BEGIN SELECT RAISE(ABORT,'synthetic plan failure'); END"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        plans.save(row["position_id"], preview["evidence_revision"])
    assert conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == before
    assert plans.list(row["position_id"]) == []
    assert all(event["action"] != "plan_saved" for event in repo.events())


def test_role_edit_undo_and_unrelated_plan_ownership(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    preview = plans.preview(row["position_id"])
    saved = plans.save(row["position_id"], preview["evidence_revision"])
    other = repo.create(imported(), "different_plan_owner_12345678")
    with pytest.raises(KeyError):
        plans.transition(other["position_id"], saved["plan_id"], "undo")
    repo.edit(row["position_id"], imported() | {"title": "修订后的岗位"}, 1)
    assert (
        plans.save(row["position_id"], preview["evidence_revision"])["plan_id"] == saved["plan_id"]
    )
    fresh = plans.preview(row["position_id"])
    repo.transition(row["position_id"], "undo")
    with pytest.raises(ValueError, match="已撤销"):
        plans.save(row["position_id"], fresh["evidence_revision"])
    assert plans.list(row["position_id"])[0]["plan_id"] == saved["plan_id"]


def test_delete_preview_binds_plan_progress_and_deletes_only_owned_plan(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    saved = plans.save(row["position_id"], plans.preview(row["position_id"])["evidence_revision"])
    other = repo.create(imported(), "different_delete_plan_12345678")
    retained = plans.save(
        other["position_id"], plans.preview(other["position_id"])["evidence_revision"]
    )
    old = repo.preview_delete(row["position_id"])
    assert old["learning_plan_count"] == 1
    storage.set_study_plan_day(saved["plan_id"], 0, True)
    with pytest.raises(ValueError, match="重新预览"):
        repo.delete(row["position_id"], old["confirmation_token"])
    repo.delete(row["position_id"], repo.preview_delete(row["position_id"])["confirmation_token"])
    assert storage.get_study_plan(saved["plan_id"]) is None
    assert storage.get_artifact(saved["artifact_id"]) is None
    assert storage.get_study_plan(retained["plan_id"]) is not None


def test_damaged_plan_is_visible_preserved_and_cannot_restore(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    saved = plans.save(row["position_id"], plans.preview(row["position_id"])["evidence_revision"])
    conn = storage._conn()
    conn.execute("UPDATE study_plans SET plan_data='broken' WHERE plan_id=?", (saved["plan_id"],))
    conn.commit()
    assert plans.list(row["position_id"])[0]["data_error"] is True
    plans.transition(row["position_id"], saved["plan_id"], "undo")
    with pytest.raises(ValueError, match="异常"):
        plans.transition(row["position_id"], saved["plan_id"], "restore")
    assert (
        conn.execute(
            "SELECT plan_data FROM study_plans WHERE plan_id=?", (saved["plan_id"],)
        ).fetchone()[0]
        == "broken"
    )


def test_api_confirmation_protected_artifact_and_disabled_contract(api, monkeypatch):
    client, _ = api
    row = client.post(
        "/api/career/positions",
        json={"position": imported(), "confirmed": True, "request_key": "plan_api_owner_12345678"},
    ).json()["data"]
    prefix = f"/api/career/positions/{row['position_id']}"
    preview = client.get(prefix + "/plan-preview").json()["data"]
    body = {"evidence_revision": preview["evidence_revision"]}
    assert client.post(prefix + "/plans", json=body).status_code == 422
    saved = client.post(prefix + "/plans", json=body | {"confirmed": True}).json()["data"]
    assert client.get(f"/study-plans/{saved['plan_id']}").status_code == 200
    assert (
        client.patch(
            f"/knowledge/artifacts/{saved['artifact_id']}",
            json={"title": "覆盖建议", "content": "{}"},
        ).status_code
        == 409
    )
    assert client.post(prefix + f"/plans/{saved['plan_id']}/undo", json={}).status_code == 422
    monkeypatch.setenv("FILEMATE_ENABLE_CAREER", "0")
    for method, route, data in [
        ("get", "/plan-preview", None),
        ("get", "/plans", None),
        ("post", "/plans", body | {"confirmed": True}),
        ("post", f"/plans/{saved['plan_id']}/undo", {"confirmed": True}),
    ]:
        assert client.request(method, prefix + route, json=data).status_code == 503


@pytest.mark.parametrize("damage", ["day", "route", "progress", "metadata"])
def test_malformed_plan_preserves_raw_and_can_be_deleted(repo, storage, damage):
    row = position(repo)
    plans = CareerPlans(repo)
    saved = plans.save(row["position_id"], plans.preview(row["position_id"])["evidence_revision"])
    content = saved["plan_data"]
    conn = storage._conn()
    if damage == "day":
        content["daily_plan"][0] = None
    elif damage == "route":
        content["daily_plan"][0]["training_actions"][0]["route"] = "https://example.com/private"
    elif damage == "progress":
        conn.execute(
            "UPDATE study_plans SET completed_days='[999]' WHERE plan_id=?", (saved["plan_id"],)
        )
    else:
        conn.execute(
            "UPDATE artifacts SET metadata='broken' WHERE artifact_id=?", (saved["artifact_id"],)
        )
    encoded = json.dumps(content)
    conn.execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", (encoded, saved["artifact_id"])
    )
    conn.execute("UPDATE study_plans SET plan_data=? WHERE plan_id=?", (encoded, saved["plan_id"]))
    conn.commit()
    assert plans.list(row["position_id"])[0]["data_error"]
    assert repo.preview_delete(row["position_id"])["learning_plan_count"] == 1
    assert (
        conn.execute(
            "SELECT plan_data FROM study_plans WHERE plan_id=?", (saved["plan_id"],)
        ).fetchone()[0]
        == encoded
    )
    repo.delete(row["position_id"], repo.preview_delete(row["position_id"])["confirmation_token"])
    assert storage.get_study_plan(saved["plan_id"]) is None


def test_old_and_future_answers_are_dated_or_excluded(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    training = start(repo, row)
    repo.answer_written(training["training_id"], answers(training) | {"network": 0})
    payload = storage.get_artifact(training["artifact_id"])["content"]
    old_date = datetime.now(timezone.utc) - timedelta(days=180)
    payload["result"]["submitted_at"] = old_date.isoformat()
    storage._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?",
        (json.dumps(payload), training["artifact_id"]),
    )
    storage._conn().commit()
    assert plans.preview(row["position_id"])["steps"][0]["status"] == "建议复练"
    assert old_date.date().isoformat() in plans.preview(row["position_id"])["steps"][0]["reason"]
    payload["result"]["submitted_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    storage._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?",
        (json.dumps(payload), training["artifact_id"]),
    )
    storage._conn().commit()
    assert all(step["status"] == "待评测" for step in plans.preview(row["position_id"])["steps"])


@pytest.mark.parametrize("api", ["anonymous"], indirect=True)
def test_other_anonymous_device_cannot_read_or_mutate_plan(api):
    client, module = api
    row = client.post(
        "/api/career/positions",
        json={
            "position": imported(),
            "confirmed": True,
            "request_key": "private_career_plan_12345678",
        },
    ).json()["data"]
    prefix = f"/api/career/positions/{row['position_id']}"
    revision = client.get(prefix + "/plan-preview").json()["data"]["evidence_revision"]
    body = {"confirmed": True, "evidence_revision": revision}
    saved = client.post(prefix + "/plans", json=body).json()["data"]
    with TestClient(module.app) as other:
        for method, route, data in [
            ("get", "/plans", None),
            ("get", "/plan-preview", None),
            ("post", "/plans", body),
            ("post", f"/plans/{saved['plan_id']}/undo", {"confirmed": True}),
        ]:
            assert other.request(method, prefix + route, json=data).status_code == 404
        assert other.get(f"/study-plans/{saved['plan_id']}").status_code == 404


@pytest.mark.parametrize("kind", ["graph", "coding"])
def test_actual_graph_or_code_error_updates_plan_and_recovery(repo, storage, kind):
    row = position(repo)
    plans = CareerPlans(repo)
    before = plans.preview(row["position_id"])
    if kind == "graph":
        text = "数据结构：用于组织和存储数据的方法。"
        sid = storage.save_source(
            original_name="合成计划资料.txt", source_path="synthetic.txt", raw_text=text
        )
        batch = storage.save_graph_batch(
            sid,
            storage.get_source_revision(sid),
            "local",
            validate_graph(extract_local(text), text, sid, []),
        )
        storage.transition_graph_batch(batch["batch_id"], "confirm")
        aid = storage.save_artifact(
            artifact_type="questions",
            source_id=sid,
            content=[{"knowledge_point": "数据结构", "question": "用途？", "answer": "组织数据"}],
        )

        def practice(correct):
            storage.record_quiz_attempt(
                artifact_id=aid,
                question_index=0,
                user_answer="组织数据" if correct else "不确定",
                is_correct=correct,
                score=int(correct),
                feedback="合成计划回归",
            )

        practice(False)
    else:
        coding = CodingRepository(storage)
        submission = coding.create(
            get_problem("array-sum"), "合成编程证据", "career_plan_code_12345678"
        )
        coding.update(
            submission["submission_id"], status="completed", payload={"result": {"verdict": "WA"}}
        )
    changed = plans.preview(row["position_id"])
    assert changed["evidence_revision"] != before["evidence_revision"]
    assert changed["steps"][0]["status"] == "建议复练"
    if kind == "graph":
        assert any(
            action["route"].startswith("/knowledge-graph?")
            for action in changed["steps"][0]["actions"]
        )
        practice(True)
        practice(True)
    else:
        assert submission["submission_id"] in changed["steps"][0]["reason"]
        coding.transition(submission["submission_id"], "undo")
    recovered = plans.preview(row["position_id"])
    assert all(step["status"] != "建议复练" for step in recovered["steps"])


def test_completed_plan_restore_stays_completed_and_timestamp_is_aware(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    saved = plans.save(row["position_id"], plans.preview(row["position_id"])["evidence_revision"])
    assert datetime.fromisoformat(saved["created_at"]).tzinfo is not None
    for index in range(len(saved["plan_data"]["daily_plan"])):
        storage.set_study_plan_day(saved["plan_id"], index, True)
    plans.transition(row["position_id"], saved["plan_id"], "undo")
    assert (
        plans.transition(row["position_id"], saved["plan_id"], "restore")["status"] == "completed"
    )


def test_same_second_answers_follow_persistent_submission_order(repo, storage):
    row = position(repo)
    plans = CareerPlans(repo)
    timestamp = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    for index in range(2):
        training = start(repo, row, key=f"same_second_plan_{index}_12345678")
        repo.answer_written(
            training["training_id"], answers(training) | {"network": 0 if index == 0 else 2}
        )
        payload = storage.get_artifact(training["artifact_id"])["content"]
        payload["result"]["submitted_at"] = timestamp
        storage._conn().execute(
            "UPDATE artifacts SET content=? WHERE artifact_id=?",
            (json.dumps(payload), training["artifact_id"]),
        )
        storage._conn().commit()
    network = next(
        step for step in plans.preview(row["position_id"])["steps"] if step["label"] == "计算机网络"
    )
    assert network["status"] == "继续验证" and training["training_id"] in network["reason"]


def test_many_unmapped_requirements_are_pending_and_plan_is_bounded(repo):
    requirements = [
        {"label": f"自定义技能{index}", "category": "knowledge", "evidence": f"自定义技能{index}；"}
        for index in range(30)
    ]
    row = repo.create(
        imported()
        | {
            "description": "岗位要求：" + "".join(item["evidence"] for item in requirements),
            "requirements": requirements,
        },
        "many_pending_plan_12345678",
    )
    preview = CareerPlans(repo).preview(row["position_id"])
    assert preview["requirements_total"] == 30 and len(preview["steps"]) == 7
    assert all(step["status"] == "待评测" for step in preview["steps"])
    assert len(row["position"]["requirements"]) == 30
