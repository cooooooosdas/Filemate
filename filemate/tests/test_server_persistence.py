"""FastAPI 持久化链路回归测试。"""
from __future__ import annotations

import importlib
import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from starlette.requests import Request

from filemate.execution.storage import SQLiteStorage


@pytest.fixture()
def server_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[ModuleType, SQLiteStorage]]:
    """在临时目录中加载服务，避免测试污染真实数据库。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FILEMATE_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("FILEMATE_DB_PATH", str(tmp_path / "bootstrap.db"))
    monkeypatch.setenv("FILEMATE_UPLOAD_DIR", str(tmp_path / "runtime" / "inbox"))
    monkeypatch.setenv("FILEMATE_ARCHIVE_DIR", str(tmp_path / "archive"))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    module._storage.close()

    storage = SQLiteStorage(tmp_path / "api.db")
    storage.init_schema()
    module._storage = storage
    module.ARCHIVE_DIR = tmp_path / "archive"
    module.UPLOAD_ROOT = tmp_path / ".filemate-data" / "inbox"
    module._sessions.clear()
    yield module, storage

    module._sessions.clear()
    current_storage = module._storage
    if current_storage is not storage:
        current_storage.close()
    storage.close()
    sys.modules.pop("server", None)


def test_ai_context_and_artifact_survive_reopen(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    module, storage = server_module
    document = tmp_path / "操作系统讲义.txt"
    document.write_text("进程是资源分配和调度的基本单位。", encoding="utf-8")

    ctx_id, source_id, artifact_id = module._persist_ai_context(
        file_path=document,
        text=document.read_text(encoding="utf-8"),
        artifact_type="summary",
        content="进程基础概念摘要",
        title="操作系统讲义 · 摘要",
    )
    database_path = storage.db_path
    storage.close()

    reopened = SQLiteStorage(database_path)
    reopened.init_schema()
    module._storage = reopened

    assert reopened.get_source(source_id)["raw_text"].startswith("进程")
    assert reopened.get_artifact(artifact_id)["content"] == "进程基础概念摘要"
    context = reopened.get_document_context(ctx_id)
    assert context["source_id"] == source_id
    assert context["artifact_id"] == artifact_id


def test_artifact_detail_can_be_opened_and_edited(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="笔记.txt",
        source_path="/tmp/笔记.txt",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="notes",
        title="课程笔记",
        content={"sections": ["第一节"]},
    )

    with TestClient(module.app) as client:
        opened = client.get(f"/knowledge/artifacts/{artifact_id}")
        edited = client.patch(
            f"/knowledge/artifacts/{artifact_id}",
            json={"title": "课程笔记修订", "content": {"sections": ["第二节"]}},
        )

    assert opened.status_code == 200
    assert opened.json()["data"]["content"] == {"sections": ["第一节"]}
    assert edited.status_code == 200
    assert edited.json()["data"]["title"] == "课程笔记修订"
    assert storage.get_artifact(artifact_id)["content"] == {"sections": ["第二节"]}


def test_anonymous_feedback_drops_raw_text_and_exports_csv(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    sensitive_target = "我的手机号13800138000:chunk-private"
    with TestClient(module.app) as client:
        saved = client.post(
            "/evaluation/feedback",
            json={
                "area": "retrieval",
                "target_id": sensitive_target,
                "rating": 1,
                "context": {
                    "rank": 1,
                    "score": 3.2,
                    "query_length": 18,
                    "raw_query": "我的手机号13800138000",
                    "filename": "个人资料.pdf",
                },
            },
        )
        summary = client.get("/evaluation/feedback/summary")
        exported = client.get("/evaluation/feedback/export.csv")

    assert saved.status_code == 200
    feedback = storage.list_product_feedback()[0]
    assert sensitive_target not in feedback["target_hash"]
    assert feedback["context"] == {"rank": 1, "score": 3.2, "query_length": 18}
    assert summary.json()["data"]["positive_rate"] == 100.0
    assert exported.status_code == 200
    assert "13800138000" not in exported.text
    assert "个人资料.pdf" not in exported.text
    assert "target_hash" in exported.text


def test_cors_allows_local_frontend_but_not_arbitrary_origins(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    """本地前端可访问 Sidecar，任意网页不能读取学习数据。"""
    module, _storage = server_module
    client = TestClient(module.app)

    allowed = client.options(
        "/",
        headers={
            "Origin": "http://127.0.0.1:4173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:4173"
    )

    rejected = client.options(
        "/",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers

    health = client.get("/api/health")
    assert health.json()["data"]["version"] == "1.2.0"


@pytest.mark.asyncio
async def test_upload_is_saved_in_durable_inbox(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module
    upload = UploadFile(
        filename="../课程讲义.txt",
        file=io.BytesIO("长期保留".encode()),
    )

    path, size = await module._save_upload(upload)

    assert path.name == "课程讲义.txt"
    assert path.is_relative_to(module.UPLOAD_ROOT)
    assert path.read_text(encoding="utf-8") == "长期保留"
    assert size == len("长期保留".encode())


def test_confirm_session_recovers_from_database(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source = storage.db_path.parent / "作业一.txt"
    source.write_text("进程调度作业", encoding="utf-8")
    storage.create_session("session-1", str(source))
    storage.update_session(
        "session-1",
        status="done",
        category="其他",
        suggested_name="进程调度作业",
        entities=json.dumps({"course_name": "计算机基础"}, ensure_ascii=False),
    )
    module._sessions.clear()

    with TestClient(module.app) as client:
        response = client.post(
            "/sessions/session-1/confirm",
            json={
                "accepted": True,
                "edits": {
                    "category": "作业",
                    "entities": {"course_name": "操作系统"},
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    stored = storage.get_session("session-1")
    assert stored["status"] == "confirmed"
    assert stored["category"] == "作业"
    assert stored["user_modified"] == 1
    assert json.loads(stored["entities"])["course_name"] == "操作系统"
    execution = response.json()["data"]["execution"]
    assert execution["status"] == "applied"
    assert Path(execution["dest_path"]).read_text(encoding="utf-8") == "进程调度作业"
    assert not source.exists()
    operations = storage.get_operations("session-1")
    assert operations[-1]["action"] == "execute"
    confirm_edit = next(op for op in operations if op["action"] == "confirm_edit")
    assert json.loads(confirm_edit["user_override"])["category"] == "作业"


def test_rejected_session_uses_valid_skipped_status(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    storage.create_session("session-2", "C:/资料/通知.pdf")
    module._sessions.clear()

    with TestClient(module.app) as client:
        response = client.post(
            "/sessions/session-2/confirm",
            json={"accepted": False},
        )

    assert response.status_code == 200
    assert storage.get_session("session-2")["status"] == "skipped"
    assert storage.get_operations("session-2")[-1]["action"] == "reject"


def test_api_errors_use_stable_envelope(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    storage.create_session("session-error", "C:/资料/error.txt")

    with TestClient(module.app) as client:
        missing = client.get("/sessions/not-found")
        invalid = client.patch(
            "/sessions/session-error",
            json={"edits": {"category": "恶意分类"}},
        )
        no_undo = client.post("/sessions/session-error/undo")

    assert missing.status_code == 404
    assert missing.json() == {
        "success": False,
        "data": None,
        "error": "Session not found",
    }
    assert invalid.status_code == 422
    assert invalid.json()["success"] is False
    assert invalid.json()["error"] == "无效的文件分类"
    assert no_undo.status_code == 409
    assert no_undo.json()["error"] == "没有可撤销的已执行操作"


def test_desktop_shutdown_requires_local_token(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module

    with TestClient(module.app) as client:
        disabled = client.post("/internal/shutdown")
    assert disabled.status_code == 404

    class FakeServer:
        should_exit = False

    module.SHUTDOWN_TOKEN = "desktop-secret"
    module._uvicorn_server = FakeServer()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/shutdown",
            "headers": [
                (b"x-filemate-shutdown-token", b"desktop-secret"),
            ],
            "client": ("127.0.0.1", 55000),
        }
    )

    response = module.shutdown_backend(request)

    assert response.success is True
    assert module._uvicorn_server.should_exit is True


def test_draft_edit_does_not_move_file(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source = storage.db_path.parent / "草稿.txt"
    source.write_text("draft", encoding="utf-8")
    storage.create_session("session-draft", str(source))
    storage.update_session("session-draft", status="done", category="待确认")

    with TestClient(module.app) as client:
        response = client.patch(
            "/sessions/session-draft",
            json={"edits": {"category": "参考资料"}},
        )

    assert response.status_code == 200
    assert response.json()["data"]["category"] == "参考资料"
    assert storage.get_session("session-draft")["status"] == "done"
    assert source.exists()
    assert storage.list_execution_records("session-draft") == []


def test_undo_endpoint_restores_confirmed_file(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source = storage.db_path.parent / "可撤销.txt"
    source.write_text("undo me", encoding="utf-8")
    storage.create_session("session-undo", str(source))
    storage.update_session(
        "session-undo",
        status="done",
        category="课件",
        suggested_name="可撤销资料",
        entities=json.dumps({"course_name": "测试课程"}, ensure_ascii=False),
    )

    with TestClient(module.app) as client:
        confirmed = client.post(
            "/sessions/session-undo/confirm",
            json={"accepted": True},
        )
        undone = client.post("/sessions/session-undo/undo")
        detail = client.get("/sessions/session-undo")
        executions = client.get("/sessions/session-undo/executions")

    assert confirmed.json()["success"] is True
    assert undone.json()["data"]["execution"]["status"] == "undone"
    assert source.read_text(encoding="utf-8") == "undo me"
    assert detail.json()["data"]["status"] == "done"
    assert detail.json()["data"]["can_undo"] is False
    assert executions.json()["data"][0]["status"] == "undone"


def test_knowledge_source_api_returns_persisted_artifacts(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="高等数学.txt",
        source_path="C:/资料/高等数学.txt",
        raw_text="极限、导数与积分",
        file_hash="math-file",
        metadata={"semester": "2026-fall"},
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="knowledge_cards",
        title="高等数学 · 知识卡",
        content=[{"front": "导数是什么？", "back": "函数变化率"}],
    )

    with TestClient(module.app) as client:
        sources_response = client.get("/knowledge/sources")
        detail_response = client.get(f"/knowledge/sources/{source_id}")
        artifacts_response = client.get(
            f"/knowledge/sources/{source_id}/artifacts",
            params={"artifact_type": "knowledge_cards"},
        )

    sources = sources_response.json()["data"]
    assert sources[0]["source_id"] == source_id
    assert "raw_text" not in sources[0]
    assert sources[0]["text_length"] == len("极限、导数与积分")
    assert detail_response.json()["data"]["raw_text"] == "极限、导数与积分"
    artifacts = artifacts_response.json()["data"]
    assert artifacts[0]["artifact_id"] == artifact_id
    assert artifacts[0]["content"][0]["front"] == "导数是什么？"


def test_chat_uses_and_updates_persisted_history(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, storage = server_module
    storage.save_document_context(
        ctx_id="ctx-chat",
        context_text="TCP 使用三次握手建立连接。",
        chat_history=[{"role": "user", "content": "这是哪门课？"}],
    )
    received: dict[str, Any] = {}

    import filemate.llm_client as llm_module
    import filemate.understanding as understanding_module

    class FakeConfig:
        @classmethod
        def from_env(cls) -> FakeConfig:
            return cls()

    class FakeClient:
        def __init__(self, config: FakeConfig) -> None:
            self.config = config

    class FakeChatbot:
        def __init__(self, llm: FakeClient) -> None:
            self.llm = llm

        def answer(
            self,
            question: str,
            context: str,
            chat_history: list[dict[str, str]],
            mode: str = "answer",
        ) -> str:
            received.update(
                question=question,
                context=context,
                chat_history=chat_history,
                mode=mode,
            )
            return "它属于计算机网络课程。"

    monkeypatch.setattr(llm_module, "LLMConfig", FakeConfig)
    monkeypatch.setattr(llm_module, "LLMClient", FakeClient)
    monkeypatch.setattr(understanding_module, "AIChatbot", FakeChatbot)

    with TestClient(module.app) as client:
        response = client.post(
            "/ai/chat",
            json={
                "ctx_id": "ctx-chat",
                "question": "为什么是三次？",
                "mode": "socratic",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "它属于计算机网络课程。"
    assert received["context"] == "TCP 使用三次握手建立连接。"
    assert received["chat_history"][0]["content"] == "这是哪门课？"
    assert received["mode"] == "socratic"
    persisted = storage.get_document_context("ctx-chat")["chat_history"]
    assert persisted[-2:] == [
        {"role": "user", "content": "为什么是三次？"},
        {"role": "assistant", "content": "它属于计算机网络课程。"},
    ]


def test_retrieval_search_and_wrongbook_flow(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    module, storage = server_module
    document = tmp_path / "网络讲义.txt"
    document.write_text("TCP 使用三次握手建立可靠连接。", encoding="utf-8")
    _ctx_id, source_id, artifact_id = module._persist_ai_context(
        file_path=document,
        text=document.read_text(encoding="utf-8"),
        artifact_type="questions",
        content=[
            {
                "type": "填空题",
                "question": "TCP 使用几次握手？",
                "answer": "三次握手",
                "explanation": "用于确认双方收发能力。",
            }
        ],
    )

    with TestClient(module.app) as client:
        search = client.get("/knowledge/search", params={"q": "TCP 握手"})
        wrong = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "两次",
            },
        )
        wrongbook = client.get("/wrongbook")
        correct_once = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "三次握手",
            },
        )
        correct_twice = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "三次握手",
            },
        )

    assert search.json()["data"][0]["source_id"] == source_id
    assert wrong.json()["data"]["is_correct"] is False
    assert wrongbook.json()["data"][0]["error_count"] == 1
    assert correct_once.json()["data"]["is_correct"] is True
    assert correct_twice.json()["data"]["is_correct"] is True
    assert storage.list_wrong_questions(mastered=True)[0]["mastered"] == 1


def test_study_plan_progress_api_persists(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="高数.txt",
        source_path="/tmp/高数.txt",
        raw_text="微积分",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="study_plan",
        content={"title": "高数冲刺"},
    )
    saved = storage.create_study_plan(
        artifact_id=artifact_id,
        source_id=source_id,
        plan={
            "title": "高数冲刺",
            "exam_date": "2026-09-01",
            "daily_minutes": 60,
            "goal": "通过考试",
            "daily_plan": [{"date": "2026-08-10", "tasks": ["极限"]}],
        },
    )

    with TestClient(module.app) as client:
        updated = client.patch(
            f"/study-plans/{saved['plan_id']}/days/0",
            json={"completed": True},
        )
        listed = client.get("/study-plans", params={"status": "completed"})
        analytics = client.get("/analytics/overview")

    assert updated.status_code == 200
    assert updated.json()["data"]["completed_days"] == [0]
    assert listed.json()["data"][0]["plan_id"] == saved["plan_id"]
    assert analytics.json()["data"]["study_completion_rate"] == 100.0


def test_today_review_combines_plan_and_wrong_question(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="复习资料.txt",
        source_path="/tmp/复习资料.txt",
        raw_text="数据库索引",
    )
    plan_artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="study_plan",
        content={"title": "数据库复习"},
    )
    storage.create_study_plan(
        artifact_id=plan_artifact_id,
        source_id=source_id,
        plan={
            "title": "数据库复习",
            "exam_date": "2099-12-31",
            "daily_minutes": 45,
            "goal": "掌握索引",
            "daily_plan": [
                {
                    "date": "2000-01-01",
                    "focus": "B+ 树索引",
                    "tasks": ["解释索引结构"],
                    "duration_minutes": 45,
                }
            ],
        },
    )
    question_artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        content=[{"question": "索引的作用？", "answer": "加速查询"}],
    )
    storage.record_quiz_attempt(
        artifact_id=question_artifact_id,
        question_index=0,
        user_answer="不知道",
        is_correct=False,
        score=0,
        feedback="待复习",
    )

    with TestClient(module.app) as client:
        response = client.get("/review/today")

    assert response.status_code == 200
    review = response.json()["data"]
    assert review["active_plan_count"] == 1
    assert review["pending_wrong_count"] == 1
    assert {item["kind"] for item in review["items"]} == {
        "plan_day",
        "wrong_question",
    }
    assert review["items"][0]["title"] == "B+ 树索引"

    storage.record_quiz_attempt(
        artifact_id=question_artifact_id,
        question_index=0,
        user_answer="加速查询",
        is_correct=True,
        score=1,
        feedback="正确",
    )
    with TestClient(module.app) as client:
        after_review = client.get("/review/today").json()["data"]
    assert [item["kind"] for item in after_review["items"]] == ["plan_day"]
    assert after_review["pending_wrong_count"] == 0


def test_mock_interview_progresses_and_persists(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    with TestClient(module.app) as client:
        started = client.post(
            "/interviews",
            json={"target_role": "后端开发", "scenario": "求职面试"},
        ).json()["data"]
        answered = client.post(
            f"/interviews/{started['interview_id']}/answers",
            json={"answer": "我负责接口设计并通过测试将错误率降低了百分之三十。"},
        ).json()["data"]
        analytics = client.get("/analytics/overview").json()["data"]

    assert started["current_index"] == 0
    assert answered["current_index"] == 1
    assert answered["latest_evaluation"]["score"] > 0
    assert len(storage.get_interview(started["interview_id"])["turns"]) == 1
    assert analytics["interview_count"] == 1
    assert analytics["average_interview_score"] > 0
    assert "内容" in analytics["interview_dimensions"]
