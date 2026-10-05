# ruff: noqa: F811
"""坏模型输出不保存，历史坏题不生成评分证据。"""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from filemate.study.generator import generate_questions_with_llm
from filemate.study.question_validation import validate_question, validate_questions
from filemate.tests.test_server_persistence import server_module  # noqa: F401

GOOD = {"question_type": "choice", "stem": "合成选择题？", "options": ["A. 一", "B. 二"], "answer": "B"}


@pytest.mark.parametrize("raw", [
    [], [None], [{"stem": "no answer"}], [{**GOOD, "answer": ""}], [{**GOOD, "answer": None}],
    [{**GOOD, "answer": "C"}], [{**GOOD, "answer": "B. 三"}], [{**GOOD, "question_type": "invented"}],
    [{**GOOD, "options": []}], [{**GOOD, "options": "A/B"}], [{**GOOD, "options": ["A. 一", "A. 二"]}],
    [{**GOOD, "options": ["A. 一", "B. 一"]}], [{**GOOD, "stem": " "}], [{**GOOD, "stem": "x" * 4001}],
    [{**GOOD, "analysis": []}], [GOOD, GOOD], [GOOD, {"stem": "bad"}],
    [{**GOOD, "question_type": "fill"}], [{**GOOD, "options": [1, 2]}],
])
def test_invalid_model_batch_is_rejected_whole(raw):
    with pytest.raises(RuntimeError, match="AI 出题失败"):
        generate_questions_with_llm(lambda **kwargs: raw, "合成", "合成", 5)


def test_valid_questions_are_not_mutated_and_cannot_change_requested_type():
    raw = [{**GOOD, "options": ["一", "二"], "answer": "二"}]
    before = deepcopy(raw)
    result = validate_questions(raw)
    assert result[0]["answer"] == "B" and result[0]["options"] == ["A. 一", "B. 二"]
    assert raw == before
    with pytest.raises(RuntimeError, match="题型或数量"):
        generate_questions_with_llm(lambda **kwargs: [{"question_type": "fill", "stem": "合成填空", "answer": "二"}], "合成", "合成", 1, question_type="choice")
    with pytest.raises(ValueError):
        validate_question({"question": "legacy", "answer": ""}, legacy=True)


def test_invalid_legacy_artifact_is_preserved_and_not_graded(server_module):
    module, store = server_module
    aid = store.save_artifact(artifact_type="questions", content=[{"stem": "缺少答案的历史题"}])
    with TestClient(module.app) as client:
        artifact = client.get(f"/knowledge/artifacts/{aid}").json()["data"]
        assert artifact["metadata"]["question_data_error"] is True
        attempt = client.post("/quiz/attempts", json={"artifact_id": aid, "question_index": 0, "user_answer": "随便回答"})
        assert attempt.status_code == 422
        assert store._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 0
        assert store.get_artifact(aid)["content"] == [{"stem": "缺少答案的历史题"}]
        invalid_edit = client.patch(f"/knowledge/artifacts/{aid}", json={"title": "修复", "content": [{**GOOD, "answer": "Z"}]})
        assert invalid_edit.status_code == 422
        assert store.get_artifact(aid)["content"] == [{"stem": "缺少答案的历史题"}]
        repaired = client.patch(f"/knowledge/artifacts/{aid}", json={"title": "已修复", "content": [GOOD]})
        assert repaired.status_code == 200
        assert not client.get(f"/knowledge/artifacts/{aid}").json()["data"]["metadata"].get("question_data_error")
        assert client.post("/quiz/attempts", json={"artifact_id": aid, "question_index": 0, "user_answer": "B", "expected_question": GOOD}).json()["data"]["is_correct"] is True


def test_bad_generated_source_artifact_does_not_persist(server_module, monkeypatch):
    module, store = server_module
    from filemate.llm_client import LLMClient, LLMConfig
    monkeypatch.setattr(LLMConfig, "from_env", classmethod(lambda cls: cls()))
    monkeypatch.setattr(LLMClient, "call", lambda *args, **kwargs: '[{"stem":"no answer"}]')
    sid = store.save_source(original_name="合成材料", source_path="synthetic", raw_text="原创合成定义")
    with TestClient(module.app) as client:
        response = client.post(f"/knowledge/sources/{sid}/artifacts", json={"artifact_type": "questions", "allow_external_model": True})
    assert response.status_code == 502
    assert store.list_artifacts(source_id=sid) == []
    assert store.get_source(sid)["raw_text"] == "原创合成定义"
