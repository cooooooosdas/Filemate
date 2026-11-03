# ruff: noqa: F811
"""Strict coach HTTP contracts, authenticated spaces and request-only credentials."""

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401

from .conftest import coach_module, read_context
from .test_requests import request, service_case  # noqa: F401

ROOT = "/api/learning/orchestrator/coach"


@pytest.fixture
def coach_http(service_case, monkeypatch):
    api = coach_module("api")
    monkeypatch.setattr(api, "utc_now", service_case["clock"])
    app = FastAPI()
    app.include_router(api.create_router(lambda: service_case["storage"]))
    with TestClient(app) as client:
        yield client


def test_strict_body_and_safe_errors(coach_http, service_case, monkeypatch):
    body = service_case["input_data"]
    for query in ("?workspace=other", "?x=1&x=2"):
        assert coach_http.get(ROOT + "/capabilities" + query).status_code == 422
    assert coach_http.post(ROOT + "/context", content=b"x" * 65537).status_code == 413
    for raw in ('{"scope":{},"scope":{}}', '{"scope":{},"extra":NaN}'):
        response = coach_http.post(ROOT + "/context", content=raw)
        assert response.status_code == 422 and "NaN" not in response.text
    for changes in (
        {"workspace": "private-secret"},
        {"db_path": "private-secret"},
        {"model_url": "https://private-secret.invalid"},
        {"question": "x" * 2001},
        {"days": [{"study_date": "2026-10-31", "options": {"available_minutes": True}}]},
    ):
        response = coach_http.post(ROOT + "/context", json=body | changes)
        assert response.status_code == 422 and "private-secret" not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert coach_http.get(ROOT + "/requests/short").status_code == 422
    assert coach_http.post(ROOT + "/day", json={"study_date": "2026-02-30"}).status_code == 422

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("synthetic-private-storage-path")

    monkeypatch.setattr(coach_module("context").CoachContextReader, "read", broken)
    response = coach_http.post(ROOT + "/context", json=body)
    assert response.status_code == 503 and "private" not in response.text


def test_rule_http_round_trip_and_catalog_never_calls_model(coach_http, service_case, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("rule/read route requested credentials")

    monkeypatch.setattr(coach_module("service").LLMConfig, "from_env", forbidden)
    context = coach_http.post(ROOT + "/context", json=service_case["input_data"])
    assert context.status_code == 200
    assert "external_digest" in context.json()["data"]
    catalog = coach_http.post(
        ROOT + "/catalog", json={"scope": service_case["input_data"]["scope"], "kind": "concept"}
    )
    assert catalog.status_code == 200 and catalog.json()["data"]["limit"] == 30
    response = coach_http.post(
        ROOT + "/requests", json=request(service_case).model_dump(mode="json")
    )
    assert response.status_code == 200
    saved = response.json()["data"]
    assert saved["status"] == "ready" and saved["model_status"] == "not_requested"
    assert not {"claim_epoch", "lease_until", "restore_epoch"} & saved.keys()
    assert coach_http.get(ROOT + "/requests/" + saved["request_key"]).json()["data"] == saved
    assert coach_http.get(ROOT + "/requests/synthetic_unknown_request").status_code == 404


@pytest.mark.parametrize(
    "flag", ["FILEMATE_ENABLE_LEARNING_COACH", "FILEMATE_ENABLE_LEARNING_ORCHESTRATOR"]
)
def test_flags_preserve_reads_cancel_and_safe_undo(coach_http, service_case, monkeypatch, flag):
    from .test_commands import confirm_body
    from .test_plans import ready

    case, view, draft = ready(service_case)
    preview = coach_http.post(ROOT + "/proposals/preview", json=draft.model_dump(mode="json"))
    assert preview.status_code == 200
    model = coach_module("models").CoachPreview.model_validate(preview.json()["data"])
    confirmed = coach_http.post(
        ROOT + "/proposals/confirm", json=confirm_body(draft, model).model_dump(mode="json")
    )
    assert confirmed.status_code == 200
    receipt = confirmed.json()["data"]
    monkeypatch.delenv(flag)
    assert coach_http.get(ROOT + "/capabilities").json()["data"]["enabled"] is False
    assert coach_http.post(ROOT + "/context", json=case["input_data"]).status_code == 503
    assert coach_http.get(ROOT + "/requests/" + view.request_key).status_code == 200
    assert (
        coach_http.post(ROOT + "/requests/" + view.request_key + "/cancel", json={}).status_code
        == 200
    )
    assert coach_http.get(ROOT + "/operations/" + receipt["request_key"]).json()["data"] == receipt
    assert (
        coach_http.post(ROOT + "/day", json={"study_date": "2026-10-31"}).json()["data"]["status"]
        == "confirmed"
    )
    undo = coach_http.post(ROOT + f"/operations/{receipt['operation_id']}/undo-preview", json={})
    assert undo.status_code == 200
    result = coach_http.post(
        ROOT + f"/operations/{receipt['operation_id']}/undo-confirm",
        json={
            "confirmation_token": undo.json()["data"]["confirmation_token"],
            "request_key": "synthetic_http_undo_key",
            "confirmed": True,
        },
    )
    assert result.status_code == 200 and result.json()["data"]["status"] == "undone"


def test_duplicate_running_http_is_202_and_cancel_remains_available(coach_http, service_case):
    body = request(service_case, mode="llm")
    repo = coach_module("repository").CoachRepository(
        service_case["storage"], clock=service_case["clock"]
    )
    repo.claim(body, read_context(service_case))
    response = coach_http.post(ROOT + "/requests", json=body.model_dump(mode="json"))
    assert response.status_code == 202 and response.json()["data"]["status"] == "running"
    response = coach_http.post(ROOT + f"/requests/{body.request_key}/cancel", json={})
    assert response.status_code == 200 and response.json()["data"]["status"] == "cancelled"


def test_only_requests_accepts_ephemeral_model_key():
    from filemate.llm_client.request_credentials import is_model_request

    assert is_model_request("POST", ROOT + "/requests")
    assert not is_model_request("GET", ROOT + "/requests/synthetic_request_key")
    for path in (
        "context",
        "catalog",
        "proposals/confirm",
        "day",
        "operations/example/undo-confirm",
    ):
        assert not is_model_request("POST", ROOT + "/" + path)


def test_coach_api_auth_origin_and_tenant_isolation(account_server, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice, keep_guest_data=False).status_code == 200
        goal = alice.post(
            "/goals/reverse-plan",
            json={
                "title": "合成体验目标",
                "goal_type": "skill",
                "deadline": "2026-12-31",
                "target_score": 80,
            },
        ).json()["data"]["goal_id"]
        from datetime import datetime

        from filemate.study.orchestrator.models import LOCAL_ZONE

        day = datetime.now(LOCAL_ZONE).date().isoformat()
        body = {
            "scope": {"goal_id": goal},
            "selection": {},
            "intent": "budget",
            "question": "今天先做什么",
            "days": [{"study_date": day, "options": {"available_minutes": 20}}],
        }
        assert alice.post(ROOT + "/context", json=body).status_code == 200
        assert bob.post(ROOT + "/context", json=body).status_code == 404
        assert (
            alice.post(
                ROOT + "/context", json=body, headers={"Origin": "https://untrusted.invalid"}
            ).status_code
            == 403
        )
        alice.cookies.set(
            account_server.ACCOUNT_COOKIE_NAME,
            "expired-synthetic",
            domain="testserver.local",
            path="/",
        )
        assert alice.get(ROOT + "/capabilities").status_code == 401


def test_generic_artifact_get_cannot_read_control_or_result(server_module):
    from filemate.study.orchestrator.repository import atomic, put

    server, storage = server_module
    with atomic(storage) as conn:
        for kind in ("request", "result", "runtime", "operation"):
            put(
                conn,
                "synthetic-protected-" + kind,
                "learning_coach_" + kind,
                {"claim_epoch": "synthetic-private-control"},
            )
    with TestClient(server.app) as client:
        for kind in ("request", "result", "runtime", "operation"):
            response = client.get("/knowledge/artifacts/synthetic-protected-" + kind)
            assert response.status_code == 404 and "private-control" not in response.text


def test_key_middleware_rejects_rule_body_and_non_model_routes(server_module, monkeypatch):
    server, _ = server_module
    key = "synthetic-ephemeral-coach-key"
    headers = {
        "X-FileMate-LLM-Key": key,
        "X-FileMate-Action": "model",
        "Origin": server.CORS_ORIGINS[0],
    }
    with TestClient(server.app) as client:
        assert client.post(ROOT + "/context", json={}, headers=headers).status_code == 403
        response = client.post(ROOT + "/requests", json={"mode": "rule"}, headers=headers)
        assert response.status_code == 403 and key not in response.text
        response = client.post(
            ROOT + "/requests",
            content=json.dumps({"mode": "llm", "question": "x" * 65536}),
            headers=headers,
        )
        assert response.status_code == 413 and key not in response.text


def test_openapi_has_all_coach_routes_and_strict_requests(coach_http):
    schema = coach_http.get("/openapi.json").json()
    assert len([p for p in schema["paths"] if p.startswith(ROOT)]) == 12
    assert schema["components"]["schemas"]["CoachRequest"]["additionalProperties"] is False


def test_missing_model_consent_has_a_safe_machine_code(coach_http, service_case):
    body = request(service_case).model_dump(mode="json") | {"mode": "llm"}
    response = coach_http.post(ROOT + "/requests", json=body)
    assert response.status_code == 422
    assert response.json()["data"]["error_code"] == "model_consent_required"


def test_ephemeral_key_reaches_only_the_authorized_worker_configuration(server_module, monkeypatch):
    from datetime import datetime

    from filemate.llm_client import LLMConfig
    from filemate.llm_client.request_credentials import REQUEST_API_KEY
    from filemate.study.orchestrator.models import LOCAL_ZONE

    from .test_requests import CountingRunner

    server, storage = server_module
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    api = coach_module("api")
    original_service = api.CoachService
    runner = CountingRunner()
    key = "synthetic-ephemeral-authorized-key"
    seen = []

    def private_configuration():
        config = LLMConfig.from_env()
        seen.append(config.api_key == key)
        return config

    class ProbeService(original_service):
        def __init__(self, store, **kwargs):
            super().__init__(store, **kwargs, config_factory=private_configuration, runner=runner)

    monkeypatch.setattr(api, "CoachService", ProbeService)
    goal = storage.save_artifact(
        artifact_type="reverse_goal_plan",
        content={"title": "合成临时凭据流程", "goal_type": "custom", "tasks": []},
    )
    payload = {
        "scope": {"goal_id": goal},
        "selection": {},
        "intent": "budget",
        "question": "今天先做什么",
        "days": [
            {
                "study_date": datetime.now(LOCAL_ZONE).date().isoformat(),
                "options": {"available_minutes": 20},
            }
        ],
    }
    headers = {
        "X-FileMate-LLM-Key": key,
        "X-FileMate-Action": "model",
        "Origin": server.CORS_ORIGINS[0],
    }
    with TestClient(server.app) as client:
        context = client.post(ROOT + "/context", json=payload).json()["data"]
        body = {
            "input": payload,
            "expected_context_revision": context["context_revision"],
            "request_key": "synthetic_http_private_key",
            "mode": "llm",
            "allow_external_model": True,
            "consent_digest": context["external_digest"],
        }
        response = client.post(ROOT + "/requests", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["model_status"] == "succeeded"
        assert key not in response.text
    assert seen == [True] and runner.calls == 1
    assert REQUEST_API_KEY.get() == ""
    assert all(
        key not in row[0] and key not in row[1]
        for row in storage._conn().execute("SELECT content,metadata FROM artifacts")
    )


def test_early_auth_origin_and_credential_errors_are_not_cacheable(account_server):
    with TestClient(account_server.app) as client:
        response = client.post(
            ROOT + "/context", json={}, headers={"Origin": "https://untrusted.invalid"}
        )
        assert response.status_code == 403
        assert response.headers.get("cache-control") == "no-store"
        headers = {
            "Origin": account_server.CORS_ORIGINS[0],
            "X-FileMate-LLM-Key": "synthetic-cache-scope-key",
            "X-FileMate-Action": "model",
        }
        response = client.post(ROOT + "/context", json={}, headers=headers)
        assert response.status_code == 403
        assert response.headers.get("cache-control") == "no-store"
        client.cookies.set(
            account_server.ACCOUNT_COOKIE_NAME,
            "expired-synthetic",
            domain="testserver.local",
            path="/",
        )
        response = client.get(ROOT + "/capabilities")
        assert response.status_code == 401
        assert response.headers.get("cache-control") == "no-store"
