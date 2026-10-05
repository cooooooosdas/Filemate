# ruff: noqa: F811
"""技能树的真实练习证据、持久化、冲突和隔离合同。"""

from copy import deepcopy

from fastapi.testclient import TestClient

from filemate.study.skills import SkillTreeRepository
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_skill_tree_uses_persistent_quiz_evidence_and_invalidates_edits(server_module):
    module, store = server_module
    question = {"question_type": "fill", "stem": "合成课程的二分查找前提？", "answer": "有序"}
    aid = store.save_artifact(artifact_type="questions", content=[question])
    body = {"schema_version": 1, "revision": 0, "skills": [{"skill_id": "binary", "label": "独立实现二分查找", "criteria": [{"kind": "quiz", "target_id": aid, "question_index": 0, "required_successes": 2}]}]}
    with TestClient(module.app) as client:
        tree = client.put("/api/skills/tree", json=body).json()["data"]
        assert tree["states"]["binary"] == "in_progress" and tree["revision"] == 1
        assert client.put("/api/skills/tree", json=body).status_code == 409
        for _ in range(2):
            assert client.post("/quiz/attempts", json={"artifact_id": aid, "question_index": 0, "user_answer": "有序"}).status_code == 200
        observed = client.get("/api/skills/tree").json()["data"]
        assert observed["states"]["binary"] == "conditions_met"
        assert observed["evidence"]["binary"][0]["observed_successes"] == 2
        assert len(observed["evidence"]["binary"][0]["records"]) == 2
        changed = {**question, "stem": "新题干", "answer": "新答案"}
        assert client.patch(f"/knowledge/artifacts/{aid}", json={"title": "已修订", "content": [changed]}).status_code == 200
        assert client.get("/api/skills/tree").json()["data"]["states"]["binary"] == "in_progress"
        assert client.patch("/knowledge/artifacts/personal-skill-tree-v1", json={"title": "绕过合同", "content": {}}).status_code == 409
    reopened = type(store)(store.db_path)
    assert SkillTreeRepository(reopened).read().skills[0].label == "独立实现二分查找"
    reopened.close()


def test_skill_tree_rejects_cycles_duplicates_and_missing_owned_evidence(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        base = {"revision": 0, "skills": [{"skill_id": "one", "label": "一", "prerequisites": ["two"]}, {"skill_id": "two", "label": "二", "prerequisites": ["one"]}]}
        assert client.put("/api/skills/tree", json=base).status_code == 409
        base["skills"][0]["prerequisites"] = []
        assert client.put("/api/skills/tree", json=base).status_code == 200
        invalid = {"revision": 1, "skills": [{"skill_id": "one", "label": "一", "criteria": [{"kind": "quiz", "target_id": "other-user-artifact", "question_index": 0}]}]}
        assert client.put("/api/skills/tree", json=invalid).status_code == 409
        invalid["skills"].append(deepcopy(invalid["skills"][0]))
        assert client.put("/api/skills/tree", json=invalid).status_code == 409
        assert client.put("/api/skills/tree", json={"revision": 1, "skills": [], "fake_mastery": 100}).status_code == 422
    assert len(SkillTreeRepository(store).read().skills) == 2


def test_skill_tree_searches_old_targets_and_can_be_disabled(server_module, monkeypatch):
    module, store = server_module
    for index in range(210):
        store.save_artifact(artifact_type="questions", content=[{"question": f"原创合成目标题{index:03d}", "answer": "答案"}])
    with TestClient(module.app) as client:
        targets = client.get("/api/skills/targets?q=原创合成目标题000").json()["data"]
        assert len(targets) == 1 and targets[0]["question_index"] == 0
        assert client.get("/api/skills/targets?q=%").json()["data"] == []
        monkeypatch.setenv("FILEMATE_ENABLE_SKILL_TREE", "0")
        assert client.get("/api/skills/tree").status_code == 503
        assert client.get("/knowledge/sources").status_code == 200
