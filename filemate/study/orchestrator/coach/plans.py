"""Native date-grouped StudyPlans with bounded original-function training actions."""

import json
import sqlite3
from collections import defaultdict
from typing import Any

from .models import CoachAction, CoachContext, CoachDraft, OrchestratorError, ScopeRequest
from .output import ACTION_METHODS
from .rules import ACTION_LABELS, _route, action_candidates


def validate_actions(context: CoachContext, draft: CoachDraft) -> None:
    """Bind human edits to selected real targets rather than arbitrary plan JSON."""
    registry = {action.action_key: action for action in action_candidates(context)}
    for action in draft.new_actions:
        original = registry.get(action.action_key)
        if (
            original is None
            or original.action != action.action
            or original.target_ref != action.target_ref
            or set(original.fact_ids) != set(action.fact_ids)
            or action.method_code not in ACTION_METHODS[action.action]
        ):
            raise OrchestratorError("draft_action_changed", 422)


def training_action(action: CoachAction) -> dict[str, Any]:
    return action.model_dump(mode="json") | {
        "title": ACTION_LABELS[action.action],
        "route": _route(action),
    }


def projected_group(
    content: dict[str, Any], metadata: dict[str, Any], index: int
) -> list[str] | None:
    """Recognize only matching bounded coach date groups for native projection."""
    try:
        namespace = metadata.get("learning_coach")
        if (
            not isinstance(namespace, dict)
            or namespace != content.get("learning_coach")
            or namespace.get("version") != 1
            or not namespace.get("work_id")
            or not namespace.get("operation_id")
        ):
            return None
        scope = ScopeRequest.model_validate(namespace["scope"])
        if scope.goal_id != namespace["goal_id"] or scope.course_id != namespace["course_id"]:
            return None
        days, groups = content["daily_plan"], namespace["day_groups"]
        if not 1 <= len(days) == len(groups) <= 7 or not 0 <= index < len(days):
            return None
        all_keys, selected_keys = [], []
        for n, (day, group) in enumerate(zip(days, groups, strict=True)):
            rows = day["training_actions"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 7:
                return None
            actions = [
                CoachAction.model_validate(
                    {k: row[k] for k in CoachAction.model_fields if k in row}
                )
                for row in rows
            ]
            keys = [action.action_key for action in actions]
            if (
                group != {"day_index": n, "date": day["date"], "action_keys": keys}
                or sum(a.minutes for a in actions) != day["duration_minutes"]
                or not 1 <= day["duration_minutes"] <= 1440
            ):
                return None
            for action, row in zip(actions, rows, strict=True):
                if (
                    action.study_date != day["date"]
                    or action.method_code not in ACTION_METHODS[action.action]
                    or row["route"] != _route(action)
                    or row["title"] != ACTION_LABELS[action.action]
                ):
                    return None
                if action.action == "read_source" and action.target_ref.id not in scope.source_ids:
                    return None
                if (
                    action.action == "train_concept"
                    and action.target_ref.course_id != scope.course_id
                ):
                    return None
            all_keys.extend(keys)
            if n == index:
                selected_keys = keys
        if (
            not 1 <= len(all_keys) <= 7
            or len(set(all_keys)) != len(all_keys)
            or set(all_keys) != set(namespace["action_keys"])
        ):
            return None
        return selected_keys
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def build_short_plan(
    context: CoachContext, draft: CoachDraft, *, plan_id: str, artifact_id: str
) -> dict[str, Any]:
    """Group actions by date without creating another completion or task store."""
    validate_actions(context, draft)
    if not draft.new_actions:
        raise OrchestratorError("new_actions_required", 422)
    by_day = defaultdict(list)
    for action in draft.new_actions:
        by_day[action.study_date].append(action)
    budgets = {day.study_date: day.options.available_minutes for day in draft.days}
    goal = next(f for f in context.facts if f.kind == "goal")
    daily = []
    groups = []
    for date, actions in sorted(by_day.items()):
        minutes = sum(action.minutes for action in actions)
        if minutes > budgets[date]:
            raise OrchestratorError("draft_budget_exceeded", 422)
        index = len(daily)
        daily.append(
            {
                "day": index + 1,
                "date": date,
                "focus": "围绕当前目标完成本日训练",
                "duration_minutes": minutes,
                "tasks": [ACTION_LABELS[a.action] for a in actions],
                "training_actions": [training_action(a) for a in actions],
            }
        )
        groups.append(
            {"day_index": index, "date": date, "action_keys": [a.action_key for a in actions]}
        )
    namespace = {
        "version": 1,
        "goal_id": context.input.scope.goal_id,
        "work_id": draft.work_id,
        "operation_id": None,
        "course_id": context.input.scope.course_id,
        "action_keys": [a.action_key for a in draft.new_actions],
        "day_groups": groups,
        "source_revisions": {f.record_id: f.revision for f in context.facts if f.kind == "source"},
        "scope": context.input.scope.model_dump(mode="json"),
    }
    data = {
        "title": ("学习教练 · " + goal.data.title)[:160],
        "goal": goal.data.title,
        "exam_date": max(by_day),
        "daily_minutes": max(d["duration_minutes"] for d in daily),
        "daily_plan": daily,
        "learning_coach": namespace,
    }
    return {
        "plan_id": plan_id,
        "artifact_id": artifact_id,
        "source_id": context.input.scope.source_ids[0]
        if len(context.input.scope.source_ids) == 1
        else None,
        "source_ids": context.input.scope.source_ids,
        "plan_data": data,
        "metadata": {
            "learning_coach": namespace,
            "dependencies": {
                "goal": context.input.scope.goal_id,
                "sources": context.input.scope.source_ids,
                **context.input.selection.model_dump(mode="json"),
                "attempt_ids": [f.record_id for f in context.facts if f.kind == "attempt"],
            },
        },
    }


def write_short_plan(conn: sqlite3.Connection, plan: dict[str, Any]) -> None:
    """Write into the caller's transaction without committing or altering old plans."""
    if not conn.in_transaction:
        raise RuntimeError("transaction_required")
    data = plan["plan_data"]
    conn.execute(
        """INSERT INTO artifacts(artifact_id,artifact_type,source_id,title,content,metadata)
        VALUES (?,'study_plan',?,?,?,?)""",
        (
            plan["artifact_id"],
            plan["source_id"],
            data["title"],
            json.dumps(data, ensure_ascii=False, allow_nan=False),
            json.dumps(plan["metadata"], ensure_ascii=False, allow_nan=False),
        ),
    )
    conn.execute(
        """INSERT INTO study_plans(plan_id,artifact_id,source_id,title,exam_date,daily_minutes,goal,plan_data,status,completed_days)
        VALUES (?,?,?,?,?,?,?,?,'active','[]')""",
        (
            plan["plan_id"],
            plan["artifact_id"],
            plan["source_id"],
            data["title"],
            data["exam_date"],
            data["daily_minutes"],
            data["goal"],
            json.dumps(data, ensure_ascii=False, allow_nan=False),
        ),
    )
    conn.executemany(
        "INSERT INTO kg_learning_artifact_sources VALUES(?,?)",
        [(plan["artifact_id"], source) for source in plan["source_ids"]],
    )
