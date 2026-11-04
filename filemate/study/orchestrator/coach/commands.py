"""Previewed joint changes reuse native plans and compare every affected day."""

import time
from datetime import date as Date
from typing import Any
from uuid import uuid4

from filemate.execution import data_actions
from filemate.execution.storage import SQLiteStorage
from filemate.task_resources import admit_plan
from filemate.wrongbook.engine import parse_time

from ..models import (
    LOCAL_ZONE,
    Clock,
    DayView,
    OperationReceipt,
    ScheduleOptions,
    ScopeRequest,
    UndoConfirmRequest,
    aware,
    utc_now,
)
from ..repository import DAY_TYPE, atomic, day_id, load, put
from ..snapshot import SnapshotReader
from ..task_views import project_tasks
from .context import CoachContextReader, read_restore_epoch
from .models import (
    CoachConfirm,
    CoachDraft,
    CoachInput,
    CoachPreview,
    CoachReceipt,
    CoachUndoPreview,
    OrchestratorError,
)
from .plans import build_short_plan, validate_actions, write_short_plan
from .repository import REQUEST_TYPE, RESULT_TYPE, result_id
from .rules import assemble_proposal
from .settings import enabled

OP_TYPE = "learning_coach_operation"
CONFIRM_ACTION = "learning_coach_confirm"
UNDO_ACTION = "learning_coach_undo"


def key_title(key: str) -> str:
    return "key:" + data_actions.digest(key)


def draft_only(body: CoachDraft) -> CoachDraft:
    return CoachDraft.model_validate({key: getattr(body, key) for key in CoachDraft.model_fields})


def _receipt(conn, record: dict[str, Any]) -> CoachReceipt:
    receipt = CoachReceipt.model_validate(record["receipt"])
    if (
        receipt.status == "confirmed"
        and conn.execute(
            "SELECT 1 FROM data_action_audit WHERE action=? AND resource_id=? LIMIT 1",
            (UNDO_ACTION, receipt.operation_id),
        ).fetchone()
    ):
        receipt.status = "undone"
    return receipt


def plan_revision(conn, identifier: str | None) -> str | None:
    if identifier is None:
        return None
    row = conn.execute(
        "SELECT p.*,a.content,a.metadata,a.title AS artifact_title FROM study_plans p JOIN artifacts a ON a.artifact_id=p.artifact_id WHERE p.plan_id=?",
        (identifier,),
    ).fetchone()
    return data_actions.digest(dict(row)) if row else None


def execution_revision(conn, refs: dict[str, Any]) -> str:
    """Hash saved execution metadata, never complete learner answers or code."""
    state = {}
    for key, table, column, group in (
        ("sources", "quiz_attempts", "source_id", "purpose,judgement_status"),
        ("interviews", "interview_answer_attempts", "interview_id", "interview_id"),
        ("problems", "coding_submissions", "problem_id", "problem_id,status,active"),
    ):
        identifiers = refs[key]
        slots = ",".join("?" for _ in identifiers) or "NULL"
        rows = conn.execute(
            f"SELECT {group},count(*) AS total,max(rowid) AS latest_row FROM {table} "
            f"WHERE {column} IN ({slots}) GROUP BY {group} ORDER BY {group}",
            identifiers,
        ).fetchall()
        state[key] = [dict(row) for row in rows]
    goal = conn.execute(
        "SELECT content,title,updated_at FROM artifacts WHERE artifact_id=? AND artifact_type=?",
        (refs["scope"]["goal_id"], "reverse_goal_plan"),
    ).fetchone()
    state["goal"] = dict(goal) if goal else None
    return data_actions.digest(state)


class CoachCommands:
    def __init__(self, storage: SQLiteStorage, *, clock: Clock | None = None) -> None:
        self.storage = storage
        self.clock = clock or utc_now

    def _find(self, conn, key: str):
        row = conn.execute(
            "SELECT artifact_id FROM artifacts WHERE artifact_type=? AND title=?",
            (OP_TYPE, key_title(key)),
        ).fetchone()
        return load(conn, row[0], OP_TYPE) if row else None

    def find(self, request_key: str) -> CoachReceipt | None:
        with self.storage.read_snapshot() as read:
            record = self._find(read._conn(), request_key)
            return _receipt(read._conn(), record) if record else None

    @staticmethod
    def _check(conn, action, resource, token, binding):
        try:
            return data_actions.check(conn, action, resource, token, binding)
        except ValueError:
            raise OrchestratorError("preview_expired_or_changed") from None

    def _prepare(self, conn, draft: CoachDraft, *, allocate: bool):
        if not enabled():
            raise OrchestratorError("learning_coach_disabled", 503)
        now = aware(self.clock())
        issued = now.astimezone(LOCAL_ZONE).date().isoformat()
        work = load(conn, draft.work_id, REQUEST_TYPE)
        saved = load(conn, result_id(draft.work_id), RESULT_TYPE)
        if not work or work["status"] != "ready" or not saved:
            raise OrchestratorError("coach_work_not_ready")
        if work["context_revision"] != draft.expected_context_revision:
            raise OrchestratorError("context_changed")
        epoch = read_restore_epoch(conn)
        reader = CoachContextReader(self.storage)
        original = CoachInput.model_validate(saved["input"])
        try:
            current = reader.read_in_transaction(
                self.storage, original, as_of=now, restore_epoch=epoch
            )
        except OrchestratorError:
            raise OrchestratorError("context_changed") from None
        if current.context_revision != work["context_revision"]:
            raise OrchestratorError("context_changed")
        edited = original.model_copy(update={"days": draft.days})
        context = reader.read_in_transaction(self.storage, edited, as_of=now, restore_epoch=epoch)
        validate_actions(context, draft)
        new_keys = {a.action_key for a in draft.new_actions}
        if any(
            new_keys & (set(d.options.minute_overrides) | set(d.options.pinned_ids))
            for d in draft.days
        ):
            raise OrchestratorError("edit_new_action_minutes_directly", 422)
        existing = {t.task_id: t for t in context.projection.tasks + context.projection.completed}
        if any(
            choice.original_task_id not in existing
            or existing[choice.original_task_id].kind != "plan"
            for choice in draft.overlap_choices
        ):
            raise OrchestratorError("overlap_reference_changed", 422)
        effective = draft.model_copy(deep=True)
        for choice in effective.overlap_choices:
            if choice.keep == "original":
                effective.new_actions = []
            else:
                for day in effective.days:
                    if choice.original_task_id in day.options.pinned_ids:
                        raise OrchestratorError("pinned_task_conflict")
                    day.options.excluded_ids = sorted(
                        set(day.options.excluded_ids) | {choice.original_task_id}
                    )
        context = context.model_copy(
            update={"input": context.input.model_copy(update={"days": effective.days})}
        )
        proposal = assemble_proposal(context, effective.new_actions, flexible_dates=False)
        if {a.action_key for a in proposal.new_actions} != {
            a.action_key for a in effective.new_actions
        }:
            raise OrchestratorError("draft_budget_or_dependency_conflict", 422)
        before = {
            day.study_date: load(conn, day_id(day.study_date), DAY_TYPE) for day in draft.days
        }
        revisions = {day: record["revision"] if record else 0 for day, record in before.items()}
        for day in draft.days:
            previous = before[day.study_date]
            old_options = ((previous or {}).get("config") or {}).get("options") or {}
            old_order = old_options.get("item_order") or []
            for pin in old_options.get("pinned_ids") or []:
                if pin in existing and existing[pin].status == "completed":
                    continue
                if (
                    pin not in day.options.pinned_ids
                    or pin not in day.options.item_order
                    or day.options.item_order.index(pin) != old_order.index(pin)
                ):
                    raise OrchestratorError("pinned_task_conflict")
        command_hash = data_actions.digest(draft.model_dump(mode="json"))
        allocation_key = data_actions.digest([command_hash, revisions, epoch, issued])
        allocations = saved.setdefault("allocations", {})
        allocation = allocations.get(allocation_key)
        if allocation is None:
            if not allocate:
                raise OrchestratorError("preview_expired_or_changed")
            if len(allocations) >= 100:
                raise OrchestratorError("preview_limit", 429)
            allocation = {
                "operation_id": "learning-coach-operation-" + uuid4().hex,
                "plan_id": uuid4().hex if effective.new_actions else None,
                "artifact_id": uuid4().hex if effective.new_actions else None,
            }
            allocations[allocation_key] = allocation
            put(conn, result_id(draft.work_id), RESULT_TYPE, saved, replace=True)
        ordered = {
            t.task_id: n
            for n, t in enumerate(t for d in proposal.days for t in d.schedule.selected)
        }
        effective.new_actions.sort(key=lambda a: (a.study_date, ordered[a.action_key]))
        plan = (
            build_short_plan(
                context,
                effective,
                plan_id=allocation["plan_id"],
                artifact_id=allocation["artifact_id"],
            )
            if effective.new_actions
            else None
        )
        if plan:
            plan["metadata"]["learning_coach"]["operation_id"] = allocation["operation_id"]
        binding = data_actions.digest(
            {
                "draft": command_hash,
                "issued": issued,
                "epoch": epoch,
                "context": context.context_revision,
                "days": before,
                "allocation": allocation,
                "plan": plan,
                "proposal": proposal.model_dump(mode="json"),
            }
        )
        return context, proposal, before, revisions, allocation, plan, binding, issued

    def preview(self, draft: CoachDraft) -> CoachPreview:
        draft = CoachDraft.model_validate(draft)
        with atomic(self.storage) as conn:
            pending = conn.execute(
                "SELECT count(*) FROM data_action_previews WHERE action=? AND resource_id=? "
                "AND result IS NULL AND expires_at>=?",
                (CONFIRM_ACTION, draft.work_id, int(time.time())),
            ).fetchone()[0]
            if pending >= 100:
                raise OrchestratorError("preview_limit", 429)
            context, proposal, before, revisions, allocation, plan, binding, issued = self._prepare(
                conn, draft, allocate=True
            )
            token = data_actions.issue(conn, CONFIRM_ACTION, draft.work_id, binding)
            return CoachPreview(
                draft=draft,
                as_of=context.as_of,
                issued_study_date=issued,
                day_revisions=revisions,
                new_plan_id=allocation["plan_id"],
                new_artifact_id=allocation["artifact_id"],
                resolved_actions=[
                    {"action_key": a.action_key, "study_date": a.study_date, "minutes": a.minutes}
                    for a in proposal.new_actions
                ],
                changes={
                    "new_study_plans": int(plan is not None),
                    "daily_schedules": len(before),
                    "preserves_completed": True,
                    "groups_actions_by_date": True,
                    "days": [
                        {
                            "study_date": day.study_date,
                            "selected": [task.model_dump(mode="json") for task in day.schedule.selected],
                            "selected_count": len(day.schedule.selected),
                            "estimated_minutes": day.schedule.estimated_minutes,
                            "deferred_count": day.schedule.deferred_count,
                            "deferred_counts": day.schedule.deferred_counts,
                            "completed_count": len(day.schedule.completed),
                            "preserves_completed": True,
                            "pinned_count": len(day.options.pinned_ids),
                            "replaces_existing_schedule": before[day.study_date] is not None,
                        }
                        for day in proposal.days
                    ],
                    "possible_overlaps": [
                        {
                            "original_task_id": task.task_id,
                            "proposed_action_keys": [a.action_key for a in draft.new_actions],
                            "reason": "composite_content_not_equated",
                        }
                        for day in proposal.days
                        for task in day.schedule.selected
                        if draft.new_actions
                        and task.kind == "plan"
                        and not any(ref.get("kind") == "coach_action" for ref in task.origin_refs)
                    ],
                },
                confirmation_token=token,
            )

    def confirm(self, body: CoachConfirm) -> CoachReceipt:
        body = CoachConfirm.model_validate(body)
        draft = draft_only(body)
        hashed = data_actions.digest(draft.model_dump(mode="json"))
        with atomic(self.storage) as conn:
            old = self._find(conn, body.request_key)
            if old:
                if old["command_digest"] != hashed or old["token_hash"] != data_actions.digest(
                    body.confirmation_token
                ):
                    raise OrchestratorError("request_key_conflict")
                return _receipt(conn, old)
            context, proposal, before, revisions, allocation, plan, binding, issued = self._prepare(
                conn, draft, allocate=False
            )
            if self._check(conn, CONFIRM_ACTION, draft.work_id, body.confirmation_token, binding):
                raise OrchestratorError("token_already_used")
            execution_refs = {
                "scope": context.input.scope.model_dump(mode="json"),
                "sources": context.input.scope.source_ids,
                "interviews": context.input.selection.interview_ids,
                "problems": sorted(
                    {f.data.problem_id for f in context.facts if f.kind == "compiler_result"}
                ),
            }
            executed = execution_revision(conn, execution_refs)
            if plan:
                admit_plan(self.storage.db_path, "study_plan", plan["plan_data"])
                write_short_plan(conn, plan)
            group_ids = (
                {
                    group["date"]: f"plan:{plan['plan_id']}:{group['day_index']}"
                    for group in plan["metadata"]["learning_coach"]["day_groups"]
                }
                if plan
                else {}
            )
            new_keys = {a.action_key for a in draft.new_actions}
            after = {}
            for day in proposal.days:
                selected = []
                for task in day.schedule.selected:
                    identifier = (
                        group_ids[day.study_date] if task.task_id in new_keys else task.task_id
                    )
                    if identifier not in selected:
                        selected.append(identifier)
                options = day.options.model_dump(mode="json")
                options["item_order"] = selected + [
                    k for k in options["item_order"] if k not in new_keys and k not in selected
                ]
                config = {
                    "scope": context.input.scope.model_dump(mode="json"),
                    "options": options,
                    "selected_ids": selected,
                    "rule_version": proposal.rule_version,
                    "evidence_revision": context.snapshot.evidence_revision,
                    "learning_coach": {
                        "work_id": draft.work_id,
                        "operation_id": allocation["operation_id"],
                        "source_revisions": {
                            f.record_id: f.revision for f in context.facts if f.kind == "source"
                        },
                    },
                }
                after[day.study_date] = config
                put(
                    conn,
                    day_id(day.study_date),
                    DAY_TYPE,
                    {
                        "revision": revisions[day.study_date] + 1,
                        "config": config,
                        "last_operation_id": allocation["operation_id"],
                    },
                    replace=True,
                )
            output = CoachReceipt(
                operation_id=allocation["operation_id"],
                request_key=body.request_key,
                status="confirmed",
                study_dates=sorted(revisions),
                day_revisions={d: r + 1 for d, r in revisions.items()},
                plan_id=allocation["plan_id"],
                affected={
                    "new_study_plans": int(plan is not None),
                    "daily_schedules": len(revisions),
                },
            )
            record = {
                "command_digest": hashed,
                "token_hash": data_actions.digest(body.confirmation_token),
                "receipt": output.model_dump(mode="json"),
                "before": before,
                "after": after,
                "restore_epoch": context.restore_epoch,
                "issued_study_date": issued,
                "execution_refs": execution_refs,
                "execution_revision": executed,
                "plan_revision": plan_revision(conn, allocation["plan_id"]),
                "source_revisions": {
                    f.record_id: f.revision for f in context.facts if f.kind == "source"
                },
            }
            put(conn, output.operation_id, OP_TYPE, record, title=key_title(body.request_key))
            data_actions.finish(
                conn,
                CONFIRM_ACTION,
                draft.work_id,
                body.confirmation_token,
                output.model_dump(mode="json"),
            )
            return output

    def _undo_target(self, conn, identifier: str):
        record = load(conn, identifier, OP_TYPE)
        if not record or record.get("undo_of"):
            raise OrchestratorError("operation_not_found", 404)
        if record.get("dependency_erased"):
            raise OrchestratorError("execution_evidence_changed")
        receipt = _receipt(conn, record)
        if receipt.status == "undone":
            raise OrchestratorError("operation_already_undone")
        if record["restore_epoch"] != read_restore_epoch(conn):
            raise OrchestratorError("restore_epoch_changed")
        revisions = {}
        for date, revision in receipt.day_revisions.items():
            saved = load(conn, day_id(date), DAY_TYPE)
            if (
                not saved
                or saved["revision"] != revision
                or saved.get("last_operation_id") != identifier
            ):
                raise OrchestratorError("schedule_changed_since_operation")
            revisions[date] = revision
        if receipt.plan_id:
            if conn.execute(
                "SELECT 1 FROM data_action_audit WHERE action='learning_coach_plan_progress' AND resource_id=? LIMIT 1",
                (receipt.plan_id,),
            ).fetchone():
                raise OrchestratorError("coach_plan_already_started")
            plan = conn.execute(
                "SELECT completed_days,status FROM study_plans WHERE plan_id=?", (receipt.plan_id,)
            ).fetchone()
            if not plan or plan["completed_days"] != "[]" or plan["status"] != "active":
                raise OrchestratorError("coach_plan_already_started")
            if record["plan_revision"] != plan_revision(conn, receipt.plan_id):
                raise OrchestratorError("coach_plan_changed")
        if execution_revision(conn, record["execution_refs"]) != record["execution_revision"]:
            raise OrchestratorError("execution_evidence_changed")
        try:
            snapshot = SnapshotReader(self.storage).read_in_transaction(
                self.storage,
                ScopeRequest.model_validate(record["execution_refs"]["scope"]),
                as_of=aware(self.clock()),
            )
        except OrchestratorError:
            raise OrchestratorError("scope_changed") from None
        sources = {
            source["source_id"]: data_actions.digest(
                {
                    "source": source,
                    "revision": self.storage.get_source_revision(source["source_id"]),
                }
            )
            for source in snapshot.facts["sources"]
        }
        if sources != record["source_revisions"]:
            raise OrchestratorError("source_changed")
        issued = aware(self.clock()).astimezone(LOCAL_ZONE).date().isoformat()
        binding = data_actions.digest(
            [
                identifier,
                revisions,
                record["plan_revision"],
                record["execution_revision"],
                record["restore_epoch"],
                issued,
            ]
        )
        return record, receipt, revisions, binding, issued

    def preview_undo(self, operation_id: str) -> CoachUndoPreview:
        with atomic(self.storage) as conn:
            record, _, revisions, binding, issued = self._undo_target(conn, operation_id)
            token = data_actions.issue(conn, UNDO_ACTION, operation_id, binding)
            return CoachUndoPreview(
                operation_id=operation_id,
                issued_study_date=issued,
                day_revisions=revisions,
                plan_revision=record["plan_revision"],
                confirmation_token=token,
            )

    def confirm_undo(self, operation_id: str, body: UndoConfirmRequest) -> CoachReceipt:
        body = UndoConfirmRequest.model_validate(body)
        hashed = data_actions.digest({"undo_of": operation_id})
        with atomic(self.storage) as conn:
            old = self._find(conn, body.request_key)
            if old:
                if old["command_digest"] != hashed or old["token_hash"] != data_actions.digest(
                    body.confirmation_token
                ):
                    raise OrchestratorError("request_key_conflict")
                return _receipt(conn, old)
            record, original, revisions, binding, issued = self._undo_target(conn, operation_id)
            if self._check(conn, UNDO_ACTION, operation_id, body.confirmation_token, binding):
                raise OrchestratorError("token_already_used")
            if original.plan_id:
                conn.execute(
                    "UPDATE study_plans SET status='archived',updated_at=strftime('%Y-%m-%dT%H:%M:%S','now') WHERE plan_id=?",
                    (original.plan_id,),
                )
            identifier = "learning-coach-operation-" + uuid4().hex
            for date, revision in revisions.items():
                before = dict(record["before"][date] or {})
                before.update(
                    revision=revision + 1,
                    config=(record["before"][date] or {}).get("config"),
                    last_operation_id=identifier,
                )
                put(conn, day_id(date), DAY_TYPE, before, replace=True)
            output = CoachReceipt(
                operation_id=identifier,
                request_key=body.request_key,
                status="undone",
                study_dates=sorted(revisions),
                day_revisions={d: r + 1 for d, r in revisions.items()},
                plan_id=original.plan_id,
                affected={
                    "archived_study_plans": int(original.plan_id is not None),
                    "daily_schedules": len(revisions),
                },
            )
            undo = {
                "undo_of": operation_id,
                "command_digest": hashed,
                "token_hash": data_actions.digest(body.confirmation_token),
                "issued_study_date": issued,
                "receipt": output.model_dump(mode="json"),
            }
            put(conn, identifier, OP_TYPE, undo, title=key_title(body.request_key))
            data_actions.finish(
                conn,
                UNDO_ACTION,
                operation_id,
                body.confirmation_token,
                output.model_dump(mode="json"),
            )
            return output


def native_operation_receipt(
    conn, identifier: str, study_date: str, revision: int
) -> OperationReceipt | None:
    """Adapt a verified multi-day receipt to the existing single-day read contract."""
    record = load(conn, identifier, OP_TYPE)
    if record is None:
        return None
    receipt = _receipt(conn, record)
    if receipt.operation_id != identifier or receipt.day_revisions.get(study_date) != revision:
        return None
    return OperationReceipt(
        operation_id=identifier,
        request_key=receipt.request_key,
        study_date=study_date,
        revision=revision,
        status=receipt.status,
        affected=receipt.affected,
    )


class CoachDayReader:
    def __init__(self, storage: SQLiteStorage, *, clock: Clock | None = None) -> None:
        self.storage = storage
        self.clock = clock or utc_now

    def read(self, study_date: str) -> DayView:
        try:
            if len(study_date) != 10 or Date.fromisoformat(study_date).isoformat() != study_date:
                raise ValueError()
        except (TypeError, ValueError):
            raise OrchestratorError("invalid_study_date", 422) from None
        with self.storage.read_snapshot() as read:
            saved = load(read._conn(), day_id(study_date), DAY_TYPE)
            return self.read_in_transaction(read, study_date, saved)

    def read_in_transaction(
        self, read: SQLiteStorage, study_date: str, saved: dict | None
    ) -> DayView:
        if not saved or not saved.get("config"):
            return DayView(
                study_date=study_date,
                revision=saved["revision"] if saved else 0,
                status="not_confirmed",
            )
        config, conn = saved["config"], read._conn()
        if not config.get("learning_coach"):
            from ..repository import OrchestratorRepository

            return OrchestratorRepository(read, clock=self.clock).today(
                Date.fromisoformat(study_date)
            )
        scope = ScopeRequest.model_validate(config["scope"])
        options = ScheduleOptions.model_validate(config["options"])
        pointer = saved.get("last_operation_id")
        latest = (
            native_operation_receipt(conn, pointer, study_date, saved["revision"])
            if pointer
            else None
        )
        try:
            snapshot = SnapshotReader(read).read_in_transaction(
                read, scope, as_of=aware(self.clock())
            )
        except OrchestratorError:
            return DayView(
                study_date=study_date,
                revision=saved["revision"],
                status="stale",
                scope=scope,
                options=options,
                stale_refs=config["selected_ids"],
                latest_operation=latest,
            )
        projection = project_tasks(snapshot)
        tasks = {task.task_id: task for task in projection.tasks + projection.completed}
        stale = []
        source_revisions = {
            s["source_id"]: data_actions.digest(
                {"source": s, "revision": read.get_source_revision(s["source_id"])}
            )
            for s in snapshot.facts["sources"]
        }
        if source_revisions != config["learning_coach"]["source_revisions"]:
            stale.append("source_changed")
        for identifier in config["selected_ids"]:
            if identifier not in tasks or tasks[identifier].eligibility not in {
                "eligible",
                "not_due",
            }:
                stale.append(identifier)
        for identifier, minutes in options.minute_overrides.items():
            if identifier in tasks:
                tasks[identifier] = tasks[identifier].model_copy(
                    update={"estimated_minutes": minutes, "estimate_source": "user_estimate"}
                )
        for task in tasks.values():
            if (
                task.kind in {"review", "plan"}
                and task.eligibility == "not_due"
                and study_date > snapshot.study_date
            ):
                due = parse_time(task.due_date)
                if due and due.astimezone(LOCAL_ZONE).date().isoformat() <= study_date:
                    task.eligibility = "eligible"
                    task.reason = "计划于到期日或之后复练；未将未来计划计作完成。"
        return DayView(
            study_date=study_date,
            revision=saved["revision"],
            status="stale" if stale else "confirmed",
            scope=scope,
            options=options,
            stale_refs=stale,
            latest_operation=latest,
            selected=[tasks[key] for key in config["selected_ids"] if key in tasks],
            completed=projection.completed,
        )
