"""FastAPI 持久化链路回归测试。"""

from __future__ import annotations

import importlib
import io
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from starlette.requests import Request

from filemate import __version__
from filemate.core.session import ProcessingSession, SessionStatus
from filemate.execution.storage import SQLiteStorage


def test_reverse_goal_persists_tasks_and_agent_evidence(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="竞赛申报书.md",
        source_path="/local/竞赛申报书.md",
        raw_text="FileMate 是本地优先的智能学习工作台。",
    )
    deadline = (
        datetime.now().astimezone().date() + timedelta(days=20)
    ).isoformat()

    with TestClient(module.app) as client:
        created_response = client.post(
            "/goals/reverse-plan",
            json={
                "title": "完成 FileMate 竞赛答辩",
                "goal_type": "competition",
                "deadline": deadline,
                "target_score": 85,
                "source_id": source_id,
            },
        )
        assert created_response.status_code == 200
        created = created_response.json()["data"]
        assert created["evidence_status"] == "insufficient"
        assert created["source_name"] == "竞赛申报书.md"
        expression_gap = next(
            item for item in created["gaps"] if item["name"] == "表达基线"
        )
        assert expression_gap["current"] == "待评测"

        task_id = created["tasks"][0]["task_id"]
        updated_response = client.patch(
            f"/goals/{created['goal_id']}/tasks/{task_id}",
            json={"completed": True},
        )
        assert updated_response.status_code == 200
        updated = updated_response.json()["data"]
        updated_task = next(
            item for item in updated["tasks"] if item["task_id"] == task_id
        )
        assert updated_task["status"] == "completed"

        replanned_response = client.post(f"/goals/{created['goal_id']}/replan")
        assert replanned_response.status_code == 200
        replanned = replanned_response.json()["data"]
        replanned_task = next(
            item for item in replanned["tasks"] if item["task_id"] == task_id
        )
        assert replanned_task["status"] == "completed"

        listed = client.get("/goals").json()["data"]
        assert listed[0]["goal_id"] == created["goal_id"]

    runs = storage.list_agent_runs()
    assert runs[0]["selected_agents"] == ["规划 Agent", "学习教练 Agent"]
    assert [step["agent_name"] for step in runs[0]["steps"]] == [
        "规划 Agent",
        "学习教练 Agent",
    ]
    assert all("raw_text" not in step["input_refs"] for step in runs[0]["steps"])

    database_path = storage.db_path
    storage.close()
    reopened = SQLiteStorage(database_path)
    reopened.init_schema()
    module._storage = reopened
    restored = reopened.get_artifact(created["goal_id"])
    assert restored is not None
    assert restored["content"]["title"] == "完成 FileMate 竞赛答辩"


def test_wrong_question_drives_source_bound_oral_training(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="数据库课件.txt", source_path="/local/数据库课件.txt",
    )
    other_source_id = storage.save_source(
        original_name="操作系统.txt", source_path="/local/操作系统.txt",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="questions",
        content=[{"stem": "B+ 树为什么适合范围查询？", "answer": "叶子节点有序"}],
    )
    attempt = storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="不知道",
        is_correct=False, score=0, feedback="待复习",
    )
    wrong = storage.list_wrong_questions(mastered=False, source_id=source_id)[0]
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()

    with TestClient(module.app) as client:
        created = client.post("/goals/reverse-plan", json={
            "title": "掌握数据库索引", "goal_type": "exam",
            "deadline": deadline, "source_id": source_id,
        })
        assert created.status_code == 200
        tasks = created.json()["data"]["tasks"]
        oral = next(task for task in tasks if task["task_id"] == "explain-wrong-aloud")
        assert oral["focus_wrong_id"] == wrong["wrong_id"]
        assert oral["evidence_ref"]["attempt_id"] == attempt["attempt_id"]
        assert oral["evidence_ref"]["source_revision"] == storage.get_source_revision(source_id)
        assert "answer" not in oral["evidence_ref"]
        goal_run = storage.get_agent_run(created.json()["data"]["last_agent_run_id"])
        assert goal_run["context_refs"]["focus_wrong_id"] == wrong["wrong_id"]
        assert goal_run["context_refs"]["attempt_id"] == attempt["attempt_id"]
        assert goal_run["steps"][1]["input_refs"]["focus_wrong_id"] == wrong["wrong_id"]

        mismatched = client.post("/interviews", json={
            "target_role": "数据库索引", "scenario": "知识讲解",
            "source_id": other_source_id, "focus_wrong_id": wrong["wrong_id"],
        })
        assert mismatched.status_code == 422

        started = client.post("/interviews", json={
            "target_role": "数据库索引", "scenario": "知识讲解",
            "source_id": source_id, "focus_wrong_id": wrong["wrong_id"],
            "goal_id": created.json()["data"]["goal_id"],
        })
        assert started.status_code == 200
        interview = started.json()["data"]
        assert "B+ 树为什么适合范围查询" in interview["current_question"]
        assert "叶子节点有序" not in interview["current_question"]
        run = storage.get_agent_run(interview["agent_run_id"])
        assert run["context_refs"]["focus_wrong_id"] == wrong["wrong_id"]
        assert run["context_refs"]["attempt_id"] == attempt["attempt_id"]
        assert run["context_refs"]["goal_id"] == created.json()["data"]["goal_id"]

        import filemate.llm_client as llm_module

        class AvailableConfig:
            @staticmethod
            def from_env() -> object:
                return object()

        model_calls: list[object] = []

        def create_model(config: object) -> object:
            model_calls.append(config)
            raise AssertionError("知识讲解不应调用外部模型")

        monkeypatch.setattr(llm_module, "LLMConfig", AvailableConfig)
        monkeypatch.setattr(llm_module, "LLMClient", create_model)

        answered = client.post(
            f"/interviews/{interview['interview_id']}/answers",
            json={"answer": "我会先核对索引叶子节点的组织形式。"},
        )
        assert answered.status_code == 200
        assert answered.json()["data"]["latest_evaluation"]["scoring_mode"] == "local_fallback"
        assert model_calls == []
        goal_before_completion = storage.get_artifact(created.json()["data"]["goal_id"])
        oral_before = next(task for task in goal_before_completion["content"]["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert oral_before["status"] == "pending"
        for _ in range(4):
            answered = client.post(
                f"/interviews/{interview['interview_id']}/answers",
                json={"answer": "我用自己的话讲清楚概念和推理过程。"},
            )
            assert answered.status_code == 200
        assert answered.json()["data"]["status"] == "completed"
        goal_after_completion = storage.get_artifact(created.json()["data"]["goal_id"])
        oral_after = next(task for task in goal_after_completion["content"]["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert oral_after["status"] == "completed"
        assert storage.get_wrong_question(wrong["wrong_id"])["mastered"] == 0
        replanned = client.post(f"/goals/{created.json()['data']['goal_id']}/replan")
        assert replanned.status_code == 200
        oral_replanned = next(task for task in replanned.json()["data"]["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert oral_replanned["status"] == "completed"
        assert model_calls == []


def test_goal_invalidates_old_evidence_and_replan_archives_reason(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="数据库课程.txt", source_path="/local/数据库课程.txt",
        raw_text="B+ 树叶子节点按键值排列。",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="questions",
        content=[{"stem": "B+ 树适合哪种查询？", "answer": "范围查询"}],
    )
    first = storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="点查询",
        is_correct=False, score=0, feedback="错误",
    )
    wrong = storage.list_wrong_questions(mastered=False, source_id=source_id)[0]
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()
    with TestClient(module.app) as client:
        created = client.post("/goals/reverse-plan", json={
            "title": "掌握索引", "goal_type": "exam", "deadline": deadline,
            "source_id": source_id,
        }).json()["data"]
        goal_id = created["goal_id"]
        oral = next(task for task in created["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert oral["evidence_ref"]["attempt_id"] == first["attempt_id"]

        storage.record_quiz_attempt(
            artifact_id=artifact_id, question_index=0, user_answer="不确定",
            is_correct=False, score=0, feedback="错误",
        )
        listed = client.get("/goals").json()["data"][0]
        stale = next(task for task in listed["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert stale["status"] == "invalidated"
        assert "更新的失败作答" in stale["invalidated_reason"]
        assert client.patch(
            f"/goals/{goal_id}/tasks/explain-wrong-aloud", json={"completed": True},
        ).status_code == 409
        assert client.post("/interviews", json={
            "target_role": "索引", "scenario": "知识讲解", "source_id": source_id,
            "focus_wrong_id": wrong["wrong_id"], "goal_id": goal_id,
        }).status_code == 422

        replanned = client.post(f"/goals/{goal_id}/replan").json()["data"]
        fresh = next(task for task in replanned["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert fresh["status"] == "pending"
        assert fresh["evidence_ref"]["attempt_id"] != first["attempt_id"]
        assert "更新的失败作答" in replanned["invalidated_tasks"][-1]["reason"]

        storage.save_source(
            source_id=source_id, original_name="数据库课程.txt",
            source_path="/local/数据库课程.txt", raw_text="B+ 树的结构已修订。",
        )
        listed = client.get("/goals").json()["data"][0]
        stale = next(task for task in listed["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert stale["status"] == "invalidated"
        assert "资料内容已变化" in stale["invalidated_reason"]
        assert client.post(f"/goals/{goal_id}/replan").status_code == 200

        storage.record_quiz_attempt(
            artifact_id=artifact_id, question_index=0, user_answer="范围查询",
            is_correct=True, score=1, feedback="正确",
        )
        storage.record_quiz_attempt(
            artifact_id=artifact_id, question_index=0, user_answer="范围查询",
            is_correct=True, score=1, feedback="正确",
        )
        listed = client.get("/goals").json()["data"][0]
        stale = next(task for task in listed["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert stale["status"] == "invalidated"
        assert "已通过复练掌握" in stale["invalidated_reason"]
        replanned = client.post(f"/goals/{goal_id}/replan").json()["data"]
        assert all(task["task_id"] != "explain-wrong-aloud" for task in replanned["tasks"])
        assert len(replanned["invalidated_tasks"]) == 3


def test_source_deletion_cascades_goal_and_wrong_evidence(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(original_name="课程.txt", source_path="/local/课程.txt")
    artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="questions",
        content=[{"stem": "问题", "answer": "答案"}],
    )
    storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="错误",
        is_correct=False, score=0, feedback="错误",
    )
    wrong_id = storage.list_wrong_questions(source_id=source_id)[0]["wrong_id"]
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()
    with TestClient(module.app) as client:
        created = client.post("/goals/reverse-plan", json={
            "title": "掌握课程", "goal_type": "exam", "deadline": deadline,
            "source_id": source_id,
        }).json()["data"]
        assert storage.delete_source(source_id) is not None
        assert storage.get_artifact(created["goal_id"]) is None
        assert storage.get_wrong_question(wrong_id) is None
        assert client.get("/goals").json()["data"] == []


def test_user_diagnosis_drives_goal_training_and_invalidates_old_plan(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="算法课程.txt", source_path="/local/算法课程.txt",
        raw_text="广度优先搜索使用队列逐层访问。",
    )
    storage.replace_source_chunks(source_id, [{
        "chunk_index": 0,
        "page_number": 2,
        "content": "广度优先搜索使用队列逐层访问。",
        "metadata": {},
    }])
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        content=[{
            "knowledge_point": "广度优先搜索",
            "question_type": "short_answer",
            "stem": "请说明 BFS 的执行过程。",
            "answer": "使用队列逐层访问",
        }],
    )
    storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="使用栈",
        is_correct=False, score=0, feedback="错误",
    )
    wrong_id = storage.list_wrong_questions(source_id=source_id)[0]["wrong_id"]
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()

    with TestClient(module.app) as client:
        diagnosed = client.patch(f"/wrongbook/{wrong_id}/diagnosis", json={
            "error_cause": "expression_gap",
            "note": "知道队列，但讲不清逐层访问",
        })
        assert diagnosed.status_code == 200
        assert diagnosed.json()["data"]["knowledge_label"] == "广度优先搜索"
        assert diagnosed.json()["data"]["error_cause_source"] == "user"

        created = client.post("/goals/reverse-plan", json={
            "title": "讲清 BFS", "goal_type": "exam", "deadline": deadline,
            "source_id": source_id,
        }).json()["data"]
        oral = next(task for task in created["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert oral["title"] == "重组表达并完成讲解"
        assert oral["knowledge_label"] == "广度优先搜索"
        assert oral["error_cause"] == "expression_gap"
        assert oral["error_cause_source"] == "user"
        assert oral["evidence_ref"]["diagnosis_revision"]
        assert oral["source_evidence"]["status"] == "matched"
        assert oral["source_evidence"]["page_number"] == 2
        assert "content" not in oral["source_evidence"]
        goal_run = storage.get_agent_run(created["last_agent_run_id"])
        assert goal_run["context_refs"]["knowledge_key"] == oral["knowledge_key"]
        assert goal_run["context_refs"]["error_cause"] == "expression_gap"
        assert goal_run["context_refs"]["source_chunk_id"] == oral["source_evidence"]["chunk_id"]

        started = client.post("/interviews", json={
            "target_role": "讲清 BFS", "scenario": "知识讲解",
            "source_id": source_id, "focus_wrong_id": wrong_id,
            "goal_id": created["goal_id"],
        })
        assert started.status_code == 200
        assert "结论、依据、例子" in started.json()["data"]["current_question"]
        assert started.json()["data"]["source_context"]["source_evidence"] == oral["source_evidence"]
        interview_run = storage.get_agent_run(started.json()["data"]["agent_run_id"])
        assert interview_run["context_refs"]["knowledge_key"] == oral["knowledge_key"]
        assert interview_run["context_refs"]["error_cause"] == "expression_gap"
        assert interview_run["context_refs"]["source_chunk_id"] == oral["source_evidence"]["chunk_id"]
        assert interview_run["steps"][0]["input_refs"]["source_chunk_id"] == oral["source_evidence"]["chunk_id"]
        restored = client.get(
            f"/interviews/{started.json()['data']['interview_id']}"
        ).json()["data"]
        assert restored["source_context"]["source_evidence"] == oral["source_evidence"]

        rediagnosed = client.patch(f"/wrongbook/{wrong_id}/diagnosis", json={
            "error_cause": "reasoning_break", "note": "遍历顺序推理断了",
        })
        assert rediagnosed.status_code == 200
        listed = client.get("/goals").json()["data"][0]
        stale = next(task for task in listed["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert stale["status"] == "invalidated"
        assert "错因诊断已更新" in stale["invalidated_reason"]

        replanned = client.post(f"/goals/{created['goal_id']}/replan").json()["data"]
        fresh = next(task for task in replanned["tasks"] if task["task_id"] == "explain-wrong-aloud")
        assert fresh["title"] == "分步讲清推理链"
        assert fresh["status"] == "pending"
        assert client.patch(f"/wrongbook/{wrong_id}/diagnosis", json={
            "error_cause": "unsupported", "note": "",
        }).status_code == 422


def test_oral_training_does_not_invent_source_evidence(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="离散数学.txt", source_path="/local/离散数学.txt",
        raw_text="集合与命题逻辑课程资料。",
    )
    storage.replace_source_chunks(source_id, [{
        "chunk_index": 0,
        "page_number": 1,
        "content": "集合的交集与并集运算。",
        "metadata": {},
    }])
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        content=[{
            "knowledge_point": "最短路径",
            "stem": "Dijkstra 算法如何选择下一个节点？",
            "answer": "选择当前距离最小的未访问节点",
        }],
    )
    storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="随机选择",
        is_correct=False, score=0, feedback="错误",
    )
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()

    with TestClient(module.app) as client:
        created = client.post("/goals/reverse-plan", json={
            "title": "掌握最短路径", "goal_type": "exam",
            "deadline": deadline, "source_id": source_id,
        }).json()["data"]
        oral = next(
            task for task in created["tasks"]
            if task["task_id"] == "explain-wrong-aloud"
        )
        assert oral["source_evidence"]["status"] == "unavailable"
        assert "chunk_id" not in oral["source_evidence"]
        assert "人工核对" in oral["source_evidence"]["reason"]
        run = storage.get_agent_run(created["last_agent_run_id"])
        assert run["context_refs"]["source_chunk_id"] is None

        artifact = storage.get_artifact(created["goal_id"])
        legacy_content = dict(artifact["content"])
        legacy_tasks = [dict(task) for task in legacy_content["tasks"]]
        legacy_oral = next(
            task for task in legacy_tasks
            if task["task_id"] == "explain-wrong-aloud"
        )
        legacy_oral.pop("source_evidence")
        legacy_content["tasks"] = legacy_tasks
        storage.update_artifact(
            created["goal_id"], title=artifact["title"], content=legacy_content,
        )
        listed = client.get("/goals").json()["data"][0]
        stale = next(
            task for task in listed["tasks"]
            if task["task_id"] == "explain-wrong-aloud"
        )
        assert stale["status"] == "invalidated"
        assert "缺少资料片段定位状态" in stale["invalidated_reason"]


def test_changed_source_chunk_invalidates_oral_training(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="算法课件.txt", source_path="/local/算法课件.txt",
        raw_text="广度优先搜索使用队列。",
    )
    storage.replace_source_chunks(source_id, [{
        "chunk_index": 0, "page_number": 3,
        "content": "广度优先搜索使用队列。", "metadata": {},
    }])
    artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="questions",
        content=[{
            "knowledge_point": "广度优先搜索",
            "stem": "广度优先搜索使用什么结构？", "answer": "队列",
        }],
    )
    storage.record_quiz_attempt(
        artifact_id=artifact_id, question_index=0, user_answer="栈",
        is_correct=False, score=0, feedback="错误",
    )
    deadline = (datetime.now().astimezone().date() + timedelta(days=7)).isoformat()

    with TestClient(module.app) as client:
        goal = client.post("/goals/reverse-plan", json={
            "title": "掌握图搜索", "goal_type": "exam",
            "deadline": deadline, "source_id": source_id,
        }).json()["data"]
        oral = next(
            task for task in goal["tasks"]
            if task["task_id"] == "explain-wrong-aloud"
        )
        assert oral["source_evidence"]["status"] == "matched"

        storage.replace_source_chunks(source_id, [{
            "chunk_index": 0, "page_number": 4,
            "content": "广度优先搜索按层访问节点。", "metadata": {},
        }])
        listed = client.get("/goals").json()["data"][0]
        stale = next(
            task for task in listed["tasks"]
            if task["task_id"] == "explain-wrong-aloud"
        )
        assert stale["status"] == "invalidated"
        assert "资料片段已变化" in stale["invalidated_reason"]


def test_workspace_import_is_local_and_deduplicated(server_module, monkeypatch):
    module, storage = server_module
    import filemate.llm_client as llm

    def unexpected(*args, **kwargs):
        pytest.fail("本地导入不能调用模型")

    monkeypatch.setattr(llm.LLMClient, "call", unexpected)
    with TestClient(module.app) as client:
        payload = "光合作用将光能转化为化学能。".encode()
        first = client.post("/knowledge/import", files={"file": ("课程.txt", payload)})
        assert first.status_code == 200
        source = first.json()["data"]
        again = client.post("/knowledge/import", files={"file": ("课程.txt", payload)})
        assert again.json()["data"]["source_id"] == source["source_id"]
        assert len(storage.list_sources()) == 1
        assert len(list(module.UPLOAD_ROOT.rglob("*.txt"))) == 1
        context = client.post(f"/knowledge/sources/{source['source_id']}/contexts")
        assert context.status_code == 200
        ctx = context.json()["data"]
        assert ctx["chat_history"] == []
        assert ctx["source_id"] == source["source_id"]
        assert storage.list_artifacts() == []
        assert client.get(f"/ai/contexts/{ctx['ctx_id']}").status_code == 200


@pytest.mark.parametrize("kind,content", [
    ("summary", {"summary": "光合作用转化能量。"}),
    ("notes", {"title": "光合作用", "sections": [{"title": "能量", "content": "光能转化为化学能"}]}),
    ("knowledge_cards", [{"front": "能量如何转化？", "back": "光能转化为化学能"}]),
])
def test_workspace_generation_reuses_source_and_preserves_chat(
    server_module, monkeypatch, kind, content,
):
    module, storage = server_module
    import filemate.llm_client as llm

    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm.LLMClient, "__init__", lambda *args: None)
    monkeypatch.setattr(llm.LLMClient, "call", lambda *args, **kwargs: json.dumps(content))
    sid = storage.save_source(original_name="课程.txt", source_path="/test/课程.txt", raw_text="光合作用转化能量。")
    storage.save_document_context(ctx_id="existing", source_id=sid, context_text="光合作用转化能量。", chat_history=[{"role": "user", "content": "我的问题"}])
    with TestClient(module.app) as client:
        denied = client.post(f"/knowledge/sources/{sid}/artifacts", json={"artifact_type": kind})
        assert denied.status_code == 422
        response = client.post(f"/knowledge/sources/{sid}/artifacts", json={"artifact_type": kind, "allow_external_model": True})
        assert response.status_code == 200
        artifact = response.json()["data"]
        assert artifact["source_id"] == sid
        assert artifact["artifact_type"] == kind
        assert len(storage.list_sources()) == 1
        assert storage.get_document_context("existing")["chat_history"][0]["content"] == "我的问题"


@pytest.mark.parametrize("output", ['not-json', '{}', '[]', '{"summary":""}'])
def test_workspace_rejects_invalid_generation_without_artifact(server_module, monkeypatch, output):
    module, storage = server_module
    import filemate.llm_client as llm

    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm.LLMClient, "__init__", lambda *args: None)
    monkeypatch.setattr(llm.LLMClient, "call", lambda *args, **kwargs: output)
    sid = storage.save_source(original_name="课程.txt", source_path="/test/课程.txt", raw_text="能量转化。")
    with TestClient(module.app) as client:
        response = client.post(f"/knowledge/sources/{sid}/artifacts", json={"artifact_type": "summary", "allow_external_model": True})
        assert response.status_code == 502
        assert storage.list_artifacts() == []
        assert client.post("/knowledge/sources/missing/contexts").status_code == 404


def test_workspace_question_generation_feeds_existing_quiz(server_module, monkeypatch):
    module, storage = server_module
    import filemate.llm_client as llm
    from filemate import study

    monkeypatch.setattr(llm.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm.LLMClient, "__init__", lambda *args: None)
    monkeypatch.setattr(study, "generate_questions_with_llm", lambda **kwargs: [{
        "question_type": "choice", "stem": "光合作用将光能转化为什么？",
        "options": ["A. 化学能", "B. 声能"], "answer": "A", "analysis": "资料指出转化为化学能。",
    }])
    sid = storage.save_source(original_name="课程.txt", source_path="/test/课程.txt", raw_text="光能转化为化学能。")
    with TestClient(module.app) as client:
        response = client.post(f"/knowledge/sources/{sid}/artifacts", json={"artifact_type": "questions", "count": 5, "allow_external_model": True})
        assert response.status_code == 200
        aid = response.json()["data"]["artifact_id"]
        result = client.post("/quiz/attempts", json={"artifact_id": aid, "question_index": 0, "user_answer": "B"})
        assert result.status_code == 200
        assert result.json()["data"]["is_correct"] is False
        assert len(client.get("/wrongbook").json()["data"]) == 1
        storage.delete_source(sid)
        assert storage.save_source_artifact(source_id=sid, artifact_type="notes", content={}, title="已删除") is None


def test_workspace_import_rejects_empty_text_and_cleans_copy(server_module):
    module, storage = server_module
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": ("blank.txt", b"   ")})
        assert response.status_code == 422
        assert storage.list_sources() == []
        assert not list(module.UPLOAD_ROOT.rglob("*.txt"))


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
    monkeypatch.setenv("FILEMATE_INTERVIEW_LOCAL_ONLY", "1")
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


def test_process_endpoint_reports_stage_failure(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阶段失败必须通过统一响应返回，不能误报 success=true。"""
    module, _ = server_module
    main_module = importlib.import_module("main")

    async def failed_process_single(
        file_path: str,
        *,
        skip_calendar: bool,
        db_path: str,
    ) -> ProcessingSession:
        del skip_calendar, db_path
        return ProcessingSession(
            session_id="failed-session",
            source_path=file_path,
            status=SessionStatus.FAILED,
            error="parse 失败: PDF 已加密",
        )

    monkeypatch.setattr(main_module, "process_single", failed_process_single)

    with TestClient(module.app) as client:
        response = client.post(
            "/process",
            files={"file": ("encrypted.pdf", b"encrypted", "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"] == "parse 失败: PDF 已加密"
    assert payload["data"]["status"] == "failed"


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
    assert allowed.headers["access-control-allow-origin"] == ("http://127.0.0.1:4173")

    rejected = client.options(
        "/",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers

    health = client.get("/api/health")
    assert health.json()["data"]["version"] == __version__


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


def test_unhandled_exception_uses_stable_envelope(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未捕获异常也应返回统一结构，而非 FastAPI 默认 detail。"""
    module, _ = server_module

    def boom(session_id: str) -> None:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(module._storage, "get_session", boom)

    with TestClient(module.app, raise_server_exceptions=False) as client:
        response = client.get("/sessions/any")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] == "服务器内部错误"
    assert "detail" not in body


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
    source_id = storage.save_source(
        original_name="网络.txt", source_path="/local/网络.txt",
        raw_text="TCP 使用三次握手建立连接。",
    )
    from filemate.understanding.retrieval import split_document
    storage.replace_source_chunks(source_id, split_document("TCP 使用三次握手建立连接。"))
    storage.save_document_context(
        ctx_id="ctx-chat",
        source_id=source_id,
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
            return "TCP 使用三次握手。[引用1]"

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
    assert response.json()["data"]["answer"] == "TCP 使用三次握手。[引用1]"
    assert "TCP 使用三次握手建立连接。" in received["context"]
    assert received["chat_history"][0]["content"] == "这是哪门课？"
    assert received["mode"] == "socratic"
    persisted = storage.get_document_context("ctx-chat")["chat_history"]
    assert persisted[-2:] == [
        {"role": "user", "content": "为什么是三次？"},
        {
            "role": "assistant",
            "content": "TCP 使用三次握手。[引用1]",
            "citations": response.json()["data"]["citations"],
        },
    ]


@pytest.mark.parametrize("with_source", [False, True])
def test_chat_without_evidence_does_not_call_model(server_module, monkeypatch, with_source):
    module, storage = server_module
    import filemate.understanding as understanding_module
    from filemate.understanding.retrieval import split_document

    source_id = None
    if with_source:
        source_id = storage.save_source(
            original_name="网络.txt", source_path="/local/网络.txt", raw_text="TCP 使用三次握手建立连接。",
        )

        storage.replace_source_chunks(source_id, split_document("TCP 使用三次握手建立连接。"))
    storage.save_document_context(
        ctx_id="no-hit", source_id=source_id, context_text="TCP 使用三次握手建立连接。",
    )

    def unexpected_model(*args, **kwargs):
        pytest.fail("无依据时不应创建或调用模型")

    monkeypatch.setattr(understanding_module, "AIChatbot", unexpected_model)
    with TestClient(module.app) as client:
        response = client.post("/ai/chat", json={"ctx_id": "no-hit", "question": "量子纠缠相对论"})
    assert response.status_code == 200
    assert response.json()["data"]["answerable"] is False
    assert response.json()["data"]["citations"] == []
    history = storage.get_document_context("no-hit")["chat_history"]
    assert len(history) == 2
    assert "没有找到" in history[-1]["content"]


def test_local_llm_settings_never_return_secret(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _ = server_module
    state = {"key": ""}

    def delete_key() -> bool:
        removed = bool(state["key"])
        state["key"] = ""
        return removed

    monkeypatch.setattr(module, "secure_store_available", lambda: True)
    monkeypatch.setattr(
        module,
        "resolve_api_key",
        lambda: (state["key"], "secure_store" if state["key"] else "none"),
    )
    monkeypatch.setattr(
        module,
        "set_stored_api_key",
        lambda api_key: state.update(key=api_key),
    )
    monkeypatch.setattr(module, "delete_stored_api_key", delete_key)

    with TestClient(module.app, client=("127.0.0.1", 51000)) as client:
        empty = client.get("/settings/llm")
        saved = client.put(
            "/settings/llm",
            json={"api_key": "sk-user-owned-secret"},
        )
        removed = client.delete("/settings/llm")

    assert empty.status_code == 200
    assert empty.json()["data"]["configured"] is False
    assert saved.status_code == 200
    assert saved.json()["data"]["configured"] is True
    assert "sk-user-owned-secret" not in saved.text
    assert removed.status_code == 200
    assert removed.json()["data"]["configured"] is False


def test_remote_client_cannot_manage_llm_secret(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module
    with TestClient(module.app, client=("203.0.113.10", 51000)) as client:
        response = client.put(
            "/settings/llm",
            json={"api_key": "sk-user-owned-secret"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "模型密钥只能在本机应用中配置"


def test_root_rejects_state_changing_methods(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module
    with TestClient(module.app) as client:
        response = client.post("/")

    assert response.status_code == 405


def test_untrusted_host_is_rejected(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module
    with TestClient(module.app) as client:
        response = client.get(
            "/api/health",
            headers={"host": "attacker.example"},
        )

    assert response.status_code == 400


@pytest.mark.parametrize("answer", ["TCP 使用三次握手。", "TCP 使用三次握手。[引用99]"])
def test_chat_rejects_missing_or_unknown_citation(server_module, monkeypatch, answer):
    module, storage = server_module
    import filemate.llm_client as llm_module
    import filemate.understanding as understanding_module
    from filemate.understanding.retrieval import split_document

    source_id = storage.save_source(original_name="网络.txt", source_path="/local/网络.txt", raw_text="TCP 使用三次握手建立连接。")
    storage.replace_source_chunks(source_id, split_document("TCP 使用三次握手建立连接。"))
    storage.save_document_context(ctx_id="bad-cite", source_id=source_id, context_text="TCP 使用三次握手。")
    monkeypatch.setattr(llm_module.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm_module, "LLMClient", lambda config: None)

    class FakeChatbot:
        def __init__(self, llm):
            pass

        def answer(self, *args, **kwargs):
            return answer

    monkeypatch.setattr(understanding_module, "AIChatbot", FakeChatbot)
    with TestClient(module.app) as client:
        response = client.post("/ai/chat", json={"ctx_id": "bad-cite", "question": "TCP 三次握手"})
    assert response.status_code == 502
    assert not storage.get_document_context("bad-cite")["chat_history"]


def test_slow_chat_keeps_health_endpoint_responsive(server_module, monkeypatch):
    import asyncio
    import threading

    import httpx

    import filemate.llm_client as llm_module
    import filemate.understanding as understanding_module
    from filemate.understanding.retrieval import split_document

    module, storage = server_module
    text = "TCP 使用三次握手建立连接。"
    source_id = storage.save_source(original_name="网络.txt", source_path="/local/network.txt", raw_text=text)
    storage.replace_source_chunks(source_id, split_document(text))
    storage.save_document_context(ctx_id="slow-chat", source_id=source_id, context_text=text)
    started, release = threading.Event(), threading.Event()
    released_by_health = []
    monkeypatch.setattr(llm_module.LLMConfig, "from_env", lambda: None)
    monkeypatch.setattr(llm_module, "LLMClient", lambda config: None)

    class SlowChatbot:
        def __init__(self, llm):
            pass

        def answer(self, *args, **kwargs):
            started.set()
            released_by_health.append(release.wait(timeout=2))
            return "TCP 使用三次握手。[引用1]"

    monkeypatch.setattr(understanding_module, "AIChatbot", SlowChatbot)

    async def exercise():
        transport = httpx.ASGITransport(app=module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat = asyncio.create_task(client.post("/ai/chat", json={"ctx_id": "slow-chat", "question": "TCP 三次握手"}))
            try:
                for _ in range(200):
                    if started.is_set():
                        break
                    await asyncio.sleep(.01)
                assert started.is_set()
                health = await client.get("/api/health")
                assert health.status_code == 200
            finally:
                release.set()
            assert (await chat).status_code == 200

    asyncio.run(exercise())
    assert released_by_health == [True]


def test_ai_context_routes_validate_limit_and_restore_history(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    storage.save_document_context(
        ctx_id="ctx-history",
        context_text="操作系统中的进程与线程。",
        chat_history=[
            {"role": "user", "content": "线程共享什么？"},
            {
                "role": "assistant",
                "content": "共享进程地址空间。",
                "citations": [{"id": 1, "source_name": "操作系统.pdf"}],
            },
        ],
    )

    with TestClient(module.app) as client:
        listed = client.get("/ai/contexts", params={"limit": 1})
        too_small = client.get("/ai/contexts", params={"limit": 0})
        too_large = client.get("/ai/contexts", params={"limit": 201})
        detail = client.get("/ai/contexts/ctx-history")
        missing = client.get("/ai/contexts/missing")

    assert listed.status_code == 200
    assert listed.json()["data"][0]["message_count"] == 2
    assert listed.json()["data"][0]["title"] == "线程共享什么？"
    assert too_small.status_code == 422
    assert too_large.status_code == 422
    assert detail.status_code == 200
    assert detail.json()["data"]["chat_history"][-1]["citations"][0]["id"] == 1
    assert missing.status_code == 404


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


def test_daily_coach_budget_order_and_diagnosis_persist(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="算法课.txt", source_path="/tmp/算法课.txt",
    )
    plan_artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="study_plan", content={"title": "算法复习"},
    )
    storage.create_study_plan(
        artifact_id=plan_artifact_id, source_id=source_id,
        plan={
            "title": "算法复习", "exam_date": "2099-12-31",
            "daily_minutes": 45, "goal": "完成算法复习",
            "daily_plan": [{
                "date": datetime.now().astimezone().date().isoformat(),
                "focus": "图算法", "tasks": ["阅读原资料"],
                "duration_minutes": 45,
            }],
        },
    )
    artifact_id = storage.save_artifact(
        source_id=source_id, artifact_type="questions",
        content=[
            {"stem": "队列有什么特点？", "answer": "先进先出"},
            {"stem": "BFS 如何遍历？", "answer": "逐层遍历"},
        ],
    )
    for question_index in (0, 1, 1):
        storage.record_quiz_attempt(
            artifact_id=artifact_id, question_index=question_index,
            user_answer="错误", is_correct=False, score=0, feedback="错误",
        )
    wrongs = storage.list_wrong_questions(source_id=source_id)
    first_id = next(item["wrong_id"] for item in wrongs if item["question_index"] == 0)
    second_id = next(item["wrong_id"] for item in wrongs if item["question_index"] == 1)

    with TestClient(module.app) as client:
        diagnosed = client.patch(f"/wrongbook/{second_id}/diagnosis", json={
            "error_cause": "reasoning_break", "note": "步骤不清",
        })
        assert diagnosed.status_code == 200
        initial = client.get("/review/today").json()["data"]
        assert initial["available_minutes"] == 60
        assert initial["recommended_minutes"] <= 60
        second = next(item for item in initial["items"] if item.get("wrong_id") == second_id)
        assert second["duration_minutes"] == 15
        assert "已确认错因：推理断点" in second["reason"]

        reordered = client.put("/review/today/preferences", json={
            "available_minutes": 30,
            "item_order": [f"wrong:{first_id}", f"wrong:{second_id}"],
        })
        assert reordered.status_code == 200
        queue = reordered.json()["data"]
        assert [item["wrong_id"] for item in queue["items"]] == [first_id, second_id]
        assert queue["recommended_minutes"] == 25
        assert queue["deferred_count"] == 1
        assert storage.get_daily_coach_preferences(queue["date"])["item_order"] == [
            f"wrong:{first_id}", f"wrong:{second_id}",
        ]
        assert client.get("/review/today").json()["data"]["available_minutes"] == 30

        shortened = client.put("/review/today/preferences", json={
            "available_minutes": 10,
            "item_order": [f"wrong:{first_id}", f"wrong:{second_id}"],
        }).json()["data"]
        assert [item["wrong_id"] for item in shortened["items"]] == [first_id]
        assert shortened["recommended_minutes"] == 10
        assert client.put("/review/today/preferences", json={
            "available_minutes": 5, "item_order": [],
        }).status_code == 422
        assert client.put("/review/today/preferences", json={
            "available_minutes": 30,
            "item_order": [f"wrong:{first_id}", f"wrong:{first_id}"],
        }).status_code == 422


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
            json={
                "answer": "我负责接口设计并通过测试将错误率降低了百分之三十。",
                "fluency_metrics": {
                    "duration_seconds": 18,
                    "filler_count": 1,
                    "long_pause_count": 0,
                    "source": "speech_recognition",
                    "markers": [
                        {"second": 6.2, "kind": "filler", "label": "出现口头语"}
                    ],
                },
            },
        ).json()["data"]
        analytics = client.get("/analytics/overview").json()["data"]

    assert started["current_index"] == 0
    assert started["agent_run_id"]
    assert answered["current_index"] == 1
    assert answered["latest_evaluation"]["score"] is None
    persisted = storage.get_interview(started["interview_id"])
    assert len(persisted["turns"]) == 1
    assert persisted["turns"][0]["score"] is None
    assert persisted["turns"][0]["scoring_mode"] == "local_fallback"
    assert "流畅性" in answered["latest_evaluation"]["dimensions"]
    assert persisted["turns"][0]["fluency_metrics"]["source"] == "speech_recognition"
    assert persisted["turns"][0]["fluency_metrics"]["markers"][0]["second"] == 6.2
    assert analytics["interview_count"] == 1
    assert analytics["average_interview_score"] is None
    assert analytics["assessed_interview_count"] == 0
    assert analytics["interview_dimensions"] == {}
    run = storage.get_agent_run(started["agent_run_id"])
    assert run is not None
    assert run["selected_agents"] == ["面试 Agent", "评价 Agent"]
    assert [step["agent_name"] for step in run["steps"]] == [
        "面试 Agent",
        "评价 Agent",
    ]
    assert "answer" not in run["steps"][1]["input_refs"]
    assert {item["memory_type"] for item in storage.list_agent_memories()} == {
        "session",
        "growth",
    }


def test_trust_center_enforces_rights_and_revokes_memory(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="公开课程说明.pdf",
        source_path="C:/资料/公开课程说明.pdf",
        raw_text="课程说明正文",
    )

    with TestClient(module.app) as client:
        initial = client.get("/trust/overview").json()["data"]
        rejected = client.put(
            f"/knowledge/sources/{source_id}/rights",
            json={
                "rights_status": "unconfirmed",
                "sharing_scope": "shareable",
            },
        )
        accepted = client.put(
            f"/knowledge/sources/{source_id}/rights",
            json={
                "rights_status": "public",
                "sharing_scope": "shareable",
                "note": "学校官网公开发布",
            },
        )
        after = client.get("/trust/overview").json()["data"]
        memory_id = after["memories"][0]["memory_id"]
        deleted = client.delete(f"/agents/memories/{memory_id}")
        final = client.get("/trust/overview").json()["data"]

    assert initial["source_rights"][0]["rights_status"] == "unconfirmed"
    assert rejected.status_code == 422
    assert accepted.status_code == 200
    assert accepted.json()["data"]["sharing_scope"] == "shareable"
    assert after["runs"][0]["selected_agents"] == ["安全 Agent"]
    assert after["runs"][0]["steps"][0]["agent_name"] == "安全 Agent"
    assert deleted.status_code == 200
    assert all(item["memory_id"] != memory_id for item in final["memories"])


def test_interview_question_bank_crud(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, _ = server_module
    with TestClient(module.app) as client:
        created = client.post(
            "/interview/questions",
            json={
                "scenario": "求职面试",
                "difficulty": "标准",
                "text": "请介绍一个你解决复杂问题的经历。",
            },
        ).json()["data"]
        question_id = created["id"]
        listed = client.get("/interview/questions").json()["data"]
        updated = client.patch(
            f"/interview/questions/{question_id}",
            json={"enabled": False},
        ).json()["data"]
        duplicate = client.post(
            "/interview/questions",
            json={
                "scenario": "求职面试",
                "difficulty": "标准",
                "text": "请介绍一个你解决复杂问题的经历。",
            },
        )
        blank_update = client.patch(
            f"/interview/questions/{question_id}",
            json={"text": "  "},
        )
        deleted = client.delete(f"/interview/questions/{question_id}").json()

    assert any(item["id"] == question_id for item in listed)
    assert updated["enabled"] == 0
    assert duplicate.status_code == 422
    assert "题目已存在" in duplicate.json()["error"]
    assert blank_update.status_code == 422
    assert "不能为空" in blank_update.json()["error"]
    assert deleted["success"] is True


def test_start_interview_uses_bank_and_scoring_mode(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    qid = storage.create_interview_question(
        scenario="求职面试",
        difficulty="标准",
        text="请介绍一个你解决复杂问题的经历，并说明结果。",
    )
    with TestClient(module.app) as client:
        started = client.post(
            "/interviews",
            json={"target_role": "后端开发", "scenario": "求职面试", "difficulty": "标准"},
        ).json()["data"]
        restored = client.get(f"/interviews/{started['interview_id']}").json()["data"]
        answered = client.post(
            f"/interviews/{started['interview_id']}/answers",
            json={"answer": "我先分析原因，再制定方案，最后完成并复盘。"},
        ).json()["data"]

    assert started["question_ids"][0] == qid
    assert started["question_ids"][1:] == [None] * 4
    assert len(started["question_ids"]) == len(started["questions"]) == 5
    assert restored["question_ids"] == started["question_ids"]
    assert started["questions"][0] == "请介绍一个你解决复杂问题的经历，并说明结果。"
    assert answered["latest_evaluation"]["scoring_mode"] in {"llm", "local_fallback"}


def test_interview_uses_selected_source_with_rights_boundary(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="FileMate竞赛申报书.pdf",
        source_path="C:/资料/FileMate竞赛申报书.pdf",
        raw_text="本项目将散落资料转化为可引用的学习资产。",
    )

    with TestClient(module.app) as client:
        private_session = client.post(
            "/interviews",
            json={
                "target_role": "创新赛道答辩",
                "scenario": "竞赛答辩",
                "difficulty": "标准",
                "source_id": source_id,
            },
        ).json()["data"]
        client.put(
            f"/knowledge/sources/{source_id}/rights",
            json={"rights_status": "self_owned", "sharing_scope": "private"},
        )
        authorized_session = client.post(
            "/interviews",
            json={
                "target_role": "创新赛道答辩",
                "scenario": "竞赛答辩",
                "difficulty": "标准",
                "source_id": source_id,
            },
        ).json()["data"]

    assert "FileMate竞赛申报书.pdf" in private_session["questions"][0]
    assert private_session["question_ids"][0] is None
    assert private_session["source_context"]["mode"] == "local_metadata_only"
    assert authorized_session["source_context"]["mode"] == "authorized_excerpt"
    run = storage.get_agent_run(authorized_session["agent_run_id"])
    assert run is not None
    assert run["context_refs"]["source_id"] == source_id
    assert "raw_text" not in run["context_refs"]


def test_delete_source_cleans_managed_inbox_file(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    inbox = module.UPLOAD_ROOT
    managed_dir = inbox / "upload-uuid"
    managed_dir.mkdir(parents=True, exist_ok=True)
    managed_file = managed_dir / "讲义.txt"
    managed_file.write_text("托管副本", encoding="utf-8")

    source_id = storage.save_source(
        original_name="讲义.txt",
        source_path=str(managed_file),
        raw_text="托管副本",
        file_hash="managed-hash",
    )

    with TestClient(module.app) as client:
        response = client.delete(f"/knowledge/sources/{source_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["managed_file"]["managed"] is True
    assert data["managed_file"]["removed"] is True
    assert not managed_file.exists()
    assert storage.get_source(source_id) is None


def test_delete_source_spares_external_file(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    module, storage = server_module
    external = tmp_path / "用户原文件.txt"
    external.write_text("用户原文件", encoding="utf-8")

    source_id = storage.save_source(
        original_name="用户原文件.txt",
        source_path=str(external),
        raw_text="用户原文件",
    )

    with TestClient(module.app) as client:
        response = client.delete(f"/knowledge/sources/{source_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["managed_file"]["managed"] is False
    assert data["external_files_untouched"] is True
    assert external.exists()
    assert storage.get_source(source_id) is None


def test_delete_source_does_not_follow_symlink_escape(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    module, storage = server_module
    inbox = module.UPLOAD_ROOT
    inbox.mkdir(parents=True, exist_ok=True)
    external = tmp_path / "真正外部.txt"
    external.write_text("外部文件", encoding="utf-8")
    link = inbox / "escape.txt"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("需要符号链接创建权限")

    source_id = storage.save_source(
        original_name="escape.txt",
        source_path=str(link),
        raw_text="外部文件",
    )

    with TestClient(module.app) as client:
        response = client.delete(f"/knowledge/sources/{source_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["managed_file"]["managed"] is False
    assert external.exists()


def test_delete_source_is_idempotent_404(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    source_id = storage.save_source(
        original_name="重复.txt",
        source_path="/tmp/重复.txt",
        raw_text="内容",
    )

    with TestClient(module.app) as client:
        first = client.delete(f"/knowledge/sources/{source_id}")
        second = client.delete(f"/knowledge/sources/{source_id}")

    assert first.status_code == 200
    assert second.status_code == 404
    assert second.json()["success"] is False


def test_delete_source_when_managed_file_already_missing(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    module, storage = server_module
    inbox = module.UPLOAD_ROOT
    inbox.mkdir(parents=True, exist_ok=True)
    missing = inbox / "已消失.txt"

    source_id = storage.save_source(
        original_name="已消失.txt",
        source_path=str(missing),
        raw_text="内容",
    )

    with TestClient(module.app) as client:
        response = client.delete(f"/knowledge/sources/{source_id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["managed_file"]["managed"] is True
    assert data["managed_file"]["exists"] is False
    assert data["managed_file"]["removed"] is False
    assert storage.get_source(source_id) is None
# ── A1 新增：/quiz/attempts 接入 check_answer + 旧格式兼容 ────────


def test_quiz_attempts_uses_check_answer_for_old_format_artifact(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """旧 Artifact 格式（type/question/options/answer）仍可作答，判题正确。"""
    module, storage = server_module
    document = tmp_path / "网络基础.txt"
    document.write_text("TCP 使用三次握手建立可靠连接。", encoding="utf-8")
    source_id = storage.save_source(
        original_name="网络基础.txt",
        source_path=str(document),
        raw_text=document.read_text(encoding="utf-8"),
        file_hash="tcp-hash",
    )
    # 使用旧格式持久化题目（模拟旧 Artifact：type/question/options/answer）
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        title="网络基础 · 练习题",
        content=[
            {
                "type": "填空题",
                "question": "TCP 使用几次握手建立连接？",
                "options": [],
                "answer": "三次",
                "explanation": "三次握手确保双方收发能力正常。",
            }
        ],
    )

    with TestClient(module.app) as client:
        wrong = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "两次",
            },
        )
        correct = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "三次",
            },
        )
        wrongbook_after_correct = client.get("/wrongbook")

    assert wrong.json()["data"]["is_correct"] is False
    assert correct.json()["data"]["is_correct"] is True
    # 旧格式答错 → 进错题本；答对 → 错题本中 error_count 仍保留但 correct_streak 增加
    items = wrongbook_after_correct.json()["data"]
    wrong_entry = next(item for item in items if item["question_index"] == 0)
    assert wrong_entry["error_count"] == 1
    assert wrong_entry["correct_streak"] == 1


def test_new_format_questions_also_work_in_quiz_attempts(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """新格式（question_type/stem/options/answer/analysis）同样可作答。"""
    module, storage = server_module
    source_id = storage.save_source(
        original_name="数学.txt",
        source_path=str(tmp_path / "数学.txt"),
        raw_text="矩阵乘法满足结合律。",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        title="数学 · 练习题",
        content=[
            {
                "question_type": "choice",
                "stem": "矩阵乘法满足什么性质？",
                "options": ["A. 结合律", "B. 交换律"],
                "answer": "A",
                "analysis": "矩阵乘法满足结合律但不满足交换律。",
            }
        ],
    )

    with TestClient(module.app) as client:
        correct = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "A. 结合律",
            },
        )
        wrong = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "B. 交换律",
            },
        )

    assert correct.json()["data"]["is_correct"] is True
    assert correct.json()["data"]["score"] == 1.0
    assert wrong.json()["data"]["is_correct"] is False
    assert wrong.json()["data"]["score"] == 0.0


def test_quiz_attempts_rejects_empty_answer(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """空答案应被判为错误（check_answer 拒绝空答案）。"""
    module, storage = server_module
    source_id = storage.save_source(
        original_name="测试.txt",
        source_path=str(tmp_path / "测试.txt"),
        raw_text="答案是 A",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        title="测试题",
        content=[
            {
                "question_type": "choice",
                "stem": "选A？",
                "options": ["A. 对", "B. 错"],
                "answer": "A",
            }
        ],
    )

    with TestClient(module.app) as client:
        response = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "",
            },
        )

    assert response.json()["data"]["is_correct"] is False
    assert response.json()["data"]["score"] == 0.0


def test_choice_answer_with_option_prefix_is_accepted(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
) -> None:
    """用户提交 'A. 结合律' 时，check_answer 应识别为正确（旧 _answer_score 会误判为 0）。"""
    module, storage = server_module
    source_id = storage.save_source(
        original_name="数学.txt",
        source_path=str(tmp_path / "数学.txt"),
        raw_text="矩阵乘法满足结合律。",
    )
    artifact_id = storage.save_artifact(
        source_id=source_id,
        artifact_type="questions",
        title="数学练习题",
        content=[
            {
                "question_type": "choice",
                "stem": "矩阵乘法满足什么性质？",
                "options": ["A. 结合律", "B. 交换律"],
                "answer": "A",
            }
        ],
    )

    with TestClient(module.app) as client:
        response = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "A. 结合律",
            },
        )

    # check_answer 对 choice 类型检查首字母：submitted.startswith(answer[:1])
    # "A. 结合律".startswith("A") → True
    # 旧 _answer_score 对 "A. 结合律" vs "A" 会返回 0.0（bigram 无交集）
    assert response.json()["data"]["is_correct"] is True
    assert response.json()["data"]["score"] == 1.0


def test_ai_questions_uses_generate_questions_with_llm(
    server_module: tuple[ModuleType, SQLiteStorage],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 /ai/questions 路由接入 generate_questions_with_llm（而非旧 QuestionExtractor）。"""
    import filemate.llm_client as llm_module
    import filemate.perception as perception_module
    import filemate.study as study_module

    module, _ = server_module

    calls: dict[str, Any] = {}

    class FakeConfig:
        @classmethod
        def from_env(cls) -> FakeConfig:
            return cls()

    class FakeLLM:
        def __init__(self, config: FakeConfig) -> None:
            self.config = config

    def fake_generate(llm, subject, knowledge_point, count, question_type="choice", context=None):
        calls["args"] = {
            "subject": subject,
            "knowledge_point": knowledge_point,
            "count": count,
            "question_type": question_type,
            "context": context,
        }
        return [
            {
                "subject": subject,
                "knowledge_point": knowledge_point,
                "question_type": question_type,
                "stem": f"测试题干 ({question_type})",
                "options": ["A. 正确", "B. 错误"],
                "answer": "A",
                "analysis": "测试解析",
            }
        ]

    class FakeParser:
        def parse(self, path: str) -> dict[str, Any]:
            return {"raw_text": "矩阵乘法满足结合律但不满足交换律。"}

    # 用假持久化替代 _persist_ai_context，避免 SQLite 锁冲突
    persisted: dict[str, Any] = {}

    def fake_persist(**kwargs):
        persisted.update(kwargs)
        return ("ctx-fake", "src-fake", "art-fake")

    monkeypatch.setattr(llm_module, "LLMConfig", FakeConfig)
    monkeypatch.setattr(llm_module, "LLMClient", FakeLLM)
    monkeypatch.setattr(study_module, "generate_questions_with_llm", fake_generate)
    monkeypatch.setattr(perception_module, "FileParser", FakeParser)
    monkeypatch.setattr(module, "_persist_ai_context", fake_persist)

    document = tmp_path / "数学讲义.txt"
    document.write_text("矩阵乘法满足结合律。", encoding="utf-8")

    with TestClient(module.app) as client:
        response = client.post(
            "/ai/questions",
            files={"file": ("数学讲义.txt", document.read_bytes(), "text/plain")},
            data={"question_types": "choice", "num_questions": "1"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["questions_count"] == 1
    assert data["questions"][0]["question_type"] == "choice"
    assert data["questions"][0]["stem"] == "测试题干 (choice)"
    # 确认调用的是 generate_questions_with_llm（subject 来自文件名）
    assert "subject" in calls.get("args", {})
    assert calls["args"]["subject"] == "数学讲义"
    assert calls["args"]["question_type"] == "choice"
    assert calls["args"]["count"] == 1
    assert persisted["artifact_type"] == "questions"


def test_ai_questions_distributes_requested_count_across_types(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多题型生成应分配余数，不能因整除少生成题目。"""
    import filemate.llm_client as llm_module
    import filemate.perception as perception_module
    import filemate.study as study_module

    module, _ = server_module
    requested: list[tuple[str, int]] = []

    class FakeConfig:
        @classmethod
        def from_env(cls) -> FakeConfig:
            return cls()

    class FakeLLM:
        def __init__(self, config: FakeConfig) -> None:
            self.config = config

    class FakeParser:
        def parse(self, path: str) -> dict[str, Any]:
            return {"raw_text": "用于匿名测试的课程内容。"}

    def fake_generate(**kwargs: Any) -> list[dict[str, Any]]:
        question_type = str(kwargs["question_type"])
        count = int(kwargs["count"])
        requested.append((question_type, count))
        return [
            {
                "question_type": question_type,
                "stem": f"{question_type}-{index}",
                "answer": "A",
            }
            for index in range(count)
        ]

    monkeypatch.setattr(llm_module, "LLMConfig", FakeConfig)
    monkeypatch.setattr(llm_module, "LLMClient", FakeLLM)
    monkeypatch.setattr(perception_module, "FileParser", FakeParser)
    monkeypatch.setattr(study_module, "generate_questions_with_llm", fake_generate)
    monkeypatch.setattr(
        module,
        "_persist_ai_context",
        lambda **kwargs: ("ctx", "source", "artifact"),
    )

    with TestClient(module.app) as client:
        response = client.post(
            "/ai/questions",
            files={"file": ("课程.txt", b"content", "text/plain")},
            data={"question_types": "choice,fill", "num_questions": "5"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["questions_count"] == 5
    assert requested == [("choice", 3), ("fill", 2)]


def test_ai_questions_does_not_persist_empty_generation(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """所有模型调用失败时应返回 502，不能保存空题集并误报成功。"""
    import filemate.llm_client as llm_module
    import filemate.perception as perception_module
    import filemate.study as study_module

    module, _ = server_module

    class FakeConfig:
        @classmethod
        def from_env(cls) -> FakeConfig:
            return cls()

    class FakeLLM:
        def __init__(self, config: FakeConfig) -> None:
            self.config = config

    class FakeParser:
        def parse(self, path: str) -> dict[str, Any]:
            return {"raw_text": "用于匿名测试的课程内容。"}

    def fail_generation(**kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("模拟模型不可用")

    monkeypatch.setattr(llm_module, "LLMConfig", FakeConfig)
    monkeypatch.setattr(llm_module, "LLMClient", FakeLLM)
    monkeypatch.setattr(perception_module, "FileParser", FakeParser)
    monkeypatch.setattr(study_module, "generate_questions_with_llm", fail_generation)

    persisted = False

    def fail_if_persisted(**kwargs: Any) -> tuple[str, str, str]:
        nonlocal persisted
        persisted = True
        return ("ctx", "source", "artifact")

    monkeypatch.setattr(module, "_persist_ai_context", fail_if_persisted)

    with TestClient(module.app) as client:
        response = client.post(
            "/ai/questions",
            files={"file": ("课程.txt", b"content", "text/plain")},
            data={"question_types": "choice,fill", "num_questions": "5"},
        )

    assert response.status_code == 502
    assert response.json()["success"] is False
    assert persisted is False


def test_ai_questions_surfaces_parser_error(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 出题应保留加密/损坏文件的可操作错误信息。"""
    import filemate.perception as perception_module

    module, _ = server_module

    class FakeParser:
        def parse(self, path: str) -> dict[str, Any]:
            return {
                "raw_text": "",
                "metadata": {"encrypted": True},
                "error": "PDF 已加密，请先解密后重新上传",
            }

    monkeypatch.setattr(perception_module, "FileParser", FakeParser)

    with TestClient(module.app) as client:
        response = client.post(
            "/ai/questions",
            files={"file": ("encrypted.pdf", b"encrypted", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "PDF 已加密，请先解密后重新上传"


def test_quiz_attempt_rejects_malformed_question_artifact(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    """损坏的题目 Artifact 应返回 422，而不是触发服务端 500。"""
    module, storage = server_module
    artifact_id = storage.save_artifact(
        artifact_type="questions",
        title="损坏题集",
        content=["not-a-question"],
    )

    with TestClient(module.app) as client:
        response = client.post(
            "/quiz/attempts",
            json={
                "artifact_id": artifact_id,
                "question_index": 0,
                "user_answer": "A",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "题目数据格式无效"


def test_run_server_reads_bind_address_from_environment(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产容器可改监听地址，桌面端仍复用同一本地启动入口。"""
    module, _ = server_module
    uvicorn_module = importlib.import_module("uvicorn")
    captured: dict[str, Any] = {}

    class FakeConfig:
        def __init__(
            self,
            app: Any,
            *,
            host: str,
            port: int,
            log_level: str,
        ) -> None:
            captured.update(
                app=app,
                host=host,
                port=port,
                log_level=log_level,
            )

    class FakeServer:
        def __init__(self, config: FakeConfig) -> None:
            captured["config"] = config

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setenv("FILEMATE_HOST", "0.0.0.0")
    monkeypatch.setenv("FILEMATE_PORT", "9000")
    monkeypatch.setattr(uvicorn_module, "Config", FakeConfig)
    monkeypatch.setattr(uvicorn_module, "Server", FakeServer)

    module.run_server()

    assert captured["app"] is module.app
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9000
    assert captured["log_level"] == "info"
    assert captured["ran"] is True


@pytest.mark.parametrize("port", ["invalid", "0", "65536"])
def test_run_server_rejects_invalid_port(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    """无效监听端口必须在启动前给出明确错误。"""
    module, _ = server_module
    monkeypatch.setenv("FILEMATE_PORT", port)

    with pytest.raises(ValueError, match="FILEMATE_PORT"):
        module.run_server()


@pytest.mark.parametrize("suffix", ["md", "markdown", "c", "cpp", "h", "hpp", "py", "java", "js", "ts"])
def test_learning_text_import_keeps_original_citations_and_context(
    server_module: tuple[ModuleType, SQLiteStorage],
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
) -> None:
    """文本学习资料复用存储/引用链，不调用模型或执行源码。"""
    module, storage = server_module
    import filemate.llm_client as llm

    def unexpected(*args: Any, **kwargs: Any) -> None:
        pytest.fail("本地文本导入不能调用模型")

    monkeypatch.setattr(llm.LLMClient, "call", unexpected)
    name = f"原创-栈笔记.{suffix.upper()}"
    text = f"# 栈与队列 {suffix}\n```cpp\npush(value); // 入栈\n```\n栈遵循后进先出。"
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": (name, text.encode("utf-8"))})
        assert response.status_code == 200
        source = response.json()["data"]
        assert source["original_name"] == name
        assert source["raw_text"] == text
        assert "source_path" not in source
        source_id = source["source_id"]
        results = client.get("/knowledge/search", params={"q": "栈", "source_id": source_id}).json()["data"]
        assert results and all(result["source_id"] == source_id for result in results)
        assert "push(value)" in results[0]["excerpt"]
        context = client.post(f"/knowledge/sources/{source_id}/contexts").json()["data"]
        assert context["source_id"] == source_id
        assert context["context_text"] == text
        assert storage.list_artifacts() == []
        repeated = client.post("/knowledge/import", files={"file": (name, text.encode("utf-8"))})
        assert repeated.json()["data"]["source_id"] == source_id
        assert len(storage.list_sources()) == 1


@pytest.mark.parametrize("name,payload", [("错误编码.md", b"\xff\xfe\x00"), ("空白.cpp", b" \n\t")])
def test_invalid_learning_text_is_rejected_and_upload_removed(
    server_module: tuple[ModuleType, SQLiteStorage], name: str, payload: bytes,
) -> None:
    """解析失败或空白正文不留下资料和托管副本。"""
    module, storage = server_module
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": (name, payload)})
        assert response.status_code == 422
        assert storage.list_sources() == []
        assert not list(module.UPLOAD_ROOT.rglob(name))


@pytest.mark.parametrize("name", ["run.exe", "script.ps1", "page.html", "bundle.zip"])
def test_learning_text_extension_allowlist_rejects_other_uploads(
    server_module: tuple[ModuleType, SQLiteStorage], name: str,
) -> None:
    """学习资料扩展不接受程序包、脚本或网页文件。"""
    module, storage = server_module
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": (name, b"text")})
        assert response.status_code == 400
        assert storage.list_sources() == []
        assert not module.UPLOAD_ROOT.exists()


def test_python_learning_source_is_never_executed(
    server_module: tuple[ModuleType, SQLiteStorage], tmp_path: Path,
) -> None:
    """Python资料仅保存原文，不产生源码中的文件副作用。"""
    module, _ = server_module
    marker = tmp_path / "must-not-exist.txt"
    code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    with TestClient(module.app) as client:
        response = client.post("/knowledge/import", files={"file": ("学习代码.py", code.encode())})
        assert response.status_code == 200
        assert response.json()["data"]["raw_text"] == code
    assert not marker.exists()


def test_classification_upload_contract_keeps_existing_formats(
    server_module: tuple[ModuleType, SQLiteStorage],
) -> None:
    """代码学习入口扩展不会改变文件分类的上传合同。"""
    module, _ = server_module
    with TestClient(module.app) as client:
        response = client.post("/process", files={"file": ("笔记.md", b"# notes")})
        assert response.status_code == 400
