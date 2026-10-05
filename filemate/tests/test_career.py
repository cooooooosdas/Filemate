"""求职训练中心的合成生命周期和接口回归，不代表招聘效果评测。"""

import copy
import importlib
import json
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from filemate.career.catalog import CATALOG, extract_requirements
from filemate.career.evidence import basic_questions
from filemate.career.models import Position
from filemate.career.repository import CareerRepository
from filemate.execution.storage import _MIGRATIONS, SQLiteStorage
from filemate.programming.problems import get_problem
from filemate.programming.repository import CodingRepository
from filemate.study.knowledge_graph import extract_local, validate_graph


@pytest.fixture
def storage(tmp_path):
    store = SQLiteStorage(tmp_path / "career.db")
    store.init_schema()
    yield store
    store.close()


@pytest.fixture
def repo(storage):
    return CareerRepository(storage)


def imported():
    return CATALOG[0] | {"source_kind": "user_import", "source": "合成回归岗位资料"}


def position(repo):
    return repo.create(imported(), "position_key_12345678")


def start(repo, row, kind="written", key="training_key_12345678"):
    return repo.start(row["position_id"], kind, key, row["revision"])


def answers(training):
    return {q["id"]: q["correct"] for q in basic_questions(training["payload"]["position"])}


@pytest.mark.parametrize(
    "change",
    [
        {"company": " "},
        {"title": "x" * 101},
        {"description": "短"},
        {"requirements": []},
        {"unknown": "extra"},
        {"source_url": "http://example.com"},
        {"source_url": "https://name:secret@example.com"},
        {"source_url": "javascript:alert(1)"},
        {"collected_at": "2026-01-01T00:00:00"},
        {"collected_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
        {
            "requirements": [
                {"label": "数据库", "category": "knowledge", "evidence": "不存在的原句"}
            ]
        },
        {"requirements": [CATALOG[0]["requirements"][0]] * 2},
    ],
)
def test_invalid_position_is_rejected(change):
    with pytest.raises(ValidationError):
        Position.model_validate(imported() | change)


def test_catalog_and_local_extract_have_real_origin_and_no_invented_skill(repo):
    assert len(CATALOG) == 3 and len({p["company"] for p in CATALOG}) == 2
    for index, item in enumerate(CATALOG):
        assert Position.model_validate(item).source_kind == "official_snapshot"
        assert all(r["evidence"] in item["description"] for r in item["requirements"])
        repo.create(item, f"catalog_key_12345678_{index}")
    with pytest.raises(ValueError, match="官方来源"):
        repo.create(CATALOG[0] | {"title": "未经核对的修改"}, "invalid_key_12345678")
    text = "岗位需要Python、算法和数据结构，具备项目实践与沟通能力。"
    extracted = extract_requirements(text)
    assert {r["label"] for r in extracted} >= {"Python", "算法", "数据结构"}
    assert all(r["evidence"] in text for r in extracted)
    assert extract_requirements("负责校园园艺工作，定期照料花草。") == []


def test_case_insensitive_language_keeps_actual_quote_and_excludes_javascript():
    text = "岗位要求掌握python与c++，前端使用JavaScript。"
    extracted = extract_requirements(text)
    assert {r["label"] for r in extracted} == {"Python", "C++"}
    assert next(r for r in extracted if r["label"] == "Python")["evidence"] == "python"
    assert all(r["evidence"] in text for r in extracted)


def test_unmapped_position_still_supports_interview_and_pending_review(repo):
    data = imported() | {
        "description": "岗位要求具备绘画实践与创作经历。",
        "requirements": [{"label": "绘画", "category": "project", "evidence": "绘画实践"}],
    }
    row = repo.create(data, "unmapped_position_12345678")
    with pytest.raises(ValueError, match="没有.*原创训练题"):
        start(repo, row)
    assert len(repo.trainings(row["position_id"])) == 0
    assert start(repo, row, "interview")["interview_id"]
    review = start(repo, row, "review", "unmapped_review_12345678")
    assert review["payload"]["comparison"]["skills"][0]["status"] == "待评测"


@pytest.mark.parametrize(
    "status,verdict",
    [("queued", "AC"), ("failed", "SYS"), ("cancelled", "AC"), ("completed", "SYS")],
)
def test_unfinished_cancelled_and_infrastructure_failures_do_not_become_evidence(
    repo, storage, status, verdict
):
    row = position(repo)
    coding = CodingRepository(storage)
    record = coding.create(get_problem("array-sum"), "合成代码", "excluded_coding_12345678")
    coding.update(record["submission_id"], status=status, payload={"result": {"verdict": verdict}})
    assert all(s["coding_count"] == 0 for s in repo.comparison(row["position_id"])["skills"])


def test_create_edit_retry_and_historical_snapshot_are_independent(repo):
    row = position(repo)
    assert position(repo)["position_id"] == row["position_id"]
    assert len(repo.list()) == 1
    with pytest.raises(ValueError, match="保存键"):
        repo.create(imported() | {"title": "新名称"}, "position_key_12345678")
    training = start(repo, row)
    new = imported() | {"title": "核对后改名"}
    changed = repo.edit(row["position_id"], new, 1)
    assert changed["revision"] == 2
    assert repo.edit(row["position_id"], new, 1)["revision"] == 2
    with pytest.raises(ValueError, match="已更新"):
        repo.edit(row["position_id"], imported(), 1)
    assert (
        repo.training(training["training_id"])["payload"]["position"]["title"]
        == row["position"]["title"]
    )
    assert start(repo, row)["training_id"] == training["training_id"]
    with pytest.raises(ValueError, match="已更新"):
        start(repo, row, key="fresh_training_key_12345678")


def test_undo_restore_is_idempotent_and_keeps_old_training(repo):
    row = position(repo)
    training = start(repo, row)
    identifier = row["position_id"]
    assert repo.transition(identifier, "undo")["revision"] == 2
    assert repo.transition(identifier, "undo")["revision"] == 2
    with pytest.raises(ValueError, match="已撤销"):
        repo.start(identifier, "review", "other_key_12345678", 2)
    assert repo.training(training["training_id"])["data_error"] is False
    assert repo.transition(identifier, "restore")["revision"] == 3
    assert repo.transition(identifier, "restore")["revision"] == 3
    assert [e["action"] for e in repo.events()].count("restore") == 1


def test_written_score_requires_complete_valid_answers_and_is_idempotent(repo):
    row = position(repo)
    training = start(repo, row)
    identifier = training["training_id"]
    assert all(
        "correct" not in q and "explanation" not in q for q in training["payload"]["questions"]
    )
    correct = answers(training)
    for invalid in [
        {},
        {"no_question": 1},
        correct | {next(iter(correct)): 99},
        correct | {next(iter(correct)): True},
    ]:
        with pytest.raises(ValueError):
            repo.answer_written(identifier, invalid)
    submitted = repo.answer_written(identifier, correct)
    result = submitted["payload"]["result"]
    assert result["correct"] == result["total"] and result["correct_rate"] == 1
    assert repo.answer_written(identifier, correct) == submitted
    with pytest.raises(ValueError, match="已经提交"):
        repo.answer_written(identifier, {q: 0 for q in correct})
    assert [e["action"] for e in repo.events()].count("written_submitted") == 1
    evidence = repo.comparison(row["position_id"])
    assert len(evidence["written"]) == 1
    assert sum(s["written_count"] for s in evidence["skills"]) == result["total"]


def test_empty_evidence_stays_pending_and_review_is_frozen(repo):
    row = position(repo)
    evidence = repo.comparison(row["position_id"])
    assert all(
        s["status"] == "待评测" and s["coding_count"] == 0 and s["written_count"] == 0
        for s in evidence["skills"]
    )
    assert evidence["interviews"] == [] and evidence["written"] == []
    snapshot = start(repo, row, "review")
    written = start(repo, row, key="written_second_12345678")
    repo.answer_written(written["training_id"], answers(written))
    assert repo.comparison(row["position_id"])["written"]
    assert repo.training(snapshot["training_id"]) == snapshot


def test_graph_coding_and_actual_interview_evidence_remain_traceable(repo, storage):
    row = position(repo)
    text = "数据结构：用于组织和存储数据的方法。"
    sid = storage.save_source(
        original_name="合成笔记.txt", source_path="synthetic.txt", raw_text=text
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
    storage.record_quiz_attempt(
        artifact_id=aid,
        question_index=0,
        user_answer="组织数据",
        is_correct=True,
        score=1,
        feedback="正确",
    )
    coding = CodingRepository(storage)
    submission = coding.create(get_problem("array-sum"), "synthetic", "coding_key_12345678")
    coding.update(
        submission["submission_id"], status="completed", payload={"result": {"verdict": "AC"}}
    )
    session = start(repo, row, "interview")
    interview = storage.get_interview(session["interview_id"])
    assert (
        len(interview["questions"]) == 5 and row["position"]["company"] in interview["questions"][0]
    )
    run = storage.get_agent_run(interview["agent_run_id"])
    assert run["context_refs"]["allow_external_analysis"] is False
    storage.save_interview_turn(
        interview_id=interview["interview_id"],
        question_index=0,
        question=interview["questions"][0],
        answer="合成项目证据",
        score=None,
        dimensions={},
        feedback="仅记录",
        scoring_mode="local_fallback",
    )
    evidence = repo.comparison(row["position_id"])
    skill = next(s for s in evidence["skills"] if s["label"] == "数据结构")
    assert skill["graph_nodes"][0]["source_id"] == sid and skill["recent_graph_samples"] == 1
    assert skill["coding_count"] == 1 and skill["coding_ac_count"] == 1
    assert skill["coding_evidence"][0]["submission_id"] == submission["submission_id"]
    assert evidence["interviews"][0]["answered"] == 1 and evidence["interviews"][0]["assessed"] == 0
    coding.transition(submission["submission_id"], "undo")
    assert (
        next(s for s in repo.comparison(row["position_id"])["skills"] if s["label"] == "数据结构")[
            "coding_count"
        ]
        == 0
    )


def test_concurrent_training_creates_one_interview_agent_and_artifact(repo, storage):
    row = position(repo)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: start(repo, row, "interview"), range(4)))
    assert len({r["training_id"] for r in records}) == 1
    for table in ("career_trainings", "interview_sessions", "agent_runs", "agent_steps"):
        assert storage._conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
    assert len(storage.list_artifacts(artifact_type="career_training")) == 1


def test_failed_atomic_training_leaves_no_orphan_records(repo, storage):
    row = position(repo)
    storage._conn().execute(
        "CREATE TRIGGER career_fail BEFORE INSERT ON artifacts "
        "WHEN NEW.artifact_type='career_training' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"
    )
    storage._conn().commit()
    with pytest.raises(sqlite3.IntegrityError, match="synthetic failure"):
        start(repo, row, "interview")
    for table in ("career_trainings", "interview_sessions", "agent_runs", "agent_steps"):
        assert storage._conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert repo.get(row["position_id"])["active"] == 1
    assert [e["action"] for e in repo.events()] == ["created"]


@pytest.mark.parametrize("kind", ["written", "review"])
def test_damaged_training_is_not_silently_repaired(repo, storage, kind):
    row = position(repo)
    training = start(repo, row, kind)
    storage._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?",
        ('{"version":"2.5"}', training["artifact_id"]),
    )
    storage._conn().commit()
    assert repo.training(training["training_id"])["data_error"] is True
    with pytest.raises(ValueError):
        repo.answer_written(training["training_id"], {"stack": 1})
    assert storage.get_artifact(training["artifact_id"])["content"] == {"version": "2.5"}


def test_damaged_position_preserves_original_bytes(repo, storage):
    row = position(repo)
    storage._conn().execute(
        "UPDATE career_positions SET payload='bad bytes' WHERE position_id=?", (row["position_id"],)
    )
    storage._conn().commit()
    assert repo.list()[0]["data_error"] is True
    with pytest.raises(ValueError, match="数据异常"):
        start(repo, row)
    repo.transition(row["position_id"], "undo")
    with pytest.raises(ValueError, match="不能恢复"):
        repo.transition(row["position_id"], "restore")
    assert (
        storage._conn().execute("SELECT payload FROM career_positions").fetchone()[0] == "bad bytes"
    )


def test_delete_preview_stales_after_answer_and_delete_preserves_other_domains(repo, storage):
    row = position(repo)
    written = start(repo, row)
    interview = start(repo, row, "interview", "interview_key_12345678")
    other = repo.create(imported() | {"title": "另一个岗位"}, "other_position_12345678")
    old = repo.preview_delete(row["position_id"])
    repo.answer_written(written["training_id"], answers(written))
    with pytest.raises(ValueError, match="重新预览"):
        repo.delete(row["position_id"], old["confirmation_token"])
    preview = repo.preview_delete(row["position_id"])
    assert preview["training_count"] == 2
    assert repo.delete(row["position_id"], preview["confirmation_token"])["deleted"]
    assert repo.delete(row["position_id"], preview["confirmation_token"])["deleted"]
    assert storage.get_interview(interview["interview_id"])
    assert len(storage.list_artifacts(artifact_type="career_training")) == 0
    assert repo.get(other["position_id"])["active"] == 1
    event = next(e for e in repo.events() if e["action"] == "position_deleted")
    assert event["position_id"] is None and event["training_id"] is None
    assert "company" not in event["detail"]


def test_v23_database_upgrades_without_rewriting_existing_interview(tmp_path):
    db = tmp_path / "v23.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)"
        )
        for version, name, script in _MIGRATIONS:
            if version > 23:
                break
            conn.executescript(script)
            conn.execute(
                "INSERT INTO schema_migrations(version,name) VALUES (?,?)", (version, name)
            )
        conn.execute(
            "INSERT INTO interview_sessions(interview_id,target_role,scenario,difficulty,questions) "
            "VALUES('old','后端','求职面试','标准','[\"旧问题\"]')"
        )
    store = SQLiteStorage(db)
    try:
        store.init_schema()
        store.init_schema()
        assert store.get_schema_version() == 26 and store.get_interview("old")["questions"] == [
            "旧问题"
        ]
        row = CareerRepository(store).create(imported(), "reopen_position_12345678")
    finally:
        store.close()
    reopened = SQLiteStorage(db)
    try:
        reopened.init_schema()
        assert CareerRepository(reopened).get(row["position_id"])["position"] == imported()
    finally:
        reopened.close()


def test_growth_overview_empty_then_tracks_actual_training_and_original_refs(repo, storage):
    empty = repo.overview()
    assert all(value == 0 for value in empty["counts"].values())
    assert empty["updated_at"] is None and empty["recent"] == []
    row = position(repo)
    written = start(repo, row)
    assert repo.overview()["counts"]["completed_written"] == 0
    repo.answer_written(written["training_id"], answers(written))
    interview = start(repo, row, "interview", "growth_interview_12345678")
    session = storage.get_interview(interview["interview_id"])
    storage.save_interview_turn(
        interview_id=session["interview_id"],
        question_index=0,
        question=session["questions"][0],
        answer="合成成长作答",
        score=None,
        dimensions={},
        feedback="仅记录",
        scoring_mode="local_fallback",
    )
    start(repo, row, "review", "growth_review_12345678")
    result = repo.overview()
    assert result["counts"] == {
        "positions": 1,
        "active_positions": 1,
        "trainings": 3,
        "completed_written": 1,
        "written_answers": 4,
        "written_correct": 4,
        "interviews": 1,
        "interview_answers": 1,
        "assessed_answers": 0,
        "review_snapshots": 1,
        "excluded_records": 0,
    }
    assert result["updated_at"] and len(result["recent"]) == 3
    assert all(t["position_id"] == row["position_id"] for t in result["recent"])
    assert repo.overview() == result
    repo.transition(row["position_id"], "undo")
    undone = repo.overview()
    assert undone["counts"]["active_positions"] == 0 and undone["counts"]["written_answers"] == 4
    repo.delete(row["position_id"], repo.preview_delete(row["position_id"])["confirmation_token"])
    assert repo.overview() == empty
    assert storage.get_interview(interview["interview_id"])


def test_growth_overview_counts_more_than_display_history_limit(repo):
    row = position(repo)
    for index in range(105):
        training = start(repo, row, key=f"growth_written_key_{index:016d}")
        repo.answer_written(training["training_id"], answers(training))
    result = repo.overview()
    assert result["counts"]["completed_written"] == 105
    assert result["counts"]["written_answers"] == 420
    assert len(result["recent"]) == 5 and len(repo.trainings(row["position_id"])) == 100


def test_growth_overview_excludes_damaged_payload_and_preserves_bytes(repo, storage):
    row = position(repo)
    training = start(repo, row)
    repo.answer_written(training["training_id"], answers(training))
    raw = storage.get_artifact(training["artifact_id"])["content"]
    raw["result"]["submitted_at"] = ["corrupt timestamp"]
    encoded = json.dumps(raw)
    storage._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", (encoded, training["artifact_id"])
    )
    storage._conn().commit()
    result = repo.overview()
    assert result["counts"]["excluded_records"] == 1
    assert result["counts"]["completed_written"] == 0 and result["recent"] == []
    assert (
        storage._conn()
        .execute("SELECT content FROM artifacts WHERE artifact_id=?", (training["artifact_id"],))
        .fetchone()[0]
        == encoded
    )


@pytest.fixture
def api(storage, monkeypatch, tmp_path, request):
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "bootstrap.db"))
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", getattr(request, "param", "local"))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    module._storage.close()
    module._storage = module._StorageRouter(storage)
    with TestClient(module.app) as client:
        yield client, module
    sys.modules.pop("server", None)


def create_api(client):
    response = client.post(
        "/api/career/positions",
        json={"position": imported(), "confirmed": True, "request_key": "api_position_12345678"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def start_api(client, row, kind="written"):
    response = client.post(
        f"/api/career/positions/{row['position_id']}/trainings",
        json={
            "kind": kind,
            "confirmed": True,
            "expected_revision": row["revision"],
            "request_key": "api_training_12345678",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_api_confirmation_exports_protection_and_strict_answer_types(api):
    client, _ = api
    assert client.get("/api/career/positions").json()["data"] == []
    assert len(client.get("/api/career/catalog").json()["data"]) == 3
    assert (
        client.post(
            "/api/career/positions",
            json={"position": imported(), "request_key": "unconfirmed_12345678"},
        ).status_code
        == 422
    )
    assert client.get("/api/career/positions").json()["data"] == []
    row = create_api(client)
    training = start_api(client, row)
    identifier = training["training_id"]
    export = client.get(f"/api/career/trainings/{identifier}/export")
    assert export.status_code == 200 and export.headers["Cache-Control"] == "no-store"
    assert all("correct" not in q for q in export.json()["payload"]["questions"])
    for invalid in [True, "1", 1.5]:
        assert (
            client.post(
                f"/api/career/trainings/{identifier}/answers", json={"answers": {"stack": invalid}}
            ).status_code
            == 422
        )
    assert (
        client.post(
            f"/api/career/trainings/{identifier}/answers", json={"answers": answers(training)}
        ).status_code
        == 200
    )
    markdown = client.get(f"/api/career/trainings/{identifier}/export?format=markdown")
    assert (
        "训练快照" in markdown.text
        and "平台原创" in markdown.text
        and '"correct_rate": 1.0' in markdown.text
    )
    assert (
        client.patch(
            f"/knowledge/artifacts/{training['artifact_id']}", json={"title": "覆盖", "content": {}}
        ).status_code
        == 409
    )
    assert client.get("/api/career/trainings/missing").status_code == 404
    assert client.post("/api/career/extract", json={"description": " " * 12}).status_code == 422


def test_api_disabled_boundary_preserves_original_modules(api, monkeypatch):
    client, _ = api
    row = create_api(client)
    training = start_api(client, row, "interview")
    pid, tid = row["position_id"], training["training_id"]
    monkeypatch.setenv("FILEMATE_ENABLE_CAREER", "0")
    assert client.get("/api/career/status").json()["data"]["enabled"] is False
    for method, path, body in [
        ("get", "/catalog", None),
        ("get", "/positions", None),
        ("get", "/events", None),
        ("get", "/overview", None),
        ("post", "/extract", {"description": "数据结构与算法岗位描述文本"}),
        (
            "post",
            "/positions",
            {"position": imported(), "confirmed": True, "request_key": "off_position_12345678"},
        ),
        ("get", f"/positions/{pid}", None),
        (
            "patch",
            f"/positions/{pid}",
            {"position": imported(), "confirmed": True, "expected_revision": 1},
        ),
        ("get", f"/positions/{pid}/evidence", None),
        ("get", f"/positions/{pid}/trainings", None),
        (
            "post",
            f"/positions/{pid}/trainings",
            {
                "kind": "review",
                "confirmed": True,
                "expected_revision": 1,
                "request_key": "off_training_12345678",
            },
        ),
        ("post", f"/positions/{pid}/state/undo", {"confirmed": True}),
        ("get", f"/positions/{pid}/delete-preview", None),
        ("delete", f"/positions/{pid}", {"confirmed": True, "confirmation_token": "a" * 64}),
        ("get", f"/trainings/{tid}", None),
        ("get", f"/trainings/{tid}/export", None),
        ("post", f"/trainings/{tid}/answers", {"answers": {"stack": 1}}),
    ]:
        assert client.request(method, "/api/career" + path, json=body).status_code == 503, path
    assert client.get(f"/interviews/{training['interview_id']}").status_code == 200
    assert client.get("/api/programming/problems").status_code == 200
    assert client.get("/knowledge/sources").status_code == 200
    monkeypatch.setenv("FILEMATE_ENABLE_CAREER", "1")
    assert client.get(f"/api/career/positions/{pid}").json()["data"] == row


def test_career_interview_model_failure_keeps_original_answer_and_snapshot(api, monkeypatch):
    client, _ = api
    row = create_api(client)
    training = start_api(client, row, "interview")
    iid = training["interview_id"]
    stored = client.post(
        f"/interviews/{iid}/answers",
        json={"answer": "合成回归：我通过索引优化查询，并比较请求延时验证结果。"},
    )
    assert stored.status_code == 200
    data = stored.json()["data"]
    assert data["turns"][0]["score"] is None
    snapshot = client.get(f"/api/career/trainings/{training['training_id']}").json()["data"]
    import filemate.llm_client as llm

    class Failed:
        def call(self, **kwargs):
            raise RuntimeError("secret external failure")

    monkeypatch.delenv("FILEMATE_INTERVIEW_LOCAL_ONLY")
    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: object())
    monkeypatch.setattr(llm, "LLMClient", lambda _: Failed())
    tid = data["turns"][0]["turn_id"]
    failure = client.post(f"/interviews/{iid}/turns/{tid}/analyze", json={"external_consent": True})
    assert failure.status_code == 502 and "secret" not in failure.text
    assert client.get(f"/interviews/{iid}").json()["data"]["turns"] == data["turns"]
    assert client.get(f"/api/career/trainings/{training['training_id']}").json()["data"] == snapshot


@pytest.mark.parametrize("api", ["anonymous"], indirect=True)
def test_anonymous_positions_trainings_and_exports_are_tenant_isolated(api):
    client, module = api
    row = create_api(client)
    training = start_api(client, row)
    with TestClient(module.app) as other:
        assert other.get("/api/career/overview").json()["data"]["counts"]["positions"] == 0
        assert other.get("/api/career/positions").json()["data"] == []
        assert other.get(f"/api/career/positions/{row['position_id']}").status_code == 404
        assert (
            other.get(f"/api/career/trainings/{training['training_id']}/export").status_code == 404
        )
        assert (
            other.get(f"/api/career/positions/{row['position_id']}/delete-preview").status_code
            == 404
        )


@pytest.mark.parametrize("damage", ["answer", "review"])
def test_invalid_stored_payload_blocks_export_without_rewriting(api, storage, damage):
    client, _ = api
    row = create_api(client)
    training = start_api(client, row, "written" if damage == "answer" else "review")
    if damage == "answer":
        client.post(
            f"/api/career/trainings/{training['training_id']}/answers",
            json={"answers": answers(training)},
        )
    raw = storage.get_artifact(training["artifact_id"])["content"]
    broken = copy.deepcopy(raw)
    if damage == "answer":
        broken["result"]["answers"]["stack"] = 999
    else:
        broken["comparison"]["skills"] = "damaged"
    encoded = json.dumps(broken, ensure_ascii=False)
    storage._conn().execute(
        "UPDATE artifacts SET content=? WHERE artifact_id=?", (encoded, training["artifact_id"])
    )
    storage._conn().commit()
    assert (
        client.get(f"/api/career/trainings/{training['training_id']}").json()["data"]["data_error"]
        is True
    )
    assert client.get(f"/api/career/trainings/{training['training_id']}/export").status_code == 409
    assert (
        storage._conn()
        .execute("SELECT content FROM artifacts WHERE artifact_id=?", (training["artifact_id"],))
        .fetchone()[0]
        == encoded
    )
