"""验证画像范围、样本不足、异常排除及原记录回看。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.study.evidence_profile import build_evidence_profile

NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def profile(**changes):
    """使用明确的合成行为夹具，不构造用户研究结果。"""
    return build_evidence_profile(attempts=changes.get("attempts", []),
        wrongs=changes.get("wrongs", []), plans=changes.get("plans", []),
        interviews=changes.get("interviews", []), now=NOW)


def attempt(index=0, **changes):
    return {"attempt_id": f"attempt-{index}", "artifact_id": "artifact", "source_id": "source",
            "question_index": 0, "is_correct": 1, "score": 1,
            "created_at": NOW.isoformat(), **changes}


def test_empty_profile_has_no_invented_scores_or_update_times():
    result = profile()
    for metric in result["metrics"].values():
        assert metric["value"] is None
        assert metric["sample_count"] == 0
        assert metric["updated_at"] is None
        assert metric["status"] == "pending_assessment"
        assert metric["records"] == []


def test_few_observations_are_pending_with_units_and_real_record_link():
    metric = profile(attempts=[attempt()])["metrics"]["quiz"]
    assert metric["sample_count"] == 1
    assert metric["value"] == 100
    assert metric["status"] == "insufficient_samples"
    assert metric["sample_unit"] == "次作答"
    assert metric["records"][0]["href"] == "/ai-tools?artifact=artifact&source=source"
    assert "user_answer" not in json.dumps(metric)


def test_error_updates_all_saved_counts_without_rewriting_older_evidence():
    rows = [attempt(index) for index in range(6)]
    original = json.dumps(rows, sort_keys=True)
    before = profile(attempts=rows)
    after = profile(attempts=[*rows, attempt(7, is_correct=0, score=0)])
    assert before["metrics"]["quiz"]["value"] == 100
    assert after["metrics"]["quiz"]["value"] == 85.71
    assert after["metrics"]["quiz"]["sample_count"] == 7
    assert len(after["metrics"]["quiz"]["records"]) == 5
    assert json.dumps(rows, sort_keys=True) == original
    assert profile(attempts=list(reversed(rows))) == before


@pytest.mark.parametrize("changes", [{"score": float("nan")}, {"score": 2},
    {"is_correct": 0.5}, {"created_at": "broken"},
    {"created_at": (NOW + timedelta(seconds=1)).isoformat()}, {"score": True}])
def test_invalid_attempts_are_excluded_without_fabricating_dates(changes):
    metric = profile(attempts=[attempt(**changes)])["metrics"]["quiz"]
    assert metric["sample_count"] == 0
    assert metric["excluded_count"] == 1
    assert metric["value"] is None


def test_old_naive_sqlite_utc_records_are_historical_only():
    old = NOW - timedelta(days=91)
    metric = profile(attempts=[attempt(created_at=old.replace(tzinfo=None).isoformat())])["metrics"]["quiz"]
    assert metric["status"] == "historical_only"
    assert metric["updated_at"] == old.isoformat()


@pytest.mark.parametrize("completed", [[1, 1], [9], [True], "broken"])
def test_invalid_plan_progress_cannot_raise_completion_above_100(completed):
    row = {"plan_id": "plan", "status": "active", "updated_at": NOW.isoformat(),
           "plan_data": {"daily_plan": [{"day": 1}]}, "completed_days": completed}
    result = profile(plans=[row])
    assert result["metrics"]["plan"]["excluded_count"] == 1
    assert result["total_study_days"] == 0


def test_archived_plan_does_not_inflate_current_progress():
    row = {"plan_id": "plan", "status": "active", "updated_at": NOW.isoformat(),
           "plan_data": {"daily_plan": [{"day": 1}, {"day": 2}]}, "completed_days": [1]}
    result = profile(plans=[row, {**row, "plan_id": "old", "status": "archived"}])
    assert result["metrics"]["plan"]["value"] == 50
    assert result["completed_study_days"] == 1
    assert result["archived_plans_excluded"] == 1


def test_interview_dimension_sample_counts_do_not_mix_fallback_or_bad_values():
    base = {"turn_id": "turn", "scoring_mode": "llm", "created_at": NOW.isoformat(),
            "score": 80, "dimensions": {"内容": 80, "结构": float("inf")}}
    result = profile(interviews=[{"interview_id": "interview", "turns": [base,
        {**base, "turn_id": "local", "scoring_mode": "local_fallback"},
        {**base, "turn_id": "invalid", "score": 999}]}])
    assert result["metrics"]["interview"]["sample_count"] == 1
    assert result["metrics"]["interview"]["excluded_count"] == 1
    assert result["unassessed_interview_turns"] == 1
    assert set(result["dimensions"]) == {"内容"}
    assert result["dimensions"]["内容"]["status"] == "insufficient_samples"


def test_real_storage_source_scope_and_wrong_correction_are_read_only(tmp_path: Path):
    store = SQLiteStorage(tmp_path / "synthetic.db")
    store.init_schema()
    first = store.save_source(original_name="合成一.txt", source_path="/synthetic/1", raw_text="栈")
    second = store.save_source(original_name="合成二.txt", source_path="/synthetic/2", raw_text="进程")
    artifacts = [store.save_artifact(source_id=source, artifact_type="questions", content=[
        {"stem": "工程题", "answer": "正确"}]) for source in [first, second]]
    for artifact in artifacts:
        store.record_quiz_attempt(artifact_id=artifact, question_index=0, user_answer="错误",
                                  is_correct=False, score=0, feedback="工程夹具")
    for _ in range(2):
        store.record_quiz_attempt(artifact_id=artifacts[0], question_index=0, user_answer="正确",
                                  is_correct=True, score=1, feedback="工程夹具")
    before = store._conn().total_changes
    scoped = store.get_learning_analytics(source_id=first)["evidence_profile"]
    assert scoped["metrics"]["quiz"]["sample_count"] == 3
    assert scoped["pending_wrong_count"] == 0
    assert scoped["mastered_wrong_count"] == 1
    assert scoped["scope"] == "source"
    assert store.get_learning_analytics(source_id=second)["evidence_profile"]["pending_wrong_count"] == 1
    assert store._conn().total_changes == before
    store.close()


def test_corrupted_plan_and_interview_records_do_not_break_overview(tmp_path: Path):
    store = SQLiteStorage(tmp_path / "synthetic.db")
    store.init_schema()
    artifact = store.save_artifact(artifact_type="study_plan", content={})
    plan = store.create_study_plan(artifact_id=artifact, source_id=None, plan={"title": "合成计划",
        "exam_date": "2026-10-10", "daily_minutes": 30, "daily_plan": [{"day": 1}]})
    session = store.create_interview(target_role="合成训练", scenario="求职面试", difficulty="标准",
                                     questions=["工程问题"])
    store.save_interview_turn(interview_id=session["interview_id"], question_index=0,
        question="工程问题", answer="工程回答", score=80, dimensions={"内容": 80},
        feedback="工程夹具", scoring_mode="llm")
    connection = store._conn()
    connection.execute("UPDATE study_plans SET plan_data='[]' WHERE plan_id=?", (plan["plan_id"],))
    connection.execute("UPDATE interview_turns SET dimensions='broken'")
    connection.commit()
    result = store.get_learning_analytics()
    assert result["study_completion_rate"] == 0
    assert result["evidence_profile"]["metrics"]["plan"]["excluded_count"] == 1
    assert result["evidence_profile"]["metrics"]["interview"]["excluded_count"] == 1
    assert result["average_interview_score"] is None
    assert connection.execute("SELECT dimensions FROM interview_turns").fetchone()[0] == "broken"
    store.close()
