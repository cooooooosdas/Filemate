# ruff: noqa: F811
"""Real HTTP contracts with synthetic identities, documents and credentials."""

import pytest
from fastapi.testclient import TestClient

from filemate.llm_client.request_credentials import REQUEST_API_KEY, is_model_request
from filemate.tests.test_accounts import register
from filemate.tests.test_graph_api import _upload, graph_server  # noqa: F401

ROOT = "/api/knowledge-graph/courses"


@pytest.fixture
def api_server(graph_server, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_COURSE_GRAPH", "1")
    return graph_server


def setup(client, mode="local"):
    response = client.post(ROOT, json={"name": "数据结构", "request_key": "create_course_0001"})
    assert response.status_code == 200, response.text
    cid = response.json()["data"]["course_id"]
    sid = _upload(client)
    assert client.post(f"{ROOT}/{cid}/sources", json={"source_ids": [sid], "expected_revision": 0}).status_code == 200
    draft = client.post(f"{ROOT}/{cid}/drafts", json={"source_ids": [sid], "mode": mode, "request_key": "create_draft_0001"})
    assert draft.status_code == 200, draft.text
    did = draft.json()["data"]["draft_id"]
    return cid, sid, did, f"{ROOT}/{cid}/drafts/{did}/sources/{sid}/extract"


@pytest.mark.parametrize("account", [False, True])
def test_anonymous_and_account_course_isolation(api_server, account):
    with TestClient(api_server.app) as alice, TestClient(api_server.app) as bob:
        if account:
            assert register(alice).status_code == 200
            assert register(bob, email="other@example.invalid").status_code == 200
        cid, sid, did, route = setup(alice)
        assert bob.get(f"{ROOT}/{cid}").status_code == 404
        assert bob.get(f"{ROOT}/{cid}/drafts/{did}").status_code == 404
        assert bob.get(f"{ROOT}/{cid}/concepts/unknown").status_code == 404
        assert bob.post(route, json={"mode": "local", "request_key": "extract_source_001"}).status_code == 404
        assert bob.post(f"{ROOT}/{cid}/sources", json={"source_ids": [sid], "expected_revision": 1}).status_code == 404
        assert bob.get(ROOT).json()["data"]["total"] == 0


def test_model_consent_and_browser_key_context(api_server, monkeypatch):
    from filemate.course_graph.extraction import CourseGraphProvider, extract_local_course

    seen = []
    def extract(self, text):
        seen.append(REQUEST_API_KEY.get())
        return extract_local_course(text)
    monkeypatch.setattr(CourseGraphProvider, "extract", extract)
    with TestClient(api_server.app) as client:
        _, _, _, route = setup(client, "llm")
        body = {"mode": "llm", "request_key": "extract_source_001"}
        assert client.post(route, json=body).status_code == 422
        headers = {"Origin": api_server.CORS_ORIGINS[0], "X-FileMate-Action": "model", "X-FileMate-LLM-Key": "sk-synthetic-only"}
        result = client.post(route, json=body | {"allow_external_model": True}, headers=headers)
        assert result.status_code == 200, result.text
        assert seen == ["sk-synthetic-only"]
        assert REQUEST_API_KEY.get() == ""
        assert "sk-synthetic-only" not in result.text


def test_non_model_routes_and_similar_paths_never_receive_key(api_server):
    with TestClient(api_server.app) as client:
        cid, _, did, route = setup(client)
        headers = {"Origin": api_server.CORS_ORIGINS[0], "X-FileMate-Action": "model", "X-FileMate-LLM-Key": "sk-synthetic-only"}
        for method, path in [("GET", route), ("POST", route + "/oops"), ("POST", f"{ROOT}/{cid}/drafts/{did}/confirm"),
                             ("POST", f"{ROOT}/{cid}/merges/confirm"), ("POST", ROOT)]:
            assert is_model_request(method, path) is False
            assert client.request(method, path, headers=headers).status_code == 403
        assert client.post(route, headers=headers, json={"mode": "local", "request_key": "extract_source_001"}).status_code == 403


def test_switch_off_preserves_legacy_graph(api_server, monkeypatch):
    with TestClient(api_server.app) as client:
        setup(client)
        monkeypatch.setenv("FILEMATE_ENABLE_COURSE_GRAPH", "0")
        assert client.get(ROOT).status_code == 503
        assert client.get("/api/knowledge-graph").status_code == 200
        monkeypatch.setenv("FILEMATE_ENABLE_COURSE_GRAPH", "1")
        assert client.get(ROOT).json()["data"]["total"] == 1


def test_http_retry_and_parameter_boundaries(api_server):
    with TestClient(api_server.app) as client:
        cid, _, did, route = setup(client)
        body = {"name": "数据结构", "request_key": "create_course_0001"}
        assert client.post(ROOT, json=body).json()["data"]["course_id"] == cid
        assert client.post(ROOT, json=body | {"name": "另一门"}).status_code == 409
        assert client.post(ROOT, json=body | {"extra": True}).status_code == 422
        assert client.post(f"{ROOT}/{cid}/drafts", json={"source_ids": [str(i) for i in range(11)], "mode": "local", "request_key": "create_draft_0002"}).status_code == 422
        assert client.post(f"{ROOT}/{cid}/drafts/{did}/decisions", json={"expected_digest": "x" * 64, "decisions": [{"item_id": "x", "verdict": "revise", "relation": "invented"}]}).status_code == 422
        first = client.post(route, json={"mode": "local", "request_key": "extract_source_001"})
        assert first.status_code == 200
        assert client.post(route, json={"mode": "local", "request_key": "extract_source_001"}).json() == first.json()


def test_provider_error_redacts_and_preserves_graph(api_server, monkeypatch):
    from filemate.course_graph.extraction import CourseGraphProvider

    def fail(self, text):
        raise RuntimeError("sk-synthetic-only " + text)
    monkeypatch.setattr(CourseGraphProvider, "extract", fail)
    with TestClient(api_server.app) as client:
        cid, _, did, route = setup(client, "llm")
        response = client.post(route, json={"mode": "llm", "allow_external_model": True, "request_key": "extract_source_001"})
        assert response.status_code == 502
        assert "sk-synthetic-only" not in response.text and "数据结构包含树" not in response.text
        saved = client.get(f"{ROOT}/{cid}/drafts/{did}").json()["data"]
        assert saved["sources"][0]["status"] == "failed"
        assert saved["sources"][0]["error_code"] == "extraction_failed"
        assert client.get(f"{ROOT}/{cid}/graph").json()["data"]["nodes"] == []
