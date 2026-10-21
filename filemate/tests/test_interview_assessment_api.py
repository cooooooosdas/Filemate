"""Tenant-scoped API and opt-in assessment integration using synthetic answers."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from filemate.tests.test_interview_assessment_storage import Provider
from filemate.tests.test_interview_coach_api import answer, start
from filemate.tests.test_interview_coach_api import api as coach_api

api = coach_api


def post(client, sid, key="assessment_api01", **kwargs):
    context = client.get(f"/interviews/{sid}/assessments/context").json()["data"]
    return client.post(
        f"/interviews/{sid}/assessments",
        json={"request_key": key, "expected_digest": context["input_digest"], **kwargs},
    )


def test_default_off_and_read_export_survive_flag_disable(api, monkeypatch):
    client, _ = api
    sid = start(client)
    answer(client, sid)
    assert client.get(f"/interviews/{sid}/assessments/context").status_code == 200
    assert post(client, sid).status_code == 503
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "1")
    result = post(client, sid)
    assert result.status_code == 200
    aid = result.json()["data"]["assessment_id"]
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "0")
    for fmt in ["json", "markdown", "pdf"]:
        response = client.get(f"/interviews/{sid}/assessments/{aid}/export", params={"format": fmt})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        if fmt == "pdf":
            assert response.content.startswith(b"%PDF-")
        else:
            assert "待校准" in response.text and "口头表达清晰度" in response.text
    assert client.get("/interview/assessments/history").json()["data"]["total"] == 1
    assert (
        client.post(f"/interviews/{sid}/analysis/clear", json={"confirmed": True}).status_code
        == 200
    )
    assert client.get("/interview/assessments/history").json()["data"]["items"] == []


def test_no_external_without_consent_or_in_local_mode(api, monkeypatch):
    client, _ = api
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "1")
    monkeypatch.setattr("server._coach_llm", lambda: pytest.fail("provider must not be created"))
    sid = start(client)
    answer(client, sid)
    assert post(client, sid, mode="model").status_code == 409
    assert post(client, sid, mode="model", external_consent=True).status_code == 503
    assert post(client, sid).status_code == 200
    assert post(client, sid, "assessment_invalid", mode="local", bogus=True).status_code == 422


def test_slow_model_does_not_block_reads_and_flag_off_prevents_publish(api, monkeypatch):
    client, module = api
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "1")
    monkeypatch.delenv("FILEMATE_INTERVIEW_LOCAL_ONLY")
    sid = start(client)
    answer(client, sid)
    provider = Provider(module._storage.get_interview(sid), block=True)
    monkeypatch.setattr(module, "_coach_llm", lambda: provider)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(post, client, sid, mode="model", external_consent=True)
        assert provider.entered.wait(5)
        assert client.get("/api/health").status_code == 200
        assert client.get(f"/interviews/{sid}/coach").status_code == 200
        monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "0")
        provider.release.set()
        assert future.result(timeout=10).json()["data"]["status"] == "cancelled"


@pytest.mark.parametrize("api", ["anonymous"], indirect=True)
def test_foreign_reports_history_and_comparison_are_hidden(api, monkeypatch):
    client, module = api
    monkeypatch.setenv("FILEMATE_ENABLE_INTERVIEW_ASSESSMENT", "1")
    sid = start(client)
    answer(client, sid)
    aid = post(client, sid).json()["data"]["assessment_id"]
    assert (
        client.get("/interview/assessments/compare", params={"left": aid, "right": aid}).status_code
        == 200
    )
    with TestClient(module.app) as foreign:
        assert foreign.get(f"/interviews/{sid}/assessments/context").status_code == 404
        assert foreign.get(f"/interviews/{sid}/assessments/{aid}").status_code == 404
        assert foreign.get(f"/interviews/{sid}/assessments/{aid}/export").status_code == 404
        assert foreign.get("/interview/assessments/history").json()["data"]["items"] == []
        assert (
            foreign.get(
                "/interview/assessments/compare", params={"left": aid, "right": aid}
            ).status_code
            == 404
        )
