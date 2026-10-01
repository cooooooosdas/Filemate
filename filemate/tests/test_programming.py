"""编程提交的事务、状态机、API 和模型建议边界回归。"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import _MIGRATIONS, SQLiteStorage
from filemate.programming import service, windows_sandbox
from filemate.programming.feedback import evidence_profile, local_feedback, model_feedback
from filemate.programming.judge import normalized_output
from filemate.programming.problems import PROBLEMS, get_problem, public_problem
from filemate.programming.repository import CodingRepository
from filemate.programming.windows_sandbox import SandboxUnavailable


@pytest.fixture
def repository(tmp_path):
    storage = SQLiteStorage(tmp_path / "coding.db")
    storage.init_schema()
    yield CodingRepository(storage)
    storage.close()


def create(repository, suffix="1", code="int main(){return 0;}"):
    return repository.create(get_problem("array-sum"), code, "request_key_test_" + suffix)


def complete(repository, verdict, suffix):
    row = create(repository, suffix)
    repository.start(row["submission_id"])
    return repository.update(row["submission_id"], status="completed", payload={"result": {
        "verdict": verdict, "passed": int(verdict == "AC"), "total": 1,
        "score": 100 if verdict == "AC" else 0, "tests": [], "compile_log": "",
    }}, event="completed")


def test_original_bank_has_8_problems_and_maximum_boundary_cases():
    assert len(PROBLEMS) == 8
    assert [p["difficulty"] for p in PROBLEMS].count("简单") == 3
    assert [p["difficulty"] for p in PROBLEMS].count("中等") == 3
    assert [p["difficulty"] for p in PROBLEMS].count("困难") == 2
    assert len({p["id"] for p in PROBLEMS}) == 8
    assert all(p["tests"][-1]["name"] == "最大规模边界" for p in PROBLEMS)
    assert all("tests" not in public_problem(p) and public_problem(p)["test_count"] >= 6 for p in PROBLEMS)


def test_output_policy_keeps_semantically_relevant_spaces():
    assert normalized_output("YES  \r\n\r\n") == "YES"
    assert normalized_output("1  2") != normalized_output("1 2")
    assert normalized_output(" YES") != normalized_output("YES")
    assert normalized_output("yes") != normalized_output("YES")


@pytest.mark.parametrize("data,fallback,expected", [
    ("语法错误".encode(), "gbk", "语法错误"),
    ("语法错误".encode("gbk"), "gbk", "语法错误"),
    (b"error C2065", "gbk", "error C2065"),
    (b"\xff", None, "\ufffd"),
    (b"caf\xe9", "cp1252", "café"),
])
def test_output_decoder_preserves_utf8_and_supports_compiler_ansi(data, fallback, expected):
    assert windows_sandbox.decode_output(data, fallback) == expected


def test_student_output_does_not_silently_use_compiler_ansi_decoder():
    data = "语法错误".encode("gbk")
    assert windows_sandbox.decode_output(data) != "语法错误"


def test_compile_requests_ansi_fallback_only_for_compiler(tmp_path, monkeypatch):
    from filemate.programming.judge import WindowsCppJudge

    captured = {}

    def run(*args, **kwargs):
        captured.update(kwargs)
        return windows_sandbox.ProcessResult(1, "语法错误", "", 1, 0)

    monkeypatch.setattr("filemate.programming.judge.run_isolated", run)
    result = WindowsCppJudge(tmp_path)._compile("int main( {", tmp_path, threading.Event())
    assert captured["output_fallback_encoding"] == "mbcs"
    assert not captured["least_privileged"]
    assert result.stdout == "语法错误"


def test_create_is_idempotent_and_conflicting_key_cannot_replace_code(repository):
    row = create(repository)
    assert create(repository)["submission_id"] == row["submission_id"]
    with pytest.raises(ValueError):
        create(repository, code="different")
    assert len(repository.list()) == len(repository.events()) == 1
    assert repository.storage.get_artifact(row["artifact_id"])["content"]["code"] == row["code"]


def test_concurrent_duplicate_creation_keeps_one_artifact(repository):
    with ThreadPoolExecutor(max_workers=5) as pool:
        ids = list(pool.map(lambda _: create(repository)["submission_id"], range(8)))
    assert len(set(ids)) == 1
    assert repository.storage._conn().execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 1


def test_cancel_wins_over_late_progress_and_completion(repository):
    row = create(repository)
    identifier = row["submission_id"]
    assert repository.start(identifier)[1]
    assert not repository.start(identifier)[1]
    repository.transition(identifier, "cancel")
    repository.update(identifier, payload={"result": {"verdict": "AC"}})
    repository.update(identifier, status="completed", payload={"result": {"verdict": "AC"}})
    assert repository.get(identifier)["status"] == "cancelled"
    assert repository.get(identifier)["result"] == {}
    repository.update(identifier, payload={"notes": "取消后也保留复盘"})
    assert repository.get(identifier)["notes"] == "取消后也保留复盘"
    assert evidence_profile(repository.list())["attempt_count"] == 0


def test_undo_restore_are_idempotent_and_only_change_evidence(repository):
    wrong = complete(repository, "WA", "bad")
    identifier = wrong["submission_id"]
    before = wrong["code"], wrong["result"]
    repository.transition(identifier, "undo")
    repository.transition(identifier, "undo")
    assert evidence_profile(repository.list())["wrongbook"] == []
    repository.transition(identifier, "restore")
    repository.transition(identifier, "restore")
    latest = repository.get(identifier)
    assert (latest["code"], latest["result"]) == before
    assert [e["action"] for e in repository.events()].count("undo") == 1
    assert [e["action"] for e in repository.events()].count("restore") == 1
    assert evidence_profile(repository.list())["wrongbook"][0]["error_count"] == 1


def test_running_cannot_be_undone_and_undone_cannot_start(repository):
    row = create(repository)
    with pytest.raises(ValueError):
        repository.transition(row["submission_id"], "undo")
    repository.transition(row["submission_id"], "cancel")
    repository.transition(row["submission_id"], "undo")
    with pytest.raises(ValueError):
        repository.start(row["submission_id"])


def test_wrongbook_uses_observed_errors_and_two_actual_passes(repository):
    assert all(c["accept_rate"] is None for c in evidence_profile([])["categories"])
    complete(repository, "WA", "bad")
    complete(repository, "AC", "good1")
    complete(repository, "AC", "good2")
    cancelled = create(repository, "cancel")
    repository.transition(cancelled["submission_id"], "cancel")
    profile = evidence_profile(repository.list())
    assert profile["attempt_count"] == 3 and profile["accepted_count"] == 2
    assert profile["wrongbook"][0]["mastered"] is True
    assert profile["wrongbook"][0]["correct_streak"] == 2
    assert profile["wrongbook"][0]["error_count"] == 1
    assert next(c for c in profile["categories"] if c["tag"] == "图")["accept_rate"] is None


@pytest.mark.parametrize("damaged", ["broken", "[]", '{"code":"x","result":[]}'])
def test_corrupt_artifact_does_not_disappear_or_get_overwritten(repository, damaged):
    row = create(repository)
    conn = repository.storage._conn()
    conn.execute("UPDATE artifacts SET content=? WHERE artifact_id=?", (damaged, row["artifact_id"]))
    conn.commit()
    assert repository.get(row["submission_id"])["data_error"] is True
    with pytest.raises(ValueError):
        repository.start(row["submission_id"])
    assert conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)).fetchone()[0] == damaged
    assert repository.transition(row["submission_id"], "cancel")["status"] == "cancelled"
    assert repository.transition(row["submission_id"], "undo")["active"] == 0
    with pytest.raises(ValueError, match="损坏"):
        repository.transition(row["submission_id"], "restore")
    assert conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)).fetchone()[0] == damaged


def test_orphan_recovery_keeps_original_code_and_is_idempotent(repository):
    row = create(repository)
    repository.start(row["submission_id"])
    service.recover(repository)
    service.recover(repository)
    latest = repository.get(row["submission_id"])
    assert latest["status"] == "failed" and latest["code"] == row["code"]
    assert [e["action"] for e in repository.events()].count("interrupted") == 1


@pytest.mark.parametrize("problem_id,version", [("unavailable-problem", 1), ("array-sum", 999)])
def test_unavailable_problem_revision_preserves_history_and_valid_evidence(repository, problem_id, version):
    damaged = complete(repository, "WA", "old")
    valid = complete(repository, "AC", "current")
    conn = repository.storage._conn()
    raw = conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (damaged["artifact_id"],)).fetchone()[0]
    conn.execute("UPDATE coding_submissions SET problem_id=?,problem_version=? WHERE submission_id=?",
                 (problem_id, version, damaged["submission_id"]))
    conn.commit()
    assert repository.get(damaged["submission_id"])["data_error"] is True
    assert [item["submission_id"] for item in repository.evidence()] == [valid["submission_id"]]
    assert evidence_profile(repository.evidence())["attempt_count"] == 1
    repository.transition(damaged["submission_id"], "undo")
    with pytest.raises(ValueError, match="损坏"):
        repository.transition(damaged["submission_id"], "restore")
    assert conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (damaged["artifact_id"],)).fetchone()[0] == raw


def test_persisted_notes_and_review_survive_reopen(repository):
    row = complete(repository, "WA", "bad")
    repository.update(row["submission_id"], payload={"review": local_feedback(row), "notes": "改为64位整数"})
    reopened = SQLiteStorage(repository.storage.db_path)
    reopened.init_schema()
    try:
        latest = CodingRepository(reopened).get(row["submission_id"])
        assert latest["notes"] == "改为64位整数"
        assert latest["review"]["provider"] == "local_rules"
    finally:
        reopened.close()


def test_v21_upgrade_does_not_change_existing_artifacts(tmp_path):
    store = SQLiteStorage(tmp_path / "v21.db")
    conn = store._conn()
    conn.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)")
    for version, name, script in _MIGRATIONS:
        if version <= 21:
            conn.executescript(script)
            conn.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (version, name, "legacy"))
            conn.commit()
    identifier = store.save_artifact(artifact_type="notes", content={"text": "历史笔记"})
    before = store.get_artifact(identifier)
    store.init_schema()
    store.init_schema()
    assert store.get_schema_version() == 22
    assert store.get_artifact(identifier) == before
    assert CodingRepository(store).list() == []
    store.close()


def test_resource_queue_full_does_not_claim_or_lose_submission(repository, monkeypatch):
    class Full:
        def acquire(self, **kwargs):
            return False
    monkeypatch.setattr(service, "_SLOTS", Full())
    row = create(repository)
    with pytest.raises(ValueError, match="队列已满"):
        service.execute(repository, row["submission_id"])
    assert repository.get(row["submission_id"])["status"] == "queued"


def test_unexpected_adapter_failure_is_persisted_without_sensitive_message(repository, monkeypatch):
    class Failing:
        def judge(self, *args):
            raise RuntimeError("private credential must not appear")
    monkeypatch.setattr(service, "WindowsCppJudge", Failing)
    row = create(repository)
    with pytest.raises(SandboxUnavailable):
        service.execute(repository, row["submission_id"])
    latest = repository.get(row["submission_id"])
    assert latest["status"] == "failed" and latest["code"] == row["code"]
    assert "private credential" not in json.dumps(latest)


def test_live_cancel_race_and_duplicate_run_only_invoke_provider_once(repository, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []
    class Paused:
        def judge(self, code, problem, cancel, progress):
            calls.append(code)
            started.set()
            assert release.wait(5)
            return {"verdict": "AC", "tests": [], "compile_log": "", "passed": 1, "total": 1, "score": 100}
    monkeypatch.setattr(service, "WindowsCppJudge", Paused)
    row = create(repository)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(service.execute, repository, row["submission_id"])
        assert started.wait(5)
        assert service.execute(repository, row["submission_id"])["status"] == "running"
        service.cancel(repository, row["submission_id"])
        release.set()
        assert future.result()["status"] == "cancelled"
    assert len(calls) == 1 and evidence_profile(repository.list())["attempt_count"] == 0


def test_model_feedback_validates_line_numbers_and_does_not_judge(repository):
    row = complete(repository, "WA", "bad")
    class Model:
        def call_structured(self, **kwargs):
            return {"summary": "仅参考", "issues": [{"line": 1, "message": "建议"}],
                    "time_complexity": "无法确定", "space_complexity": "无法确定"}
    feedback = model_feedback(Model(), row)
    assert feedback["provider"] == "external_model" and feedback["reference_only"]
    assert repository.get(row["submission_id"])["result"]["verdict"] == "WA"
    class Invalid:
        def call_structured(self, **kwargs):
            return {"summary": "bad", "issues": [{"line": 500, "message": "bad"}]}
    with pytest.raises(ValueError):
        model_feedback(Invalid(), row)


def test_model_attribution_must_reference_every_failed_real_test(repository):
    row = complete(repository, "WA", "bad")
    row["result"]["tests"] = [{"index": 0, "name": "边界", "verdict": "WA", "input": "0\n",
                               "actual": "1", "expected": "0", "stderr": ""}]
    class Valid:
        def call_structured(self, **kwargs):
            return {"summary": "可能遗漏空数组", "issues": [],
                    "failed_tests": [{"index": 0, "message": "请检查初值。"}]}
    assert model_feedback(Valid(), row)["failed_tests"][0]["name"] == "边界"
    class Missing:
        def call_structured(self, **kwargs):
            return {"summary": "遗漏测试点", "issues": []}
    with pytest.raises(ValueError, match="遗漏"):
        model_feedback(Missing(), row)


def test_all_time_evidence_weekly_and_average_exclude_cancelled(repository):
    complete(repository, "WA", "bad")
    complete(repository, "AC", "good1")
    complete(repository, "AC", "good2")
    cancelled = create(repository, "cancel")
    repository.transition(cancelled["submission_id"], "cancel")
    profile = evidence_profile(repository.evidence(), now=datetime.now(timezone.utc))
    assert profile["attempt_count"] == profile["weekly"]["submissions"] == 3
    assert profile["weekly"]["verdicts"]["AC"] == 2
    assert profile["average_submissions_per_problem"] == 3
    assert profile["lowest_acceptance_tags"] == ["数组", "整数边界"]


@pytest.fixture
def api(repository, monkeypatch, tmp_path, request):
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "api-bootstrap.db"))
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", getattr(request, "param", "local"))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    module._storage.close()
    module._storage = module._StorageRouter(repository.storage)
    with TestClient(module.app) as client:
        yield client, module
    sys.modules.pop("server", None)


def test_api_input_validation_and_artifact_evidence_protection(api, repository):
    client, _ = api
    base = {"problem_id": "array-sum", "code": "int main(){}", "request_key": "valid_request_key_123"}
    assert client.post("/api/programming/submissions", json=base | {"code": "  "}).status_code == 422
    assert client.post("/api/programming/submissions", json=base | {"language": "python"}).status_code == 422
    assert client.post("/api/programming/submissions", json=base | {"code": "中" * 40000}).status_code == 422
    assert client.post("/api/programming/submissions", json=base | {"problem_id": "missing"}).status_code == 404
    response = client.post("/api/programming/submissions", json=base)
    assert response.status_code == 200
    row = response.json()["data"]
    assert client.post("/api/programming/submissions", json=base).json()["data"]["submission_id"] == row["submission_id"]
    assert client.patch(f"/knowledge/artifacts/{row['artifact_id']}", json={"title": "改判", "content": {"result": {"verdict": "AC"}}}).status_code == 409
    assert repository.get(row["submission_id"])["status"] == "queued"
    assert client.get("/api/programming/submissions/missing").status_code == 404


@pytest.mark.parametrize("damaged", ["broken", "[]", '{"code":"x","result":[]}'])
def test_overview_recovers_corrupt_running_submission_without_overwriting_it(api, repository, damaged):
    client, _ = api
    row = create(repository, "corrupt-running")
    repository.start(row["submission_id"])
    complete(repository, "AC", "healthy")
    conn = repository.storage._conn()
    conn.execute("UPDATE artifacts SET content=? WHERE artifact_id=?", (damaged, row["artifact_id"]))
    conn.commit()
    response = client.get("/api/programming/overview")
    assert response.status_code == 200
    assert response.json()["data"]["profile"]["attempt_count"] == 1
    assert repository.get(row["submission_id"])["status"] == "failed"
    assert repository.get(row["submission_id"])["data_error"] is True
    assert client.get("/api/programming/overview").status_code == 200
    assert [event["action"] for event in repository.events()].count("interrupted") == 1
    assert conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)).fetchone()[0] == damaged


def test_corrupt_orphan_recovery_rolls_back_status_when_event_write_fails(repository):
    row = create(repository, "failed-event")
    repository.start(row["submission_id"])
    conn = repository.storage._conn()
    conn.execute("UPDATE artifacts SET content='broken' WHERE artifact_id=?", (row["artifact_id"],))
    conn.commit()
    conn.execute("""CREATE TRIGGER reject_interrupted BEFORE INSERT ON coding_events
                    WHEN NEW.action='interrupted' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        service.recover(repository)
    assert repository.get(row["submission_id"])["status"] == "running"
    assert not any(event["action"] == "interrupted" for event in repository.events())
    assert conn.execute("SELECT content FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)).fetchone()[0] == "broken"


def test_api_model_consent_failure_keeps_existing_feedback_and_score(api, repository, monkeypatch):
    client, _ = api
    row = complete(repository, "WA", "bad")
    endpoint = f"/api/programming/submissions/{row['submission_id']}/review"
    assert client.post(endpoint, json={"mode": "llm"}).status_code == 422
    assert client.post(endpoint, json={"mode": "local"}).status_code == 200
    before = repository.get(row["submission_id"])
    def failed(*args):
        raise RuntimeError("sensitive provider exception")
    monkeypatch.setattr("filemate.programming.feedback.model_feedback", failed)
    monkeypatch.setattr("filemate.llm_client.LLMClient", lambda: object())
    response = client.post(endpoint, json={"mode": "llm", "allow_external_model": True})
    assert response.status_code == 502 and "sensitive" not in response.text
    after = repository.get(row["submission_id"])
    assert after["review"] == before["review"] and after["result"] == before["result"]


def test_all_programming_routes_have_independent_feature_flag(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("FILEMATE_ENABLE_PROGRAMMING", "0")
    requests = [("GET", "/status", None), ("GET", "/problems", None), ("GET", "/overview", None),
                ("POST", "/setup", {}), ("GET", "/submissions/id", None),
                ("POST", "/submissions", {"problem_id": "array-sum", "code": "x", "request_key": "valid_request_key_123"}),
                ("POST", "/submissions/id/run", {}), ("POST", "/submissions/id/review", {}),
                ("POST", "/submissions/id/notes", {"notes": "x"}), ("POST", "/submissions/id/undo", {}),
                ("POST", "/submissions/id/cancel", {}), ("POST", "/submissions/id/restore", {})]
    for method, path, body in requests:
        assert client.request(method, "/api/programming" + path, json=body).status_code == 503
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("api", ["anonymous"], indirect=True)
def test_anonymous_clients_cannot_read_cancel_or_edit_each_others_code(api):
    first, module = api
    payload = {"problem_id": "array-sum", "code": "int main(){}", "request_key": "same_key_separate_user_123"}
    row = first.post("/api/programming/submissions", json=payload).json()["data"]
    with TestClient(module.app) as second:
        assert second.get(f"/api/programming/submissions/{row['submission_id']}").status_code == 404
        assert second.post(f"/api/programming/submissions/{row['submission_id']}/cancel").status_code == 404
        assert second.get(f"/knowledge/artifacts/{row['artifact_id']}").status_code == 404
        other = second.post("/api/programming/submissions", json=payload).json()["data"]
        assert other["submission_id"] != row["submission_id"]
        assert second.get("/api/programming/overview").json()["data"]["submissions"][0]["submission_id"] == other["submission_id"]


def test_disabled_network_isolation_service_stops_before_any_process(tmp_path, monkeypatch):
    import os

    from filemate.programming import windows_sandbox

    if os.name != "nt":
        pytest.skip("Windows 原生隔离服务检查")
    monkeypatch.setattr(windows_sandbox, "network_isolation_available", lambda: False)
    with pytest.raises(SandboxUnavailable, match="网络隔离服务"):
        windows_sandbox.run_isolated(tmp_path / "unstarted.exe", [], tmp_path, environment={})
