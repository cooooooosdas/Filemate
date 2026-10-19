# ruff: noqa: F811
"""Synthetic authenticated API, rollback and privacy contracts for timed practice."""

from uuid import uuid4

from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_interview_coach_api import api  # noqa: F401


def prepare(client):
    return client.post(
        "/interviews/runtime",
        json={
            "request_key": uuid4().hex,
            "content": {
                "configuration": {
                    "execution_mode": "timed",
                    "category": "creator",
                    "track": "knowledge",
                },
                "target_role": "知识讲解",
                "project_details": "C++：RAII关联资源与对象生命周期。",
            },
        },
    )


def action(client, state, kind, **fields):
    runtime = state["session"]["runtime"]
    return client.post(
        f"/interviews/{state['session']['interview_id']}/runtime/commands",
        json={
            "request_key": uuid4().hex,
            "expected_revision": runtime["revision"],
            "expected_token": runtime["version_token"],
            "task_index": runtime["current_task"],
            "kind": kind,
            **fields,
        },
    )


def test_runtime_flags_guard_old_paths_and_export_restore(api, monkeypatch):
    client, _module = api
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_RUNTIME", "1")
    response = prepare(client)
    assert response.status_code == 200, response.text
    p = response.json()["data"]
    s = action(client, p, "start").json()["data"]["snapshot"]
    sid = s["session"]["interview_id"]
    deadline = s["session"]["runtime"]["deadline"]
    s = action(client, s, "submit", answer="我通过真实测试验证了索引").json()["data"]["snapshot"]
    for path, body in [
        ("/answers", {"answer": "旧路由"}),
        (
            "/coach/answers",
            {
                "request_key": uuid4().hex,
                "expected_revision": s["revision"],
                "question_index": 0,
                "expected_attempt_id": s["current_attempt"]["attempt_id"],
                "answer": "旧教练",
            },
        ),
    ]:
        denied = client.post(f"/interviews/{sid}{path}", json=body)
        assert denied.status_code == 409
        assert denied.json()["data"]["error_code"] == "runtime_command_required"
    raw = client.get("/api/privacy/export").content
    preview = client.post(
        "/api/privacy/restore-preview", files={"file": ("synthetic.zip", raw, "application/zip")}
    ).json()["data"]
    restored = client.post("/api/privacy/restore", json={**preview, "confirmed": True})
    assert restored.status_code == 200, restored.text
    r = client.get(f"/interviews/{sid}/runtime").json()["data"]
    assert r["session"]["runtime"]["status"] == "interrupted"
    assert r["session"]["runtime"]["deadline"] == deadline
    assert r["session"]["runtime"]["version_token"] != s["session"]["runtime"]["version_token"]
    assert action(client, s, "resume").status_code == 409
    r = action(client, r, "resume").json()["data"]["snapshot"]
    assert r["session"]["runtime"]["deadline"] == deadline
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_RUNTIME", "0")
    assert prepare(client).status_code == 503
    assert action(client, r, "finish").status_code == 503
    assert client.get(f"/interviews/{sid}/runtime").status_code == 200
    assert client.get("/api/privacy/export").status_code == 200


def test_runtime_input_validation(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_RUNTIME", "1")
    assert (
        client.post("/interviews/runtime", json={"request_key": "x", "content": {}}).status_code
        == 422
    )
    assert client.get("/interviews/missing/runtime").status_code == 404
    response = client.post(
        "/interviews/runtime",
        json={
            "request_key": uuid4().hex,
            "content": {
                "configuration": {
                    "execution_mode": "timed",
                    "category": "creator",
                    "track": "commerce",
                }
            },
        },
    )
    assert response.status_code == 422


def test_runtime_tenant_isolation(account_server, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_RUNTIME", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_COACH", "1")
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice, email="alice-runtime@example.invalid").status_code == 200
        assert register(bob, email="bob-runtime@example.invalid").status_code == 200
        s = prepare(alice).json()["data"]
        sid = s["session"]["interview_id"]
        assert bob.get(f"/interviews/{sid}/runtime").status_code == 404
        assert action(bob, s, "start").status_code == 404
        assert action(alice, s, "start").status_code == 200
