# ruff: noqa: F811
"""Real HTTP contracts remain opt-in, tenant scoped and independent of LLMs."""

import json

import pytest
from fastapi.testclient import TestClient

from filemate.tests.test_server_persistence import server_module  # noqa: F401


def seed(store):
    sid = store.save_source(original_name="合成课程", source_path="synthetic.txt")
    question = {"question_type": "choice", "stem": "请选择栈的次序", "options": ["后进先出", "先进先出"], "answer": "A"}
    aid = store.save_artifact(source_id=sid, artifact_type="questions", content=[question])
    return {"artifact_id": aid, "question_index": 0, "expected_question": question,
            "user_answer": "B", "request_key": "synthetic-http-answer-key"}


def test_disabled_writes_leave_history_readable(server_module, monkeypatch):
    module, store = server_module
    body = seed(store)
    monkeypatch.delenv("FILEMATE_ENABLE_WRONGBOOK_V2", raising=False)
    with TestClient(module.app) as client:
        assert client.post("/wrongbook/v2/attempts", json=body).status_code == 503
        assert client.get("/wrongbook/v2/summary").status_code == 200
        monkeypatch.setenv("FILEMATE_ENABLE_WRONGBOOK_V2", "1")
        response = client.post("/wrongbook/v2/attempts", json=body)
        assert response.status_code == 200, response.text
        result = response.json()["data"]
        wid = result["wrong_id"]
        monkeypatch.setenv("FILEMATE_ENABLE_WRONGBOOK_V2", "0")
        assert client.get(f"/wrongbook/v2/{wid}").json()["data"]["wrong_id"] == wid
        assert client.get(f"/wrongbook/v2/{wid}/attempts").json()["data"]["total"] == 1
        assert client.post("/quiz/attempts", json=body).status_code == 409


@pytest.mark.parametrize("change", [{"unexpected": "secret-key-must-not-echo"}, {"user_answer": ""},
                                    {"question_index": -1}, {"request_key": "short"}, {"duration_ms": True}])
def test_http_rejects_invalid_commands_without_echoing_sensitive_input(server_module, monkeypatch, change):
    module, store = server_module
    body = seed(store)
    monkeypatch.setenv("FILEMATE_ENABLE_WRONGBOOK_V2", "1")
    with TestClient(module.app) as client:
        response = client.post("/wrongbook/v2/attempts", json={**body, **change})
        assert response.status_code == 422
        assert "secret-key-must-not-echo" not in response.text
        assert store._conn().execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0] == 0


def test_static_routes_errors_history_query_and_confirm_contract(server_module, monkeypatch):
    module, store = server_module
    body = seed(store)
    monkeypatch.setenv("FILEMATE_ENABLE_WRONGBOOK_V2", "1")
    with TestClient(module.app) as client:
        assert client.get("/wrongbook/v2/summary").status_code == 200
        assert client.get("/wrongbook/v2/missing").status_code == 404
        assert client.post("/wrongbook/v2/attempts", json={**body, "artifact_id": "missing"}).status_code == 404
        result = client.post("/wrongbook/v2/attempts", json=body).json()["data"]
        wid = result["wrong_id"]
        assert client.post("/wrongbook/v2/attempts", json={**body, "user_answer": "A"}).status_code == 409
        for suffix in ("?limit=0", "?limit=1&limit=2", "?unknown=x"):
            assert client.get(f"/wrongbook/v2/{wid}/attempts" + suffix).status_code == 422
        command = {"action": "pause", "request_key": "synthetic-http-schedule-key", "expected_revision": 1}
        preview = client.post(f"/wrongbook/v2/{wid}/schedule-preview", json=command)
        assert preview.status_code == 200, preview.text
        token = preview.json()["data"]["confirmation_token"]
        confirm = {**command, "confirmation_token": token, "confirmed": True}
        assert client.post(f"/wrongbook/v2/{wid}/schedule-confirm", json={**confirm, "confirmed": False}).status_code == 422
        first = client.post(f"/wrongbook/v2/{wid}/schedule-confirm", json=confirm)
        assert first.status_code == 200, first.text
        assert client.post(f"/wrongbook/v2/{wid}/schedule-confirm", json=confirm).json() == first.json()
        assert client.get(f"/wrongbook/v2/{wid}/events").json()["data"]["total"] == 2


def test_reads_never_call_models_and_database_errors_are_redacted(server_module, monkeypatch):
    import sqlite3

    from filemate.llm_client import LLMClient
    from filemate.wrongbook.repository import ReviewRepository

    module, store = server_module
    seed(store)

    def forbidden(*args, **kwargs):
        raise AssertionError("read attempted model call")

    monkeypatch.setattr(LLMClient, "call", forbidden)
    with TestClient(module.app) as client:
        assert client.get("/wrongbook/v2/summary").status_code == 200

        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError("private-db-location-and-secret")

        monkeypatch.setattr(ReviewRepository, "summary", unavailable)
        response = client.get("/wrongbook/v2/summary")
        assert response.status_code == 503 and "private-db-location-and-secret" not in response.text


def test_today_full_count_is_separate_from_candidate_limit(server_module):
    module, store = server_module
    body = seed(store)
    conn = store._conn()
    conn.executemany("""INSERT INTO wrong_questions
        (wrong_id,artifact_id,question_index,question,next_review_at)
        VALUES (?,?,?,?,'2000-01-01T00:00:00+00:00')""", [
            (f"synthetic-wrong-{i}", body["artifact_id"], i, json.dumps(body["expected_question"])) for i in range(55)
        ])
    conn.commit()
    with TestClient(module.app) as client:
        response = client.get("/review/today")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["pending_wrong_count"] == 55
        assert data["wrong_candidate_count"] == 50
        assert data["deferred_count"] == 55 - len(data["items"])
