# ruff: noqa: F811
"""HTTP workspace reads retain real tenant middleware and strict parameters."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from filemate.llm_client.request_credentials import is_model_request
from filemate.tests.course_graph.test_api import ROOT, api_server, graph_server, setup  # noqa: F401


def paths(cid):
    return [f"{ROOT}/{cid}/workspace", f"{ROOT}/{cid}/canvas", f"{ROOT}/{cid}/concepts-page",
            f"{ROOT}/{cid}/workspace/chapter-path/missing", f"{ROOT}/{cid}/workspace/concepts/missing",
            f"{ROOT}/{cid}/concepts/missing/source-evidence/missing"]


def test_read_routes_tenant_isolation_and_flag_off(api_server, monkeypatch):
    with TestClient(api_server.app) as alice, TestClient(api_server.app) as bob:
        cid, _, _, _ = setup(alice)
        for path in paths(cid):
            assert bob.get(path).status_code == 404
        result = alice.get(paths(cid)[0])
        assert result.status_code == 200 and result.json()["data"]["total_concepts"] == 0
        assert result.headers["cache-control"] == "no-store"
        monkeypatch.setenv("FILEMATE_ENABLE_COURSE_GRAPH", "0")
        for path in paths(cid):
            assert alice.get(path).status_code == 503
        assert alice.get("/api/knowledge-graph").status_code == 200


@pytest.mark.parametrize("suffix", ["workspace", "canvas", "concepts-page", "workspace/concepts/missing"])
def test_strict_filters_and_limits(api_server, suffix):
    with TestClient(api_server.app) as client:
        cid, _, _, _ = setup(client)
        path = f"{ROOT}/{cid}/{suffix}"
        assert client.get(path + "?unexpected=value").status_code == 422
        if suffix == "canvas":
            for qs in ("limit=101", "group_limit=21", "relation=unknown", "relation=related_to&relation=related_to",
                       "hide_relations=true&relation=related_to", "limit=10&limit=20"):
                assert client.get(path + "?" + qs).status_code == 422, qs
            assert client.get(path + "?hide_relations=true").status_code == 200
        elif suffix == "concepts-page":
            assert client.get(path, params={"q": "x" * 161}).status_code == 422
            assert client.get(path + "?limit=201").status_code == 422


def test_read_routes_do_not_accept_model_credentials(api_server):
    with TestClient(api_server.app) as client:
        cid, _, _, _ = setup(client)
        headers = {"Origin": api_server.CORS_ORIGINS[0], "X-FileMate-Action": "model", "X-FileMate-LLM-Key": "sk-synthetic-only"}
        for path in paths(cid):
            assert not is_model_request("GET", path)
            assert client.get(path, headers=headers).status_code == 403


def test_old_b_graph_contract_unchanged(api_server):
    with TestClient(api_server.app) as client:
        cid, _, _, _ = setup(client)
        data = client.get(f"{ROOT}/{cid}/graph").json()["data"]
        assert "total" in data and "group_total" not in data
        assert client.get(f"{ROOT}/{cid}/concepts-page").status_code == 200


def test_storage_failure_returns_redacted_503(api_server, monkeypatch):
    from filemate.course_graph import workspace_query

    with TestClient(api_server.app) as client:
        cid, _, _, _ = setup(client)

        def fail(*args, **kwargs):
            raise sqlite3.OperationalError("private-path-secret")

        monkeypatch.setattr(workspace_query, "get_workspace", fail)
        response = client.get(f"{ROOT}/{cid}/workspace")
        assert response.status_code == 503
        assert "private-path-secret" not in response.text
