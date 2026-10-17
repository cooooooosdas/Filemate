"""Synthetic upstream failures and concurrent readiness checks for upload tools."""

import asyncio
import json
import threading
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

import filemate.llm_client as llm_module
from filemate.perception import FileParser
from filemate.runtime_governance import BudgetExceeded, GovernanceUnavailable
from filemate.tests import test_server_persistence

server_module = test_server_persistence.server_module

ROUTES = ["/ai/summarize", "/ai/knowledge-cards", "/ai/questions", "/ai/notes", "/ai/study-plan"]


def model_payload(route):
    """Return original synthetic learning content, never a real provider response."""
    if route.endswith("summarize"):
        return "合成摘要：栈遵循后进先出。"
    if route.endswith("knowledge-cards"):
        return [{"front": "栈的出入顺序？", "back": "后进先出"}]
    if route.endswith("questions"):
        return [{"question_type": "choice", "stem": "栈的顺序？", "options": ["后进先出", "先进先出"],
                 "answer": "A", "analysis": "栈为LIFO"}]
    if route.endswith("notes"):
        return {"title": "栈", "sections": [{"title": "顺序", "content": ["后进先出"]}]}
    tomorrow = (datetime.now().astimezone().date() + timedelta(days=1)).isoformat()
    return {"title": "栈复习", "daily_plan": [{"date": tomorrow, "focus": "栈", "tasks": ["手写栈"]}]}


def form_data():
    return {"exam_date": (datetime.now().astimezone().date() + timedelta(days=3)).isoformat(),
            "num_questions": "1", "num_cards": "1"}


def install_model(monkeypatch, call):
    class SyntheticModel:
        def call(self, **kwargs):
            return call()

        def call_structured(self, **kwargs):
            return json.loads(call())

    monkeypatch.setattr(llm_module.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm_module, "LLMClient", lambda config: SyntheticModel())


@pytest.mark.parametrize("route", ROUTES)
def test_slow_upload_model_does_not_block_readiness(server_module, monkeypatch, route):
    module, storage = server_module
    started, release = threading.Event(), threading.Event()
    released_by_probe = []

    def slow_call():
        started.set()
        released_by_probe.append(release.wait(3))
        payload = model_payload(route)
        return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)

    install_model(monkeypatch, slow_call)

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test") as client:
            task = asyncio.create_task(client.post(route, data=form_data(), files={"file": ("合成课程.txt", "栈后进先出".encode())}))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                assert started.is_set()
                response = await asyncio.wait_for(client.get("/api/ready"), 1)
                assert response.status_code == 200
            finally:
                release.set()
            response = await task
            assert response.status_code == 200, response.text
            assert response.json()["success"] is True
            data = response.json()["data"]
            assert storage.get_artifact(data["artifact_id"])
            assert storage.get_document_context(data["ctx_id"])

    asyncio.run(exercise())
    assert released_by_probe == [True]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("failure,status", [(RuntimeError, 502), (BudgetExceeded, 429), (GovernanceUnavailable, 503)])
def test_upstream_failure_is_not_a_success_artifact(server_module, monkeypatch, route, failure, status, caplog):
    module, storage = server_module

    def failed_call():
        raise failure("synthetic-private-upstream-body")

    install_model(monkeypatch, failed_call)
    with TestClient(module.app) as client:
        response = client.post(route, data=form_data(), files={"file": ("合成课程.txt", b"synthetic lesson")})
    assert response.status_code == status, response.text
    assert response.json()["success"] is False
    assert not storage.list_artifacts()
    assert not storage.list_sources()
    assert not list(module.UPLOAD_ROOT.glob("*/*"))
    if status == 502:
        assert "synthetic-private" not in response.text
        assert "synthetic-private" not in caplog.text


@pytest.mark.parametrize("route,payload", [
    ("/ai/summarize", "   "), ("/ai/knowledge-cards", "[]"),
    ("/ai/knowledge-cards", '[{"front":"概念","back":{}}]'),
    ("/ai/notes", '{"title":"", "sections":[], "error":"private"}'),
    ("/ai/notes", '{"title":"栈", "sections":[{"title":"顺序", "content":[]}]}'),
    ("/ai/notes", "not JSON"),
])
def test_empty_and_malformed_model_output_is_rejected(server_module, monkeypatch, route, payload):
    module, storage = server_module
    install_model(monkeypatch, lambda: payload)
    with TestClient(module.app) as client:
        response = client.post(route, files={"file": ("合成课程.txt", b"synthetic lesson")})
    assert response.status_code == 502
    assert not storage.list_artifacts()


@pytest.mark.parametrize("route", ROUTES + ["/knowledge/import"])
def test_parser_resource_failure_keeps_actionable_error(server_module, monkeypatch, route):
    module, storage = server_module
    message = "资料解析超过内存上限，请拆分文件后重试"
    monkeypatch.setattr(FileParser, "parse", lambda self, path: {"raw_text": "partial", "error": message})
    with TestClient(module.app) as client:
        response = client.post(route, data=form_data(), files={"file": ("合成课程.txt", b"synthetic")})
    assert response.status_code == 422
    assert response.json()["error"] == message
    assert not storage.list_sources()


def test_truncation_evidence_survives_import_and_reopen(server_module, monkeypatch):
    module, storage = server_module
    monkeypatch.setattr(FileParser, "parse", lambda self, path: {
        "raw_text": "合成正文", "metadata": {"truncated": True, "total_pages": 312, "private_path": "not-public"},
    })
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": ("合成课程.txt", b"synthetic")})
    source = response.json()["data"]
    assert source["metadata"]["truncated"] is True
    assert source["metadata"]["parse_warnings"]
    assert "private_path" not in source["metadata"]
    from filemate.execution.storage import SQLiteStorage

    storage.close()
    reopened = SQLiteStorage(storage.db_path)
    reopened.init_schema()
    module._storage = reopened
    assert reopened.get_source(source["source_id"])["metadata"]["parse_warnings"]


def test_long_input_analysis_warning_persists_in_context_and_artifact(server_module, monkeypatch):
    module, storage = server_module
    install_model(monkeypatch, lambda: "合成摘要")
    with TestClient(module.app) as client:
        response = client.post("/ai/summarize", files={"file": ("合成课程.txt", ("a" * 9000).encode())})
    assert response.status_code == 200
    data = response.json()["data"]
    assert "8000" in data["warnings"][0]
    assert storage.get_document_context(data["ctx_id"])["metadata"]["warnings"] == data["warnings"]
    assert storage.get_artifact(data["artifact_id"])["metadata"]["warnings"] == data["warnings"]
    assert len(storage.get_source(data["source_id"])["raw_text"]) == 9000


def test_failed_generation_preserves_history_and_allows_retry(server_module, monkeypatch):
    module, storage = server_module
    install_model(monkeypatch, lambda: "先前合成摘要")
    with TestClient(module.app) as client:
        old = client.post("/ai/summarize", files={"file": ("先前课程.txt", b"original synthetic lesson")}).json()["data"]

        def unavailable():
            raise RuntimeError("synthetic provider failure")

        install_model(monkeypatch, unavailable)
        failed = client.post("/ai/notes", files={"file": ("新课程.txt", b"new synthetic lesson")})
        assert failed.status_code == 502
        assert storage.get_artifact(old["artifact_id"])["content"] == "先前合成摘要"
        assert len(storage.list_artifacts()) == 1
        install_model(monkeypatch, lambda: json.dumps(model_payload("/ai/notes")))
        retried = client.post("/ai/notes", files={"file": ("新课程.txt", b"new synthetic lesson")})
        assert retried.status_code == 200
        assert len(storage.list_artifacts()) == 2


def test_plain_text_truncation_is_explicit(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("a" * 500_001, encoding="utf-8")
    parsed = FileParser().parse(path)
    assert len(parsed["raw_text"]) == 500_000
    assert parsed["metadata"]["truncated"] is True


def test_parser_internal_exception_is_not_exposed(server_module, monkeypatch):
    module, _ = server_module
    monkeypatch.setattr(FileParser, "parse", lambda self, path: {
        "error": "private-worker-path-and-exception", "raw_text": "partial",
    })
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": ("合成课程.txt", b"synthetic")})
    assert response.status_code == 422
    assert "private-worker" not in response.text


@pytest.mark.parametrize("failure,status", [(BudgetExceeded, 429), (GovernanceUnavailable, 503), (RuntimeError, 502)])
@pytest.mark.parametrize("kind", ["summary", "notes", "knowledge_cards", "questions"])
def test_live_workspace_keeps_governance_failure_and_old_artifacts(server_module, monkeypatch, failure, status, kind):
    module, storage = server_module
    source_id = storage.save_source(original_name="合成原件.txt", source_path="/synthetic/lesson.txt", raw_text="栈遵循后进先出")
    old = storage.save_artifact(source_id=source_id, artifact_type="summary", content="原有合成摘要")

    def failed_call():
        raise failure("synthetic failure")

    install_model(monkeypatch, failed_call)
    with TestClient(module.app) as client:
        response = client.post(f"/knowledge/sources/{source_id}/artifacts", json={
            "artifact_type": kind, "allow_external_model": True,
        })
    assert response.status_code == status
    assert storage.get_artifact(old)["content"] == "原有合成摘要"
    assert len(storage.list_artifacts()) == 1


def test_live_workspace_analysis_scope_is_saved(server_module, monkeypatch):
    module, storage = server_module
    source_id = storage.save_source(original_name="合成原件.txt", source_path="/synthetic/lesson.txt",
                                    raw_text="a" * 13000, metadata={"truncated": True})
    install_model(monkeypatch, lambda: json.dumps({"summary": "合成摘要"}))
    with TestClient(module.app) as client:
        response = client.post(f"/knowledge/sources/{source_id}/artifacts", json={
            "artifact_type": "summary", "allow_external_model": True,
        })
    assert response.status_code == 200
    artifact = response.json()["data"]
    assert len(artifact["metadata"]["warnings"]) == 2
    assert "12000" in artifact["metadata"]["warnings"][1]
    assert storage.get_artifact(artifact["artifact_id"])["metadata"]["warnings"]
