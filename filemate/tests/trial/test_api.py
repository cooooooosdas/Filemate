# ruff: noqa: F811
"""Trial HTTP respects strict JSON, tenant isolation and historical management."""

import importlib
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401

from .test_records import feedback

ROOT = "/api/trial"


@pytest.fixture
def client(world, monkeypatch):
    module = importlib.import_module("filemate.study.trial.api")
    monkeypatch.setattr(module, "utc_now", lambda: world["now"][0])
    app = FastAPI()
    app.include_router(module.create_router(lambda: world["store"]))
    with TestClient(app) as client:
        yield client


def test_strict_json_and_bounded_queries(client):
    assert client.post(ROOT + "/feedback", content=b"x" * 262145).status_code == 413
    assert (
        client.post(ROOT + "/feedback", content='{"confirmed":true,"confirmed":false}').status_code
        == 422
    )
    body = feedback().model_dump()
    assert client.post(ROOT + "/feedback", json=body | {"confirmed": 1}).status_code == 422
    for suffix in (
        "?workspace_id=other",
        "?kind=feedback&kind=reflection",
        "?limit=51",
        "?offset=10001",
    ):
        assert client.get(ROOT + "/records" + suffix).status_code == 422
    assert client.get(ROOT + "/capabilities?kind=feedback").status_code == 422
    response = client.get(ROOT + "/records?kind=feedback&limit=10&offset=0")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_off_switch_keeps_history_and_deletion_available(client, monkeypatch):
    saved = client.post(ROOT + "/feedback", json=feedback().model_dump()).json()["data"]
    monkeypatch.delenv("FILEMATE_ENABLE_TRIAL_WORKSPACE")
    assert client.get(ROOT + "/capabilities").json()["data"]["enabled"] is False
    assert (
        client.post(
            ROOT + "/feedback", json=feedback("feedback_disabled_0001").model_dump()
        ).status_code
        == 503
    )
    assert client.get(ROOT + "/records").json()["data"]["total"] == 1
    preview = client.post(
        ROOT + "/records/" + saved["record_id"] + "/delete-preview", json={}
    ).json()["data"]
    deleted = client.post(
        ROOT + "/records/" + saved["record_id"] + "/delete-confirm",
        json={
            "request_key": "delete_api_feedback_0001",
            "confirmed": True,
            "confirmation_token": preview["confirmation_token"],
        },
    )
    assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] is True
    recovered = client.get(ROOT + "/requests/" + feedback().request_key)
    assert recovered.json()["data"]["status"] == "deleted"


def test_database_failure_is_private_and_retryable(client, world, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("private-synthetic-db-path")

    monkeypatch.setattr(world["store"], "read_snapshot", broken)
    result = client.get(ROOT + "/records")
    assert result.status_code == 503
    assert "private-synthetic-db-path" not in result.text


def test_two_accounts_cannot_read_each_others_trial_records(account_server, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_TRIAL_WORKSPACE", "1")
    with TestClient(account_server.app) as first, TestClient(account_server.app) as second:
        register(first, "trial-first@example.invalid")
        register(second, "trial-second@example.invalid")
        result = first.post(ROOT + "/feedback", json=feedback().model_dump())
        assert result.status_code == 200, result.text
        identifier = result.json()["data"]["record_id"]
        assert second.get(ROOT + "/records/" + identifier).status_code == 404
        assert second.get(ROOT + "/requests/" + feedback().request_key).status_code == 404
        assert second.get(ROOT + "/records").json()["data"]["total"] == 0
