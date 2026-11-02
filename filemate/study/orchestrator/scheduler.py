"""Deterministic bounded scheduling without SQL, clocks or model calls."""

from collections import Counter
from datetime import date

from filemate.wrongbook.engine import parse_time

from .models import (
    LOCAL_ZONE,
    EvidenceSnapshot,
    OrchestratorError,
    ScheduleOptions,
    ScheduleResult,
    TaskProjection,
)

RULE_VERSION = 'learning-orchestrator-rules-v1'


def build_schedule(snapshot: EvidenceSnapshot, projection: TaskProjection, options: ScheduleOptions) -> ScheduleResult:
    all_ids = {t.task_id for t in projection.tasks + projection.completed}
    specified = set(options.item_order + options.pinned_ids + options.excluded_ids) | set(options.minute_overrides)
    if not specified <= all_ids:
        raise OrchestratorError('task_reference_changed', 422)
    manual = {tid: n for n, tid in enumerate(options.item_order)}
    today = date.fromisoformat(snapshot.study_date)
    task_map = {t.task_id: t for t in projection.tasks + projection.completed}
    depths, cycles = {}, set()

    def depth(tid, path=()):
        if tid in path:
            cycles.update(path[path.index(tid):])
            return 0
        if tid not in task_map:
            return 0
        if tid not in depths:
            depths[tid] = max((depth(dep, (*path, tid)) + 1 for dep in task_map[tid].dependency_ids), default=0)
        return depths[tid]
    for tid in task_map:
        depth(tid)

    def rank(task):
        due = parse_time(task.due_date) if task.due_date else None
        due_day = due.astimezone(LOCAL_ZONE).date().isoformat() if due else '9999-12-31'
        return (0 if task.task_id in manual else 1, manual.get(task.task_id, 0),
                0 if due and due_day <= today.isoformat() else 1,
                due_day, -task.recorded_errors, depths[task.task_id], task.task_id)

    selected, deferred, used = [], [], 0
    for original in sorted(projection.tasks, key=rank):
        task = original.model_copy(deep=True)
        if task.task_id in options.minute_overrides:
            task.estimated_minutes = options.minute_overrides[task.task_id]
            task.estimate_source = 'user_estimate'
        minutes = task.estimated_minutes
        reason = None
        if task.task_id in options.excluded_ids:
            reason = 'excluded'
        elif task.task_id in cycles:
            reason = 'dependency_cycle'
        elif any(dep not in task_map or (task_map[dep].status != 'completed' and dep not in {t.task_id for t in selected}) for dep in task.dependency_ids):
            reason = 'prerequisite_unavailable'
        elif task.eligibility != 'eligible':
            reason = task.eligibility
        elif minutes is None:
            reason = 'estimate_required'
        elif len(selected) >= 20:
            reason = 'limit'
        elif used + minutes > options.available_minutes:
            reason = 'budget'
        if reason:
            deferred.append({'task_id': task.task_id, 'reason': reason,
                             'pinned': task.task_id in options.pinned_ids})
        else:
            selected.append(task)
            used += minutes
    return ScheduleResult(rule_version=RULE_VERSION, selected=selected, deferred=deferred[:100],
                          deferred_count=len(deferred), deferred_counts=dict(Counter(t['reason'] for t in deferred)),
                          deferred_truncated=len(deferred) > 100, completed=projection.completed,
                          coverage=projection.coverage, estimated_minutes=used)
