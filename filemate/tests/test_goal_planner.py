"""目标反推规划器回归测试。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from filemate.study.goal_planner import build_reverse_goal_plan


def test_reverse_goal_marks_missing_evidence_as_pending_evaluation() -> None:
    plan = build_reverse_goal_plan(
        title="完成竞赛答辩",
        goal_type="competition",
        deadline=datetime.now().astimezone().date() + timedelta(days=14),
        target_score=85,
        analytics={},
    )

    assert plan["evidence_status"] == "insufficient"
    assert plan["evidence_snapshot"]["average_interview_score"] == 0
    expression = next(item for item in plan["gaps"] if item["name"] == "表达基线")
    assert expression["current"] == "待评测"
    assert expression["status"] == "gap"
    assert "样本不足时不生成趋势" in expression["evidence"]


def test_reverse_goal_uses_weakest_dimension_and_reopens_pending_wrong_task() -> None:
    plan = build_reverse_goal_plan(
        title="Java 实习面试",
        goal_type="job",
        deadline=datetime.now().astimezone().date() + timedelta(days=21),
        target_score=80,
        analytics={
            "source_count": 2,
            "quiz_attempt_count": 12,
            "pending_wrong_count": 3,
            "interview_count": 2,
            "average_interview_score": 74,
            "total_study_days": 5,
            "completed_study_days": 4,
            "study_completion_rate": 80,
            "interview_dimensions": {"内容准确性": 82, "表达流畅性": 61},
        },
        previous_tasks=[{"task_id": "clear-due-wrong", "status": "completed"}],
    )

    weakest = next(item for item in plan["gaps"] if item["name"] == "当前短板")
    assert weakest["current"] == "表达流畅性 61 分"
    wrong_task = next(item for item in plan["tasks"] if item["task_id"] == "clear-due-wrong")
    assert wrong_task["status"] == "pending"
    final_day = datetime.now().astimezone().date() + timedelta(days=21)
    assert all(
        date.fromisoformat(item["due_date"]) <= final_day
        for item in plan["tasks"]
    )
