"""Read saved weekly arrangements against one current, authorized evidence snapshot."""

from datetime import datetime, timedelta

from pydantic import ValidationError

from filemate.execution.data_actions import digest
from filemate.study.orchestrator.context import resolve_scope
from filemate.study.orchestrator.models import (
    LOCAL_ZONE,
    OrchestratorError,
    ScopeRequest,
    aware,
    utc_now,
)
from filemate.study.orchestrator.repository import DAY_TYPE, day_id
from filemate.study.orchestrator.snapshot import SnapshotReader
from filemate.study.orchestrator.snapshot_queries import object_json
from filemate.study.orchestrator.task_views import project_tasks

from .models import RULE_VERSION, WeeklyItem, WeeklySnapshot, WeeklySummary


class WeeklyReader:
    def __init__(self, storage, *, clock=utc_now):
        self.storage = storage
        self.clock = clock

    def read(self, scope: ScopeRequest) -> WeeklySnapshot:
        with self.storage.read_snapshot() as read:
            return self.read_in_transaction(read, scope, as_of=aware(self.clock()))

    def read_in_transaction(self, read, scope: ScopeRequest, *, as_of) -> WeeklySnapshot:
        snapshot = SnapshotReader(read).read_in_transaction(read, scope, as_of=as_of)
        projection = project_tasks(snapshot)
        tasks = {task.task_id: task for task in projection.tasks + projection.completed}
        today = as_of.astimezone(LOCAL_ZONE).date()
        monday = today - timedelta(days=today.weekday())
        days = [
            (monday + timedelta(days=index)).isoformat() for index in range(today.weekday() + 1)
        ]
        identifiers = [day_id(day) for day in days]
        placeholders = ",".join("?" for _ in identifiers)
        rows = (
            read._conn()
            .execute(
                f"SELECT artifact_id, CASE WHEN length(CAST(content AS BLOB))<=262144 "
                f"THEN content END AS content FROM artifacts WHERE artifact_type=? "
                f"AND artifact_id IN ({placeholders}) ORDER BY artifact_id",
                (DAY_TYPE, *identifiers),
            )
            .fetchall()
        )
        bindings, occurrences = [], {}
        planned_days = excluded_days = invalid_days = 0
        for row in rows:
            saved = object_json(row["content"])
            bindings.append({"id": row["artifact_id"], "saved": saved})
            if saved is None:
                invalid_days += 1
                continue
            config = saved.get("config")
            if config is None:
                continue
            if not isinstance(config, dict):
                invalid_days += 1
                continue
            try:
                saved_scope = ScopeRequest.model_validate(config.get("scope"))
                resolved, *_ = resolve_scope(read, saved_scope)
            except (ValidationError, OrchestratorError):
                excluded_days += 1
                continue
            if resolved != snapshot.scope:
                excluded_days += 1
                continue
            selected = config.get("selected_ids")
            if (
                not isinstance(selected, list)
                or len(selected) > 200
                or any(
                    not isinstance(identifier, str) or not 1 <= len(identifier) <= 500
                    for identifier in selected
                )
            ):
                invalid_days += 1
                continue
            planned_days += 1
            day = row["artifact_id"].removeprefix("learning-day-")
            for identifier in dict.fromkeys(selected):
                occurrences.setdefault(identifier, []).append(day)
        items = []
        summary = WeeklySummary(planned_days=planned_days, total_tasks=len(occurrences))
        for identifier, dates in occurrences.items():
            task = tasks.get(identifier)
            status = "unresolved"
            if task is not None and task.status == "completed":
                status = "completed"
                summary.completed_tasks += 1
            elif task is not None and task.eligibility in ("eligible", "not_due"):
                status = "pending"
                summary.pending_tasks += 1
                if task.due_date:
                    due = datetime.fromisoformat(task.due_date.replace("Z", "+00:00"))
                    due_day = (
                        due.astimezone(LOCAL_ZONE).date() if due.tzinfo is not None else due.date()
                    )
                    if due_day < today:
                        summary.overdue_tasks += 1
            else:
                summary.unresolved_tasks += 1
            items.append(WeeklyItem(task_id=identifier, status=status, dates=dates, task=task))
        items.sort(key=lambda item: (item.dates[0], item.task_id))
        coverage = {
            "meaning": "current_state_of_saved_week_arrangements",
            "excluded_days": excluded_days,
            "invalid_days": invalid_days,
            "omitted_items": max(0, len(items) - 200),
            "truncated": len(items) > 200,
            "task_coverage": projection.coverage,
            "completion_basis": "original_domain_current_state",
        }
        revision = digest(
            {
                "rule": RULE_VERSION,
                "scope": snapshot.scope.model_dump(),
                "study_date": today.isoformat(),
                "evidence": snapshot.evidence_revision,
                "saved_days": bindings,
            }
        )
        return WeeklySnapshot(
            scope=snapshot.scope,
            week_start=monday.isoformat(),
            week_end=(monday + timedelta(days=6)).isoformat(),
            study_date=today.isoformat(),
            as_of=as_of.isoformat(),
            revision=revision,
            summary=summary,
            items=items[:200],
            coverage=coverage,
        )
