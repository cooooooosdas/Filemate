"""One read transaction, minimal external payload, and stable evidence revisions."""

import json
import sqlite3
from datetime import datetime
from typing import Any

from filemate.execution.data_actions import digest
from filemate.execution.storage import SQLiteStorage

from ..models import (
    LOCAL_ZONE,
    Clock,
    EvidenceSnapshot,
    ScopeRequest,
    TaskProjection,
    aware,
    utc_now,
)
from ..snapshot import SnapshotReader
from ..task_views import project_tasks
from .evidence import (
    decode,
    fact,
    selected_concepts,
    selected_interviews,
    selected_position,
    selected_submissions,
    selected_wrongs,
)
from .models import CoachContext, CoachFact, CoachInput, CoachProposal, OrchestratorError
from .output import REASON_KINDS, REASON_METHODS, supported_task_facts
from .prompts import PROMPT_VERSION, full_message_bytes

RUNTIME_ID = "learning-coach-runtime"


def read_restore_epoch(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT artifact_type,content FROM artifacts WHERE artifact_id=?", (RUNTIME_ID,)
    ).fetchone()
    if row is None:
        return "initial"
    if row["artifact_type"] != "learning_coach_runtime":
        raise OrchestratorError("reserved_identity_conflict")
    epoch = decode(row["content"]).get("restore_epoch")
    if not isinstance(epoch, str) or not 1 <= len(epoch) <= 128:
        raise OrchestratorError("stored_coach_runtime_invalid")
    return epoch


def external_payload(
    input: CoachInput,
    snapshot: EvidenceSnapshot,
    projection: TaskProjection,
    facts: list[CoachFact],
) -> dict[str, Any]:
    from .rules import (
        RuleContext,
        allowed_action_methods,
        build_rule_proposal,
        model_action_candidates,
    )

    planning = RuleContext(input, snapshot, projection, facts)
    candidates = model_action_candidates(planning)
    baseline = build_rule_proposal(planning) if any(f.kind == "goal" for f in facts) else None
    items = [item.model_dump(mode="json") for item in facts]
    tasks = list({task.task_id: task for task in projection.tasks + projection.completed}.values())
    totals = len(items), len(tasks)
    payload = {
        "prompt_version": PROMPT_VERSION,
        "input": input.model_dump(mode="json"),
        "study_date": snapshot.study_date,
        "facts": items,
    }
    while True:
        exposed = {row["fact_id"] for row in items}
        visible_facts = [fact for fact in facts if fact.fact_id in exposed]
        payload["tasks"] = [
            {
                "task_id": task.task_id,
                "title": task.title,
                "estimated_minutes": task.estimated_minutes,
                "status": task.status,
                "eligibility": task.eligibility,
                "allowed_explanations": [
                    {
                        "fact_ids": [fact.fact_id for fact in support[:8]],
                        "reason_code": reason,
                        "method_codes": sorted(REASON_METHODS[reason]),
                    }
                    for reason in REASON_KINDS
                    if (support := supported_task_facts(task, visible_facts, reason))
                ],
            }
            for task in tasks
        ]
        payload["allowed_actions"] = [
            {
                "action": action.action,
                "target_ref": action.target_ref.model_dump(mode="json"),
                "fact_ids": action.fact_ids,
                "method_codes": sorted(allowed_action_methods(planning, action)),
                "default_minutes": action.minutes,
            }
            for action in candidates
            if set(action.fact_ids) <= exposed
        ]
        payload["baseline"] = _external_baseline(baseline, exposed, {t.task_id for t in tasks})
        payload["coverage"] = {
            "omitted_facts": totals[0] - len(items),
            "omitted_tasks": totals[1] - len(tasks),
            "omitted_actions": len(candidates) - len(payload["allowed_actions"]),
            "truncated": (len(items), len(tasks)) != totals,
        }
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if (
            len(encoded) <= 24000
            and len(encoded.encode("utf-8")) <= 54000
            and full_message_bytes(payload) <= 65536
        ):
            return payload
        if tasks:
            tasks.pop()
        elif items:
            items.pop()
        else:
            raise OrchestratorError("coach_input_too_large", 422)


def _external_baseline(
    baseline: CoachProposal | None, exposed_facts: set[str], exposed_tasks: set[str]
) -> dict[str, Any]:
    """Reserve every hidden allocation while exposing only closed action references."""
    if baseline is None:
        return {"new_actions": [], "days": []}
    minutes = {
        task.task_id: task.estimated_minutes
        for day in baseline.days
        for task in day.schedule.selected
    }
    visible = [action for action in baseline.new_actions if set(action.fact_ids) <= exposed_facts]
    return {
        "new_actions": [
            action.model_dump(mode="json", exclude={"action_key"})
            | {"minutes": minutes[action.action_key]}
            for action in visible
        ],
        "days": [
            {
                "study_date": day.study_date,
                "available_minutes": day.options.available_minutes,
                "estimated_minutes": day.schedule.estimated_minutes,
                "reserved_minutes": day.schedule.estimated_minutes
                - sum(
                    minutes[action.action_key]
                    for action in visible
                    if action.study_date == day.study_date
                ),
                "selected_task_ids": [
                    task.task_id for task in day.schedule.selected if task.task_id in exposed_tasks
                ],
            }
            for day in baseline.days
        ],
    }


class CoachContextReader:
    def __init__(self, storage: SQLiteStorage, *, clock: Clock | None = None) -> None:
        self.storage = storage
        self.clock = clock or utc_now

    def read(self, input: CoachInput) -> CoachContext:
        as_of = aware(self.clock())
        with self.storage.read_snapshot() as read:
            return self.read_in_transaction(
                read, input, as_of=as_of, restore_epoch=read_restore_epoch(read._conn())
            )

    def read_in_transaction(
        self,
        read: SQLiteStorage,
        input: CoachInput,
        *,
        as_of: datetime,
        restore_epoch: str,
        historical_read: bool = False,
    ) -> CoachContext:
        input = CoachInput.model_validate(input)
        as_of = aware(as_of)
        today = as_of.astimezone(LOCAL_ZONE).date()
        if not historical_read and any(
            not 0 <= (datetime.fromisoformat(item.study_date).date() - today).days <= 6
            for item in input.days
        ):
            raise OrchestratorError("target_day_outside_window", 422)
        snapshot = SnapshotReader(read).read_in_transaction(read, input.scope, as_of=as_of)
        input = input.model_copy(update={"scope": snapshot.scope})
        reflection_revision = None
        if input.reflection_id:
            reflection = read.get_artifact(input.reflection_id)
            if reflection is None or reflection['artifact_type'] != 'weekly_reflection':
                raise OrchestratorError('reflection_not_found', 404)
            saved_scope = ScopeRequest.model_validate(reflection['content'].get('scope'))
            if saved_scope != snapshot.scope:
                raise OrchestratorError('reflection_outside_scope', 422)
            reflection_revision = digest(reflection['content'])
        goal = snapshot.facts["goal"]
        original = (
            read._conn()
            .execute(
                "SELECT content,updated_at FROM artifacts WHERE artifact_id=?",
                (input.scope.goal_id,),
            )
            .fetchone()
        )
        facts = [
            fact(
                "goal",
                input.scope.goal_id,
                {"content": decode(original["content"]), "updated_at": original["updated_at"]},
                {k: goal.get(k) for k in ("title", "goal_type", "deadline")},
                observed_at=original["updated_at"],
                label="当前目标",
            )
        ]
        for source in snapshot.facts["sources"]:
            facts.append(
                fact(
                    "source",
                    source["source_id"],
                    {"source": source, "revision": read.get_source_revision(source["source_id"])},
                    {"title": source["original_name"]},
                    observed_at=source["updated_at"],
                    label="所选学习资料",
                )
            )
        for plan in snapshot.facts["plans"]:
            row = (
                read._conn()
                .execute("SELECT * FROM study_plans WHERE plan_id=?", (plan["plan_id"],))
                .fetchone()
            )
            completed = decode(row["completed_days"], list)
            completed_count = len(
                {
                    index
                    for index in completed
                    if type(index) is int and 0 <= index < plan["day_total"]
                }
            )
            facts.append(
                fact(
                    "plan",
                    plan["plan_id"],
                    dict(row),
                    {
                        "day_count": plan["day_total"],
                        "completed_day_count": completed_count,
                    },
                    label="原计划执行记录，不代表答题正确",
                )
            )
        facts += selected_wrongs(read, input.scope, input.selection)
        interview_facts, interview_bindings = selected_interviews(
            read, input.scope, input.selection, goal.get("goal_type")
        )
        facts += interview_facts + selected_submissions(read, input.selection)
        facts += selected_position(read, input.selection, goal.get("goal_type"))
        facts += selected_concepts(read, input.scope, input.selection, snapshot)
        projection = project_tasks(snapshot)
        payload = external_payload(input, snapshot, projection, facts)
        revision = digest(
            {
                "snapshot": snapshot.evidence_revision,
                "input": input.model_dump(mode="json"),
                "facts": [f.model_dump(mode="json") for f in facts],
                "interviews": interview_bindings,
                "restore_epoch": restore_epoch,
                "reflection_revision": reflection_revision,
            }
        )
        return CoachContext(
            input=input,
            as_of=as_of,
            context_revision=revision,
            restore_epoch=restore_epoch,
            snapshot=snapshot,
            projection=projection,
            facts=facts,
            external_payload=payload,
            external_digest=digest(payload),
            coverage={
                "snapshot": snapshot.coverage,
                "external": payload["coverage"],
                "interviews_selected": len(input.selection.interview_ids),
                "position_linked": input.selection.position_id is not None,
            },
        )
