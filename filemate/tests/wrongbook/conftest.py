"""Synthetic-only workspaces for review foundation tests."""

from datetime import datetime, timezone

import pytest

from filemate.execution.storage import SQLiteStorage


@pytest.fixture
def review_store(tmp_path):
    store = SQLiteStorage(tmp_path / "review.db")
    store.init_schema()
    source = store.save_source(original_name="原创合成数据结构", source_path="synthetic.txt")
    questions = [
        {"question_type": "choice", "stem": "栈遵循什么顺序？", "options": ["后进先出", "先进先出"], "answer": "A", "analysis": "栈后进先出。"},
        {"question_type": "short_answer", "stem": "解释栈和队列。", "answer": "栈后进先出"},
        {"question_type": "fill", "stem": "队列遵循什么顺序？", "answer": "先进先出"},
    ]
    artifact = store.save_artifact(source_id=source, artifact_type="questions", content=questions)
    now = [datetime(2026, 10, 26, 8, tzinfo=timezone.utc)]
    yield store, source, artifact, questions, now
    store.close()


def answer_payload(fixture, answer="B", *, index=0, key="synthetic-answer-key-0001", **extra):
    return {"artifact_id": fixture[2], "question_index": index, "expected_question": fixture[3][index],
            "user_answer": answer, "request_key": key, **extra}
