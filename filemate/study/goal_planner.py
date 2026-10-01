"""基于真实学习证据反推目标、缺口与下一步任务。"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any


def _gap(
    name: str,
    current: str,
    target: str,
    status: str,
    evidence: str,
) -> dict[str, str]:
    return {
        "name": name,
        "current": current,
        "target": target,
        "status": status,
        "evidence": evidence,
    }


def _task(
    task_id: str,
    title: str,
    reason: str,
    route: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "title": title,
        "reason": reason,
        "route": route,
        "status": "pending",
        "due_date": "",
    }


_ERROR_CAUSE_GUIDANCE = {
    "concept_gap": ("概念缺口", "补全概念后口头解释", "先回到资料确认定义、边界和例子"),
    "memory_gap": ("记忆遗漏", "主动回忆并口头复述", "先遮住答案主动回忆，再用自己的话复述"),
    "reasoning_break": ("推理断点", "分步讲清推理链", "把条件、步骤和结论逐段讲清"),
    "expression_gap": ("表达困难", "重组表达并完成讲解", "按结论、依据、例子重新组织表达"),
    "option_confusion": ("选项混淆", "辨析选项并解释边界", "逐项说明正确条件和干扰项错在哪里"),
    "careless": ("审题疏漏", "口述审题与检查步骤", "复盘关键词、限制条件和最后检查步骤"),
    "unconfirmed": ("待确认", "确认错因并口头解释", "先在错题页确认原因，再按真实问题训练"),
}


def build_reverse_goal_plan(
    *,
    title: str,
    goal_type: str,
    deadline: date,
    target_score: int | None,
    analytics: dict[str, Any],
    source_id: str | None = None,
    source_name: str | None = None,
    previous_tasks: list[dict[str, Any]] | None = None,
    focus_wrong: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """用当前证据生成可解释目标路径，并保留已完成任务。"""
    source_count = int(analytics.get("source_count", 0))
    quiz_attempts = int(analytics.get("quiz_attempt_count", 0))
    pending_wrong = int(analytics.get("pending_wrong_count", 0))
    interview_count = int(analytics.get("assessed_interview_count", analytics.get("interview_count", 0)))
    interview_score = float(analytics.get("average_interview_score") or 0)
    study_days = int(analytics.get("total_study_days", 0))
    study_rate = float(analytics.get("study_completion_rate", 0))
    dimensions = analytics.get("interview_dimensions", {}) or {}

    gaps = [
        _gap(
            "资料基础",
            f"已入库 {source_count} 份" if source_count else "待建立",
            "至少 1 份目标资料",
            "ready" if source_count or source_id else "gap",
            source_name or f"本地知识库共 {source_count} 份资料",
        ),
        _gap(
            "练习证据",
            f"已作答 {quiz_attempts} 次" if quiz_attempts else "待评测",
            "先完成 10 次基线练习",
            "ready" if quiz_attempts >= 10 else "gap",
            f"quiz_attempts={quiz_attempts}，未达到阈值时不推断掌握度",
        ),
        _gap(
            "错题闭环",
            f"待复习 {pending_wrong} 道" if pending_wrong else "当前无待复习错题",
            "到期错题清零",
            "ready" if pending_wrong == 0 else "gap",
            f"wrong_questions 中未掌握记录 {pending_wrong} 条",
        ),
        _gap(
            "计划执行",
            f"完成率 {study_rate:.0f}%" if study_days else "待建立计划",
            "形成连续执行记录",
            "ready" if study_days and study_rate >= 70 else "gap",
            f"已完成 {analytics.get('completed_study_days', 0)}/{study_days} 个学习日",
        ),
    ]

    if goal_type in {"competition", "job", "postgraduate"}:
        desired = target_score or 80
        gaps.append(
            _gap(
                "表达基线",
                f"面试均分 {interview_score:.0f}" if interview_count else "待评测",
                f"目标 {desired} 分",
                "ready" if interview_count and interview_score >= desired else "gap",
                f"来自 {interview_count} 场模拟面试；样本不足时不生成趋势",
            )
        )
        if dimensions:
            weakest_name, weakest_score = min(
                dimensions.items(), key=lambda item: float(item[1])
            )
            gaps.append(
                _gap(
                    "当前短板",
                    f"{weakest_name} {float(weakest_score):.0f} 分",
                    "针对最低维度复练",
                    "gap",
                    "依据全部已保存面试回答的同名维度均值",
                )
            )

    tasks: list[dict[str, Any]] = []
    if not source_count and not source_id:
        tasks.append(_task("import-source", "导入一份目标资料", "目标尚无资料依据，先建立可引用来源。", "/ai-tools"))
    else:
        tasks.append(_task("review-source", "提取目标资料的核心要点", "先确认范围，再进入练习与复盘。", "/ai-tools"))
    if quiz_attempts < 10:
        tasks.append(_task("baseline-quiz", "完成一组基线练习", "用真实作答识别薄弱点，不用主观自评代替。", "/ai-tools"))
    if pending_wrong:
        tasks.append(_task("clear-due-wrong", f"复习 {pending_wrong} 道待处理错题", "优先处理已有失败证据。", "/wrongbook"))
    if source_id and focus_wrong:
        question = focus_wrong.get("question") or {}
        stem = (
            str(question.get("stem") or question.get("question") or "").strip()
            if isinstance(question, dict) else ""
        )
        error_cause = str(focus_wrong.get("error_cause") or "unconfirmed")
        cause_label, task_title, guidance = _ERROR_CAUSE_GUIDANCE.get(
            error_cause, _ERROR_CAUSE_GUIDANCE["unconfirmed"],
        )
        cause_source = str(focus_wrong.get("error_cause_source") or "unconfirmed")
        cause_origin = "你已确认" if cause_source == "user" else "系统低置信度建议"
        knowledge_label = str(
            focus_wrong.get("knowledge_label") or "未标注知识点"
        )
        oral_task = _task(
            "explain-wrong-aloud",
            task_title,
            (
                f"知识点：{knowledge_label}；错因：{cause_label}（{cause_origin}）。{guidance}。"
                + (f"题目：{stem[:60]}" if stem else "")
            ),
            "/interview",
        )
        oral_task["focus_wrong_id"] = str(focus_wrong["wrong_id"])
        oral_task["source_id"] = source_id
        oral_task["knowledge_key"] = focus_wrong.get("knowledge_key")
        oral_task["knowledge_label"] = knowledge_label
        oral_task["error_cause"] = error_cause
        oral_task["error_cause_label"] = cause_label
        oral_task["error_cause_source"] = cause_source
        oral_task["source_evidence"] = focus_wrong.get("source_evidence") or {
            "status": "unavailable",
            "method": "local_bm25",
            "reason": "未找到可靠资料片段。",
        }
        oral_task["evidence_ref"] = {
            "artifact_id": focus_wrong.get("artifact_id"),
            "question_index": focus_wrong.get("question_index"),
            "attempt_id": focus_wrong.get("attempt_id"),
            "attempt_at": focus_wrong.get("attempt_at"),
            "source_revision": focus_wrong.get("source_revision"),
            "question_revision": focus_wrong.get("question_revision"),
            "diagnosis_revision": focus_wrong.get("diagnosis_revision"),
        }
        tasks.append(oral_task)
    if not study_days or study_rate < 70:
        tasks.append(_task("build-study-plan", "建立并执行学习计划", "把能力缺口转成每日可完成行动。", "/study-plan"))
    if goal_type in {"competition", "job", "postgraduate"}:
        scenario = {
            "competition": "竞赛答辩",
            "job": "求职面试",
            "postgraduate": "保研复试",
        }[goal_type]
        tasks.append(_task("baseline-interview", f"完成一次{scenario}", "建立表达与证据充分性的可复盘基线。", "/interview"))
    tasks.append(_task("review-evidence", "复核目标证据并重新规划", "完成任务后重新读取数据，确认缺口是否缩小。", "/goals"))

    completed_tasks = {
        str(item.get("task_id")): item
        for item in (previous_tasks or [])
        if item.get("status") == "completed"
    }
    today = datetime.now().astimezone().date()
    total_days = max(1, (deadline - today).days)
    pending_count = max(1, len(tasks))
    for index, item in enumerate(tasks):
        offset = min(total_days, max(1, math.ceil((index + 1) * total_days / pending_count)))
        item["due_date"] = (today + timedelta(days=offset)).isoformat()
        previous = completed_tasks.get(item["task_id"])
        same_focus = (
            item["task_id"] != "explain-wrong-aloud"
            or previous and previous.get("focus_wrong_id") == item.get("focus_wrong_id")
            and previous.get("evidence_ref") == item.get("evidence_ref")
        )
        if previous and same_focus and item["task_id"] != "clear-due-wrong":
            item["status"] = "completed"

    return {
        "title": title.strip(),
        "goal_type": goal_type,
        "deadline": deadline.isoformat(),
        "target_score": target_score,
        "source_id": source_id,
        "source_name": source_name,
        "evidence_snapshot": {
            "source_count": source_count,
            "quiz_attempt_count": quiz_attempts,
            "pending_wrong_count": pending_wrong,
            "interview_count": interview_count,
            "average_interview_score": interview_score,
            "study_completion_rate": study_rate,
        },
        "gaps": gaps,
        "tasks": tasks,
        "evidence_status": "ready" if quiz_attempts or interview_count else "insufficient",
    }
