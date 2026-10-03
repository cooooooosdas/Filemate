"""V2.2 图谱 HTTP 主流程与匿名身份隔离。"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def graph_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ModuleType]:
    from filemate.llm_client import LLMClient, LLMConfig

    provider = Mock()
    provider.chat.side_effect = AssertionError("图谱合同测试不得访问外部模型")
    monkeypatch.setattr(LLMConfig, "from_env", classmethod(lambda cls: cls()))
    monkeypatch.setattr(LLMClient, "_build", staticmethod(lambda config: provider))
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "filemate.db"))
    monkeypatch.setenv("FILEMATE_IDENTITY_MODE", "anonymous")
    monkeypatch.delenv("FILEMATE_ENABLE_KNOWLEDGE_GRAPH", raising=False)
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module
    provider.chat.assert_not_called()
    module._close_tenant_storages()
    module._local_storage.close()
    sys.modules.pop("server", None)


def _upload(client: TestClient) -> str:
    lesson = "数据结构包含树。树包含二叉树。二叉树是堆的前置知识。堆应用于堆排序。\n堆：一种树形结构。"
    response = client.post(
        "/knowledge/import", files={"file": ("课程笔记.txt", lesson.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["source_id"]


@pytest.mark.parametrize("suffix", ["md", "cpp"])
def test_text_learning_import_preserves_confirmed_graph_evidence(
    graph_server: ModuleType, suffix: str,
) -> None:
    """新增资料入口沿用原文引用、确认和持久图谱，不虚构掌握率。"""
    lesson = "数据结构包含树。树包含二叉树。二叉树是堆的前置知识。\n堆：一种树形结构。"
    text = f"# 原创学习笔记\n{lesson}" if suffix == "md" else f"/*\n{lesson}\n*/"
    with TestClient(graph_server.app) as client:
        uploaded = client.post(
            "/knowledge/import",
            files={"file": (f"原创学习资料.{suffix}", text.encode("utf-8"), "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        source = uploaded.json()["data"]
        source_id = source["source_id"]
        draft = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id})
        assert draft.status_code == 200, draft.text
        batch = draft.json()["data"]
        assert batch["payload"]["edges"]
        assert client.get("/api/knowledge-graph").json()["data"]["nodes"] == []
        confirmed = client.post(f"/api/knowledge-graph/batches/{batch['batch_id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        graph = client.get("/api/knowledge-graph").json()["data"]
        heap = next(node for node in graph["nodes"] if node["label"] == "堆")
        assert heap["source_id"] == source_id
        assert heap["excerpt"] in text
        assert heap["metrics"]["correct_rate"] is None
        assert heap["metrics"]["confidence"] == "待评测"
        assert client.get(f"/knowledge/sources/{source_id}").json()["data"]["raw_text"] == text
        graph_server._close_tenant_storages()
        reopened = client.get("/api/knowledge-graph").json()["data"]
        assert any(node["id"] == heap["id"] and node["excerpt"] == heap["excerpt"]
                   for node in reopened["nodes"])


def test_question_edit_versions_history_and_rejects_stale_clients(graph_server: ModuleType) -> None:
    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        storage = next(iter(graph_server._tenant_storages.values()))
        old = {"knowledge_point": "堆", "question": "堆是什么？", "answer": "树"}
        new = {"knowledge_point": "树", "question": "树是什么？", "answer": "结构"}
        artifact = storage.save_artifact(artifact_type="questions", source_id=source_id, content=[old])
        answer = {"artifact_id": artifact, "question_index": 0, "user_answer": "不会", "expected_question": old}
        assert client.post("/quiz/attempts", json=answer).status_code == 200
        wrong_id = storage.list_wrong_questions()[0]["wrong_id"]
        assert client.patch(f"/knowledge/artifacts/{artifact}", json={"title": "新版", "content": [new]}).status_code == 200
        assert client.post("/quiz/attempts", json=answer).status_code == 409
        assert client.post("/quiz/attempts", json={k: v for k, v in answer.items() if k != "expected_question"}).status_code == 409
        assert client.post("/quiz/attempts", json=answer | {"expected_question": new}).status_code == 200
        wrongs = client.get("/wrongbook").json()["data"]
        assert len(wrongs) == 2
        history = next(w for w in wrongs if w["wrong_id"] == wrong_id)
        assert history["question"] == old and history["artifact_id"] != artifact
        assert client.patch(f"/knowledge/artifacts/{history['artifact_id']}", json={"title": "覆盖", "content": [new]}).status_code == 409
        assert client.post("/quiz/attempts", json=answer | {"artifact_id": history["artifact_id"], "user_answer": "树"}).status_code == 200
        assert len(storage.get_graph_learning_evidence(source_id)["attempts"]) == 3
        today = client.get("/review/today").json()["data"]
        assert all("question_snapshot" in item for item in today["items"] if item["kind"] == "wrong_question")


def test_edit_during_grading_returns_conflict_without_saving(graph_server: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    import filemate.study

    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        storage = next(iter(graph_server._tenant_storages.values()))
        old = {"knowledge_point": "堆", "question": "堆是什么？", "answer": "树"}
        new = {"knowledge_point": "树", "question": "树是什么？", "answer": "结构"}
        artifact = storage.save_artifact(artifact_type="questions", source_id=source_id, content=[old])

        def interleaved_grading(question: dict, answer: str) -> bool:
            storage.update_artifact(artifact, title="已修改", content=[new])
            return True

        monkeypatch.setattr(filemate.study, "check_answer", interleaved_grading)
        response = client.post("/quiz/attempts", json={
            "artifact_id": artifact, "question_index": 0, "user_answer": "树", "expected_question": old,
        })
        assert response.status_code == 409
        evidence = storage.get_graph_learning_evidence(source_id)
        assert evidence["attempts"] == [] and evidence["wrong_questions"] == []
        assert storage.get_artifact(artifact)["content"] == [new]


def test_import_confirm_practice_profile_plan_and_undo(graph_server: ModuleType) -> None:
    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        draft = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id})
        assert draft.status_code == 200, draft.text
        batch = draft.json()["data"]
        assert batch["status"] == "draft" and batch["payload"]["edges"]
        assert client.get("/api/knowledge-graph").json()["data"]["nodes"] == []
        batch_id = batch["batch_id"]
        assert client.post(f"/api/knowledge-graph/batches/{batch_id}/confirm").status_code == 200
        graph = client.get("/api/knowledge-graph").json()["data"]
        heap = next(node for node in graph["nodes"] if node["label"] == "堆")
        assert heap["metrics"]["confidence"] == "待评测"
        assert heap["metrics"]["correct_rate"] is None
        assert heap["source_id"] == source_id and heap["excerpt"]
        assert graph["profile"]["attempt_count"] == 0
        assert graph["profile"]["weaknesses"] == []

        identity = graph_server._verify_identity_cookie(client.cookies["filemate_identity"])
        assert identity
        storage = graph_server._tenant_storage(identity)
        artifact_id = storage.save_artifact(
            source_id=source_id, artifact_type="questions", title="堆练习",
            content=[{"type": "填空题", "question": "堆属于哪种结构？",
                      "knowledge_point": "堆", "answer": "树"}],
        )
        preview_before = client.get(f"/api/knowledge-graph/nodes/{heap['id']}/plan").json()["data"]
        attempt = client.post("/quiz/attempts", json={
            "artifact_id": artifact_id, "question_index": 0, "user_answer": "数组",
        })
        assert attempt.status_code == 200, attempt.text
        refreshed = client.get("/api/knowledge-graph").json()["data"]
        heap = next(node for node in refreshed["nodes"] if node["label"] == "堆")
        assert heap["metrics"]["sample_count"] == 1
        assert heap["metrics"]["correct_rate"] == 0
        assert len(heap["wrong_ids"]) == 1
        assert refreshed["profile"]["observed_node_count"] == 1
        assert refreshed["profile"]["pending_wrong_count"] == 1
        assert refreshed["profile"]["weaknesses"][0]["node_id"] == heap["id"]
        preview = client.get(f"/api/knowledge-graph/nodes/{heap['id']}/plan").json()["data"]
        assert preview["evidence_revision"] != preview_before["evidence_revision"]
        assert preview["steps"][-1]["label"] == "堆"
        stale = client.post(f"/api/knowledge-graph/nodes/{heap['id']}/plan", json={
            "evidence_revision": preview_before["evidence_revision"],
        })
        assert stale.status_code == 409
        save = client.post(f"/api/knowledge-graph/nodes/{heap['id']}/plan", json={
            "evidence_revision": preview["evidence_revision"],
        })
        assert save.status_code == 200, save.text
        plan_id = save.json()["data"]["plan_id"]
        repeated = client.post(f"/api/knowledge-graph/nodes/{heap['id']}/plan", json={
            "evidence_revision": preview["evidence_revision"],
        })
        assert repeated.json()["data"]["plan_id"] == plan_id
        plan = client.get(f"/study-plans/{plan_id}").json()["data"]
        assert plan["plan_data"]["daily_plan"][-1]["focus"] == "堆"
        assert any(item["plan_id"] == plan_id for item in client.get(
            "/api/knowledge-graph").json()["data"]["plans"])
        assert client.post(f"/api/knowledge-graph/plans/{plan_id}/undo").json()["data"]["status"] == "archived"
        assert next(item for item in client.get("/api/knowledge-graph").json()["data"]["plans"]
                    if item["plan_id"] == plan_id)["status"] == "archived"
        assert client.post(f"/api/knowledge-graph/plans/{plan_id}/restore").json()["data"]["status"] == "active"
        assert client.post(f"/api/knowledge-graph/batches/{batch_id}/undo").json()["data"]["status"] == "undone"
        assert client.get("/api/knowledge-graph").json()["data"]["nodes"] == []
        assert client.post(f"/api/knowledge-graph/batches/{batch_id}/restore").status_code == 200
        actions = {event["action"] for event in client.get("/api/knowledge-graph").json()["data"]["events"]}
        assert {"extract", "confirm", "undo", "restore", "plan_create", "plan_undo", "plan_restore"} <= actions


def test_graph_identity_errors_and_disable(
    graph_server: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(graph_server.app) as alice, TestClient(graph_server.app) as bob:
        source_id = _upload(alice)
        batch = alice.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).json()["data"]
        assert bob.get("/api/knowledge-graph").json()["data"]["batches"] == []
        assert bob.get("/api/knowledge-graph").json()["data"]["events"] == []
        assert bob.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).status_code == 404
        assert bob.post(f"/api/knowledge-graph/batches/{batch['batch_id']}/confirm").status_code == 404
        assert alice.post("/api/knowledge-graph/drafts", json={
            "source_id": source_id, "mode": "llm",
        }).status_code == 422
        monkeypatch.setenv("FILEMATE_ENABLE_KNOWLEDGE_GRAPH", "0")
        assert alice.get("/api/knowledge-graph").status_code == 503
        assert alice.get("/api/health").status_code == 200


def test_graph_provider_failure_keeps_prior_graph_and_logs_failure(
    graph_server: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import filemate.llm_client as llm

    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        created = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id})
        batch_id = created.json()["data"]["batch_id"]
        client.post(f"/api/knowledge-graph/batches/{batch_id}/confirm")
        original = client.get("/api/knowledge-graph").json()["data"]["nodes"]

        def fail_model(*args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("private provider detail")

        monkeypatch.setattr(llm.LLMClient, "call_structured", fail_model)
        failed = client.post("/api/knowledge-graph/drafts", json={
            "source_id": source_id, "mode": "llm", "allow_external_model": True,
        })
        assert failed.status_code == 502
        assert "private provider detail" not in failed.text
        graph = client.get("/api/knowledge-graph").json()["data"]
        assert graph["nodes"] == original
        assert graph["batches"][0]["status"] == "failed"
        assert graph["batches"][0]["payload"] == {"nodes": [], "edges": []}
        assert graph["events"][0]["action"] == "extract_failed"
        assert "private provider detail" not in str(graph["events"])


def test_empty_invalid_boundary_input_and_cancelled_draft(graph_server: ModuleType) -> None:
    with TestClient(graph_server.app) as client:
        assert client.post("/api/knowledge-graph/drafts", json={"source_id": ""}).status_code == 422
        assert client.post("/api/knowledge-graph/drafts", json={"source_id": "x", "mode": "invalid"}).status_code == 422
        source_id = _upload(client)
        batch = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).json()["data"]
        url = f"/api/knowledge-graph/batches/{batch['batch_id']}"
        client.post(url + "/undo")
        client.post(url + "/undo")
        cancelled = client.get("/api/knowledge-graph").json()["data"]
        assert cancelled["nodes"] == [] and cancelled["batches"][0]["status"] == "undone"
        assert [event["action"] for event in cancelled["events"]] == ["undo", "extract"]
        assert client.post(url + "/confirm").status_code == 409
        assert client.post(url + "/restore").status_code == 200
        identity = graph_server._verify_identity_cookie(client.cookies["filemate_identity"])
        storage = graph_server._tenant_storage(identity)
        empty = storage.save_source(original_name="空资料.txt", source_path="empty.txt", raw_text="")
        assert client.post("/api/knowledge-graph/drafts", json={"source_id": empty}).status_code == 422
        long_text = "# 开头概念\n" + "无结构内容。" * 4000 + "\n# 截断之外"
        long_source = storage.save_source(original_name="长资料.md", source_path="long.md", raw_text=long_text)
        long_batch = client.post("/api/knowledge-graph/drafts", json={"source_id": long_source}).json()["data"]
        assert long_batch["payload"]["source_truncated"] is True
        assert long_batch["payload"]["input_characters"] == 20000
        assert [node["label"] for node in long_batch["payload"]["nodes"]] == ["开头概念"]


def test_model_invalid_output_and_source_change_do_not_overwrite_graph(
    graph_server: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from filemate.llm_client import LLMClient

    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        batch = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).json()["data"]
        client.post(f"/api/knowledge-graph/batches/{batch['batch_id']}/confirm")
        original = client.get("/api/knowledge-graph").json()["data"]["nodes"]
        request = {"source_id": source_id, "mode": "llm", "allow_external_model": True}
        monkeypatch.setattr(LLMClient, "call_structured", lambda *args, **kwargs: {
            "nodes": [{"label": "幻觉", "excerpt": "资料没有这句话"}], "edges": [],
        })
        assert client.post("/api/knowledge-graph/drafts", json=request).status_code == 422
        assert client.get("/api/knowledge-graph").json()["data"]["nodes"] == original
        identity = graph_server._verify_identity_cookie(client.cookies["filemate_identity"])
        storage = graph_server._tenant_storage(identity)

        def change_source(*args: object, **kwargs: object) -> dict[str, object]:
            storage.replace_source_chunks(source_id, [{"chunk_index": 0, "content": "新版"}])
            return {"nodes": [{"label": "堆", "excerpt": "堆：一种树形结构"}], "edges": []}

        monkeypatch.setattr(LLMClient, "call_structured", change_source)
        assert client.post("/api/knowledge-graph/drafts", json=request).status_code == 409
        graph = client.get("/api/knowledge-graph").json()["data"]
        assert graph["nodes"] == []  # 来源已变更，旧确认结果暂不投影。
        assert all(batch["stale"] for batch in graph["batches"])


def test_corrupt_history_does_not_block_valid_graph_or_sources(graph_server: ModuleType) -> None:
    with TestClient(graph_server.app) as client:
        source_id = _upload(client)
        batch = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).json()["data"]
        client.post(f"/api/knowledge-graph/batches/{batch['batch_id']}/confirm")
        original = client.get("/api/knowledge-graph").json()["data"]["nodes"]
        second = client.post("/api/knowledge-graph/drafts", json={"source_id": source_id}).json()["data"]
        identity = graph_server._verify_identity_cookie(client.cookies["filemate_identity"])
        storage = graph_server._tenant_storage(identity)
        storage._conn().execute("UPDATE knowledge_graph_batches SET payload='null' WHERE batch_id=?",
                                (second["batch_id"],))
        storage._conn().commit()
        response = client.get("/api/knowledge-graph")
        assert response.status_code == 200
        graph = response.json()["data"]
        assert graph["nodes"] == original and graph["batches"][0]["data_error"] is True
        assert client.post(f"/api/knowledge-graph/batches/{second['batch_id']}/confirm").status_code == 409
        assert client.get(f"/knowledge/sources/{source_id}").status_code == 200
