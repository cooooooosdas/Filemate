# ruff: noqa: F811
"""New goal types round-trip through the existing authenticated routes."""

from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server, register  # noqa: F401


def test_skill_goal_round_trip_and_cross_account_isolation(account_server, monkeypatch):
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as guest:
        assert register(alice, keep_guest_data=False).status_code == 200
        response = alice.post(
            "/goals/reverse-plan",
            json={"title": "四周C++专题训练", "goal_type": "skill", "deadline": "2026-12-31"},
        )
        assert response.status_code == 200
        identifier = response.json()["data"]["goal_id"]
        options = alice.post("/api/learning/orchestrator/goal-options", json={}).json()["data"][
            "items"
        ]
        assert any(
            i["goal_id"] == identifier and i["goal_type"] == "skill" and i["valid"] for i in options
        )
        assert (
            guest.post(
                "/api/learning/orchestrator/snapshot", json={"goal_id": identifier}
            ).status_code
            == 404
        )
