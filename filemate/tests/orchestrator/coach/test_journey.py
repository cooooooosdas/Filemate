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
    executions = {item["kind"]: item for item in result["domain_execution"]}
    assert executions["wrongbook"]["persisted"] is True
    if goal_type in {"competition", "job"}:
        interview = executions["interview"]
        assert interview["persisted"] is True
        assert interview["new_attempt_id"] != interview["original_attempt_id"]
        assert interview["original_answer_preserved"] is True
        assert interview["request_replay_created_attempts"] == 0
    if goal_type in {"job", "skill"}:
        coding = executions["programming"]
        assert coding["persisted"] is True
        assert coding["new_submission_id"] != coding["original_submission_id"]
        assert coding["original_submission_preserved"] is True
        assert coding["request_replay_created_submissions"] == 0
        assert coding["execution_attempted"] is True
        assert coding["synthetic_judge_result"] is False
        assert coding["status"] in {"completed", "dependency_unavailable"}
        if coding["status"] == "completed":
            assert coding["verdict"] == "AC"
            assert coding["passed"] == coding["total"] > 0
        else:
            assert coding["verdict"] == "SYSTEM_ERROR"
            assert "programming_sandbox_unavailable" in result["dependencies"]
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


def test_unavailable_judge_is_reported_without_fabricated_compiler_success(tmp_path, monkeypatch):
    from filemate.programming.judge import WindowsCppJudge
    from filemate.programming.linux_judge import LinuxCppJudge
    from filemate.programming.windows_sandbox import SandboxUnavailable
    from scripts.acceptance.learning_coach_journey import run_journey

    def unavailable(*args, **kwargs):
        raise SandboxUnavailable("owned acceptance fault injection")

    monkeypatch.setattr(WindowsCppJudge, "judge", unavailable)
    monkeypatch.setattr(LinuxCppJudge, "judge", unavailable)
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_ORCHESTRATOR", "1")
    monkeypatch.setenv("FILEMATE_ENABLE_LEARNING_COACH", "1")
    result = run_journey(tmp_path / "skill", "skill")
    assert result["status"] == "CONDITIONAL_PASS"
    assert result["compiler_execution"] == "dependency_unavailable"
    assert result["context_compiler_evidence"] == "synthetic_record_only"
    coding = next(item for item in result["domain_execution"] if item["kind"] == "programming")
    assert coding["stored_status"] == "failed"
    assert coding["verdict"] == "SYSTEM_ERROR"
    assert coding["synthetic_judge_result"] is False
    assert coding["original_submission_preserved"] is True
