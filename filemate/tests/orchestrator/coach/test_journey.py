"""Four real domain journeys in owned synthetic storage."""

import importlib.util

import pytest


@pytest.mark.parametrize("goal_type", ["exam", "competition", "job", "skill"])
def test_complete_target_journey(tmp_path, monkeypatch, goal_type):
    assert importlib.util.find_spec("scripts.acceptance.learning_coach_journey")
    from scripts.acceptance.learning_coach_journey import run_journey

    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    result = run_journey(tmp_path / goal_type, goal_type)
    assert result["data_type"] == "synthetic"
    assert result["goal_type"] == goal_type
    assert result["rule_status"] == "ready"
    assert result["saved_plan_count"] == 1
    assert result["replay_created_plans"] == 0
    assert result["original_completion_recorded"] is True
    assert result["undo_after_progress_rejected"] is True
    assert result["history_damage"] == 0
    assert result["learning_improvement"] is None
    assert (tmp_path / goal_type / "control/resource-governance.db").is_file()
    assert set(result["conditions"]) == {"rule", "model_explanation", "manual_edit"}
    for name, metrics in result["conditions"].items():
        assert metrics["actual_edit_count"] == int(name == "manual_edit")
        assert metrics["learning_improvement"] is None
        assert all(
            value == 0
            for field, value in metrics.items()
            if field not in {"actual_edit_count", "learning_improvement"}
        )
