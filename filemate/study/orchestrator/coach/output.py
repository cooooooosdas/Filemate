"""Finite model suggestions validated against the exact server evidence registry."""

from pydantic import Field, ValidationError

from ..models import TaskView
from .evidence import decode
from .models import (
    CoachAction,
    CoachActionSpec,
    CoachContext,
    CoachExplanation,
    CoachExplanationSpec,
    CoachFact,
    CoachProposal,
    OrchestratorError,
    StrictRequest,
)

REASON_KINDS = {
    "due_review": {"review"},
    "confirmed_cause": {"cause"},
    "confirmed_dependency": {"relation"},
    "selected_feedback": {"interview_feedback"},
    "compiler_result": {"compiler_result"},
    "selected_requirement": {"position_requirement"},
    "goal_step": {"goal", "source", "concept", "plan"},
}
REASON_METHODS = {
    "due_review": {"retry_independently", "compare_cases"},
    "confirmed_cause": {"trace_error", "compare_cases", "reread"},
    "confirmed_dependency": {"reread", "practice"},
    "selected_feedback": {"rehearse"},
    "compiler_result": {"trace_error", "compare_cases", "practice"},
    "selected_requirement": {"reread", "practice", "rehearse"},
    "goal_step": {"reread", "practice", "retry_independently"},
}
ACTION_METHODS = {
    "read_source": {"reread"},
    "review_question": {"retry_independently", "trace_error", "compare_cases"},
    "train_concept": {"reread", "practice", "compare_cases"},
    "rehearse_interview": {"rehearse"},
    "practice_problem": {"practice", "trace_error", "compare_cases"},
}
REASON_TEXT = {
    "due_review": "依据已保存的复习时间安排独立复练。",
    "confirmed_cause": "依据你已确认的错因选择练习方法。",
    "confirmed_dependency": "依据已确认且来源有效的前置关系安排先后。",
    "selected_feedback": "依据你选中的原回答和反馈安排表达练习；反馈仍是模型建议。",
    "compiler_result": "依据已保存的编译器结果安排复练，不推断能力水平。",
    "selected_requirement": "围绕你选定的岗位要求核对资料，不推断岗位胜任程度。",
    "goal_step": "依据当前目标和所选资料安排下一步。",
}
METHOD_TEXT = {
    "reread": "回到原文核对定义和条件。",
    "trace_error": "逐步定位失败步骤并自行验证。",
    "compare_cases": "对照边界情形，说明差异。",
    "retry_independently": "暂时不看答案，独立重做并核对。",
    "rehearse": "按结论、依据、示例组织一次重答。",
    "practice": "做一次小练习，再用实际结果核对。",
}


class CoachActionCandidate(CoachActionSpec):
    pass


class CoachModelOutput(StrictRequest):
    explanations: list[CoachExplanationSpec] = Field(max_length=30)
    task_order: list[str] = Field(max_length=200)
    new_actions: list[CoachActionCandidate] = Field(max_length=7)


def render_explanation(reason_code: str, method_code: str, facts: list[CoachFact]) -> str:
    """Render server-owned wording after checking typed support for the chosen method."""
    if (
        reason_code not in REASON_KINDS
        or method_code not in REASON_METHODS[reason_code]
        or not any(f.kind in REASON_KINDS[reason_code] for f in facts)
    ):
        raise OrchestratorError("enhancement_evidence_mismatch", 422)
    return REASON_TEXT[reason_code] + METHOD_TEXT[method_code]


def supported_task_facts(
    task: TaskView, facts: list[CoachFact], reason_code: str
) -> list[CoachFact]:
    """Use the same exact task-to-evidence binding for preview and validation."""
    origin_ids = {ref.get("id") for ref in task.origin_refs}
    return [
        fact
        for fact in facts
        if fact.kind in REASON_KINDS[reason_code]
        and (
            fact.record_id in origin_ids
            or fact.kind == "goal"
            and fact.record_id == task.goal_id
            or fact.kind == "source"
            and fact.record_id == task.source_id
        )
    ]


def validate_enhancement(
    context: CoachContext, baseline: CoachProposal, raw: object
) -> CoachProposal:
    """Reject an entire invalid enhancement while leaving the baseline untouched."""
    from .rules import action_candidates, assemble_proposal

    try:
        data = CoachModelOutput.model_validate(decode(raw) if isinstance(raw, str) else raw)
    except (ValidationError, TypeError, ValueError):
        raise OrchestratorError("model_output_invalid", 422) from None
    exposed_tasks = {row["task_id"] for row in context.external_payload["tasks"]}
    known_tasks = {
        task.task_id: task
        for task in context.projection.tasks + context.projection.completed
        if task.task_id in exposed_tasks
    }
    if len(data.task_order) != len(set(data.task_order)) or not set(data.task_order) <= set(
        known_tasks
    ):
        raise OrchestratorError("model_task_reference_invalid", 422)
    for day in context.input.days:
        if data.task_order and any(
            p not in data.task_order or data.task_order.index(p) != day.options.item_order.index(p)
            for p in day.options.pinned_ids
        ):
            raise OrchestratorError("pinned_task_conflict")
    exposed = {f["fact_id"] for f in context.external_payload["facts"]}
    facts = {f.fact_id: f for f in context.facts if f.fact_id in exposed}
    registry = action_candidates(context)
    actions, keys = [], set()
    for item in data.new_actions:
        match = next(
            (
                a
                for a in registry
                if a.action == item.action
                and a.target_ref == item.target_ref
                and set(a.fact_ids) == set(item.fact_ids)
            ),
            None,
        )
        if (
            match is None
            or not set(item.fact_ids) <= set(facts)
            or item.method_code not in ACTION_METHODS[item.action]
            or match.action_key in keys
        ):
            raise OrchestratorError("model_action_reference_invalid", 422)
        keys.add(match.action_key)
        actions.append(CoachAction(**item.model_dump(), action_key=match.action_key))
    explanations = []
    for item in data.explanations:
        if (
            not set(item.fact_ids) <= set(facts)
            or item.task_id is not None
            and item.task_id not in known_tasks
        ):
            raise OrchestratorError("model_fact_reference_invalid", 422)
        cited = [facts[key] for key in item.fact_ids]
        if item.task_id:
            task = known_tasks[item.task_id]
            if not supported_task_facts(task, cited, item.reason_code):
                raise OrchestratorError("enhancement_evidence_mismatch", 422)
        explanations.append(
            CoachExplanation(
                **item.model_dump(),
                text=render_explanation(item.reason_code, item.method_code, cited),
            )
        )
    merged = {a.action_key: a for a in baseline.new_actions}
    merged.update({a.action_key: a for a in actions})
    if len(merged) > 7:
        raise OrchestratorError("model_actions_unschedulable", 422)
    enhanced = assemble_proposal(
        context, list(merged.values()), task_order=data.task_order, flexible_dates=False
    )
    if {a.action_key for a in enhanced.new_actions} != set(merged):
        raise OrchestratorError("model_actions_unschedulable", 422)
    enhanced.explanations.extend(explanations)
    enhanced.coverage["enhancement"] = "validated_structure_not_teaching_quality"
    return enhanced
