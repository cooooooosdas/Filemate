"""Evidence-bound local proposals with one shared budget and dependency scheduler."""

from urllib.parse import urlencode

from filemate.execution.data_actions import digest
from filemate.wrongbook.engine import parse_time

from ..models import LOCAL_ZONE, ScheduleOptions, TaskProjection, TaskView
from ..scheduler import build_schedule
from ..task_views import review_key
from .models import (
    CoachAction,
    CoachContext,
    CoachExplanation,
    CoachProposal,
    CoachProposalDay,
    CoachTarget,
    OrchestratorError,
)
from .output import render_explanation
from .prompts import PROMPT_VERSION

RULE_VERSION = "learning-coach-rules-v1"
DEFAULT_MINUTES = {
    "read_source": 15,
    "review_question": 10,
    "train_concept": 10,
    "rehearse_interview": 12,
    "practice_problem": 20,
}
ACTION_LABELS = {
    "read_source": "核对所选资料",
    "review_question": "独立复练原题",
    "train_concept": "练习所选知识点",
    "rehearse_interview": "按反馈重练回答",
    "practice_problem": "重新验证编程题",
}


def action_candidates(context: CoachContext) -> list[CoachAction]:
    """Map only typed selected facts to real targets and canonical action identities."""
    result = {}
    causes = {f.record_id: f for f in context.facts if f.kind == "cause"}
    requirements = [f for f in context.facts if f.kind == "position_requirement"]
    compiler = {}
    for fact in context.facts:
        if fact.kind == "compiler_result":
            key = fact.data.problem_id, fact.data.problem_version
            previous = compiler.get(key)
            if previous is None or (fact.observed_at or "", fact.record_id) > (
                previous.observed_at or "",
                previous.record_id,
            ):
                compiler[key] = fact
    for fact in context.facts:
        common = {"id": fact.record_id, "revision": fact.revision}
        method, supporting = "practice", [fact.fact_id]
        cycle = None
        if fact.kind == "source":
            action, target, method = "read_source", CoachTarget(kind="source", **common), "reread"
            supporting += [r.fact_id for r in requirements[:5]]
        elif fact.kind == "review":
            if fact.data.schedule_status != "active" or not parse_time(fact.data.next_review_at):
                continue
            action, method = "review_question", "retry_independently"
            target = CoachTarget(
                kind="question",
                artifact_id=fact.data.artifact_id,
                question_index=fact.data.question_index,
                **common,
            )
            cycle = fact.data.next_review_at
            if fact.record_id in causes:
                method = "trace_error"
                supporting.append(causes[fact.record_id].fact_id)
        elif fact.kind == "concept":
            action = "train_concept"
            target = CoachTarget(kind="concept", course_id=fact.data.course_id, **common)
            relations = [
                r
                for r in context.facts
                if r.kind == "relation"
                and (
                    r.data.relation_type == "prerequisite"
                    and r.data.to_id == fact.record_id
                    or r.data.relation_type == "depends_on"
                    and r.data.from_id == fact.record_id
                )
            ]
            supporting += [r.fact_id for r in relations[:1]]
        elif fact.kind == "interview_feedback":
            action, method = "rehearse_interview", "rehearse"
            target = CoachTarget(
                kind="interview",
                id=fact.data.interview_id,
                revision=fact.revision,
                attempt_id=fact.data.attempt_id,
            )
            cycle = fact.data.attempt_id
        elif fact.kind == "compiler_result":
            if compiler[(fact.data.problem_id, fact.data.problem_version)] is not fact:
                continue
            action = "practice_problem"
            method = "trace_error" if fact.data.verdict != "AC" else "practice"
            target = CoachTarget(
                kind="problem",
                id=fact.data.problem_id,
                revision=fact.revision,
                problem_version=fact.data.problem_version,
            )
            cycle = fact.record_id
        else:
            continue
        identity = {
            "goal_id": context.input.scope.goal_id,
            "course_id": context.input.scope.course_id,
            "action": action,
            "target": target.id,
            "attempt_id": target.attempt_id,
            "problem_version": target.problem_version,
            "cycle": cycle,
        }
        key = (
            review_key(target.id, cycle)
            if action == "review_question"
            else "coach-action-" + digest(identity)
        )
        if key in result:
            current = result[key]
            current.fact_ids = sorted(set(current.fact_ids + supporting))[:8]
            continue
        result[key] = CoachAction(
            action_key=key,
            action=action,
            target_ref=target,
            method_code=method,
            study_date=context.input.days[0].study_date,
            minutes=DEFAULT_MINUTES[action],
            fact_ids=supporting,
        )
    # Stable finite priorities; they are action categories, not learner ability estimates.
    rank = {
        "review_question": 0,
        "train_concept": 1,
        "practice_problem": 2,
        "rehearse_interview": 3,
        "read_source": 4,
    }
    return sorted(result.values(), key=lambda a: (rank[a.action], a.action_key))


def _existing(context: CoachContext, action: CoachAction) -> TaskView | None:
    for task in context.projection.tasks + context.projection.completed:
        if task.action_key == action.action_key:
            return task
        if (
            action.action == "read_source"
            and task.source_id == action.target_ref.id
            and any(
                ref.get("kind") == "goal" and ref.get("template_id") == "review-source"
                for ref in task.origin_refs
            )
        ):
            return task
    return None


def _route(action: CoachAction) -> str:
    target = action.target_ref
    root, query = {
        "read_source": ("/ai-tools", {"source": target.id}),
        "review_question": ("/wrongbook", {"wrong_id": target.id}),
        "train_concept": ("/knowledge-graph", {"course": target.course_id, "node": target.id}),
        "rehearse_interview": ("/interview", {"interview": target.id}),
        "practice_problem": ("/programming", {"problem": target.id}),
    }[action.action]
    return root + "?" + urlencode(query)


def _view(context: CoachContext, action: CoachAction) -> TaskView:
    ref = {"kind": "coach_action", "id": action.action_key}
    return TaskView(
        task_id=action.action_key,
        kind="coach",
        title=ACTION_LABELS[action.action],
        goal_id=context.input.scope.goal_id,
        course_id=context.input.scope.course_id,
        source_id=action.target_ref.id if action.action == "read_source" else None,
        estimated_minutes=action.minutes,
        estimate_source="rule_default",
        evidence_refs=[{"kind": "coach_fact", "id": key} for key in action.fact_ids],
        origin_refs=[ref],
        action_key=action.action_key,
        reason="基于所选记录的方法建议",
        route=_route(action),
    )


def _reason(context: CoachContext, action: CoachAction) -> str:
    kinds = {f.kind for f in context.facts if f.fact_id in action.fact_ids}
    if action.action == "review_question":
        return "confirmed_cause" if "cause" in kinds else "due_review"
    if action.action == "train_concept" and "relation" in kinds:
        return "confirmed_dependency"
    return {
        "read_source": "selected_requirement" if "position_requirement" in kinds else "goal_step",
        "train_concept": "goal_step",
        "rehearse_interview": "selected_feedback",
        "practice_problem": "compiler_result",
    }[action.action]


def assemble_proposal(
    context: CoachContext,
    candidates: list[CoachAction],
    *,
    task_order: list[str] | None = None,
    flexible_dates: bool = True,
) -> CoachProposal:
    """Use the existing scheduler for all original and proposed actions together."""
    allowed_days = {day.study_date for day in context.input.days}
    if any(action.study_date not in allowed_days for action in candidates):
        raise OrchestratorError("target_day_outside_window", 422)
    keys = [a.action_key for a in candidates]
    if len(keys) != len(set(keys)):
        raise OrchestratorError("duplicate_action", 422)
    facts = {f.fact_id: f for f in context.facts}
    selected, used, new_actions, days, explanations = set(), set(), [], [], []
    goal_fact = next(f for f in context.facts if f.kind == "goal")
    all_originals = context.projection.tasks + context.projection.completed
    known = {t.task_id for t in all_originals} | set(keys)
    for day in context.input.days:
        specified = set(
            day.options.item_order + day.options.pinned_ids + day.options.excluded_ids
        ) | set(day.options.minute_overrides)
        if not specified <= known:
            raise OrchestratorError("task_reference_changed", 422)
        if set(day.options.pinned_ids) & selected:
            raise OrchestratorError("pinned_task_conflict")
        pending = [
            t.model_copy(deep=True) for t in context.projection.tasks if t.task_id not in selected
        ]
        completed = [t.model_copy(deep=True) for t in context.projection.completed]
        # Earlier scheduled prerequisites are planned, not completed learning evidence.
        prior = [
            t.model_copy(update={"status": "completed"})
            for t in all_originals
            if t.task_id in selected
        ]
        extra = []
        for action in candidates:
            if action.action_key in used or _existing(context, action) is not None:
                continue
            if not flexible_dates and action.study_date != day.study_date:
                continue
            if len(new_actions) + len(extra) >= 7:
                break
            chosen = action.model_copy(update={"study_date": day.study_date})
            task = _view(context, chosen)
            if action.action == "review_question":
                review = next(
                    (
                        f
                        for f in context.facts
                        if f.kind == "review" and f.record_id == action.target_ref.id
                    ),
                    None,
                )
                if (
                    review
                    and parse_time(review.data.next_review_at)
                    .astimezone(LOCAL_ZONE)
                    .date()
                    .isoformat()
                    > day.study_date
                ):
                    task.eligibility = "not_due"
                if review:
                    task.due_date = review.data.next_review_at
            extra.append((chosen, task))
        tasks = (pending + [t for _, t in extra])[:200]
        concept_tasks = {
            a.target_ref.id: a.action_key
            for a, t in extra
            if a.action == "train_concept" and t in tasks
        }
        for fact in context.facts:
            if fact.kind != "relation" or fact.data.relation_type not in {
                "prerequisite",
                "depends_on",
            }:
                continue
            parent, child = fact.data.from_id, fact.data.to_id
            if fact.data.relation_type == "depends_on":
                parent, child = child, parent
            if child in concept_tasks:
                task = next(t for t in tasks if t.task_id == concept_tasks[child])
                if parent in concept_tasks:
                    task.dependency_ids = sorted(set(task.dependency_ids) | {concept_tasks[parent]})
                elif not any(
                    a.target_ref.id == parent for a in new_actions if a.action == "train_concept"
                ):
                    task.eligibility = "prerequisite_unavailable"
        for task in tasks:
            if (
                day.study_date > context.snapshot.study_date
                and task.kind == "review"
                and task.eligibility == "not_due"
                and task.due_date
            ):
                due = parse_time(task.due_date)
                if due and due.astimezone(LOCAL_ZONE).date().isoformat() <= day.study_date:
                    task.eligibility = "eligible"
                    task.reason = "计划在到期日或之后复练；当前尚未到期，不代表未来已完成。"
        available_ids = {t.task_id for t in tasks + completed + prior}
        order = task_order or day.options.item_order
        options = ScheduleOptions(
            available_minutes=day.options.available_minutes,
            item_order=[key for key in order if key in available_ids and key not in selected],
            pinned_ids=day.options.pinned_ids,
            excluded_ids=[key for key in day.options.excluded_ids if key in available_ids],
            minute_overrides={
                k: v for k, v in day.options.minute_overrides.items() if k in available_ids
            },
        )
        projected = TaskProjection(
            tasks=tasks,
            completed=completed + prior,
            unavailable=context.projection.unavailable,
            overlaps=context.projection.overlaps,
            coverage=context.projection.coverage | {"planned_prerequisites": len(prior)},
        )
        snapshot = context.snapshot.model_copy(update={"study_date": day.study_date})
        schedule = build_schedule(snapshot, projected, options)
        chosen_ids = {t.task_id for t in schedule.selected}
        if not set(options.pinned_ids) <= chosen_ids:
            raise OrchestratorError("pinned_task_conflict")
        # Do not present a previously scheduled task as an actual completed record.
        schedule.completed = completed
        for action, task in extra:
            if task.task_id in chosen_ids:
                new_actions.append(action)
                used.add(action.action_key)
                reason = _reason(context, action)
                cited = [facts[key] for key in action.fact_ids]
                explanations.append(
                    CoachExplanation(
                        task_id=task.task_id,
                        fact_ids=action.fact_ids,
                        reason_code=reason,
                        method_code=action.method_code,
                        text=render_explanation(reason, action.method_code, cited),
                    )
                )
        for task in schedule.selected:
            if task.task_id not in used:
                explanations.append(
                    CoachExplanation(
                        task_id=task.task_id,
                        fact_ids=[goal_fact.fact_id],
                        reason_code="goal_step",
                        method_code="practice",
                        text=render_explanation("goal_step", "practice", [goal_fact]),
                    )
                )
        selected.update(chosen_ids)
        days.append(CoachProposalDay(study_date=day.study_date, options=options, schedule=schedule))
    limitations = []
    if context.input.intent == "error_cause" and not any(f.kind == "cause" for f in context.facts):
        limitations.append("confirmed_cause_unavailable")
    if any(day.study_date != context.snapshot.study_date for day in days):
        limitations.append("future_schedule_not_completion")
    if not candidates:
        limitations.append("action_evidence_insufficient")
    return CoachProposal(
        rule_version=RULE_VERSION,
        prompt_version=PROMPT_VERSION,
        facts=context.facts,
        explanations=explanations,
        days=days,
        new_actions=new_actions,
        coverage=context.coverage
        | {"new_action_candidates": len(candidates), "new_actions_scheduled": len(new_actions)},
        overlaps=context.projection.overlaps,
        limitations=limitations,
    )


def build_rule_proposal(context: CoachContext) -> CoachProposal:
    """Produce usable local suggestions without provider setup, I/O or writes."""
    return assemble_proposal(context, action_candidates(context))
