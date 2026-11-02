"""One read transaction for scope authorization and all evidence projections."""

from datetime import datetime
from threading import RLock
from weakref import WeakValueDictionary

from filemate.execution.data_actions import digest
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries

from .context import display_label, resolve_scope
from .models import (
    LOCAL_ZONE,
    Clock,
    EvidenceSnapshot,
    ScopeRequest,
    aware,
    utc_now,
)
from .snapshot_queries import (
    coverage,
    read_evidence,
    read_interviews,
    read_plan_links,
    read_plans,
    read_semester,
    safe_task,
)

_READ_GATES = WeakValueDictionary()
_GATES_LOCK = RLock()


class SnapshotReader:
    def __init__(self, storage, *, clock: Clock | None = None):
        self.storage = storage
        self.clock = clock or utc_now
        with _GATES_LOCK:
            key = str(storage.db_path.resolve())
            self._read_gate = _READ_GATES.setdefault(key, RLock())

    def read(self, scope: ScopeRequest) -> EvidenceSnapshot:
        as_of = aware(self.clock())
        with self.storage.read_snapshot() as read:
            return self.read_in_transaction(read, scope, as_of=as_of)

    def read_in_transaction(self, read, scope: ScopeRequest, *, as_of: datetime) -> EvidenceSnapshot:
        # 同一库的快照组装串行，避免多个读线程反复争用Python/SQLite回调；其他学习空间独立。
        with self._read_gate:
            return self._read_locked(read, scope, as_of=as_of)

    def _read_locked(self, read, scope: ScopeRequest, *, as_of: datetime) -> EvidenceSnapshot:
        as_of = aware(as_of)
        conn = read._conn()
        resolved, goal, sources, course_ref, shared = resolve_scope(read, scope)
        ids = resolved.source_ids
        plans, plan_coverage = read_plans(conn, ids, scope.course_id, goal_id=scope.goal_id)
        semester, semester_coverage = read_semester(conn, ids)
        attempts, attempt_coverage, graph, graph_coverage = read_evidence(read, ids, scope.course_id)
        plan_links, link_coverage = read_plan_links(conn, ids, scope.course_id)
        interviews, interview_coverage = read_interviews(conn, scope.goal_id, ids)
        reviews = ReviewQueries(read).page_in_snapshot(read, ReviewFilter(sort='due', direction='asc'), as_of=as_of, source_ids=tuple(ids), limit=100)
        review_keys = ('wrong_id', 'artifact_id', 'source_id', 'question_index', 'question_digest', 'next_review_at',
                       'error_count', 'correct_streak', 'mastered', 'schedule_status', 'learning_status',
                       'scheduler_version', 'data_error', 'read_only_snapshot', 'revision')
        compact = [{k: r.get(k) for k in review_keys} for r in reviews['items']]
        goal_tasks = [t for item in goal.get('tasks', [])[:200] if (t := safe_task(item))]
        facts = {'goal': {'goal_id': scope.goal_id, 'source_id': conn.execute('SELECT source_id FROM artifacts WHERE artifact_id=?', (scope.goal_id,)).fetchone()[0],
                          'title': display_label(goal.get('title'), 160, '未命名目标'),
                          'deadline': goal.get('deadline'), 'goal_type': goal.get('goal_type'), 'tasks': goal_tasks},
                 'sources': sources, 'course': course_ref, 'plans': plans, 'semester': semester,
                 'reviews': compact, 'attempts': attempts, 'graph': graph, 'plan_links': plan_links, 'interviews': interviews}
        # 缺少显式问题/目标关联时保持未覆盖，不把面试评分或全图关系猜成课程证据。
        cov = {'needs_scope': not ids, 'reviews': coverage(reviews['total'], len(compact)),
               'shared_source_ids': shared, 'practice_scope_basis': 'source_records_not_course_mastery',
               'plans': plan_coverage, 'semester': semester_coverage,
               'goal_tasks': coverage(len(goal.get('tasks', [])), len(goal_tasks)),
               'attempts': attempt_coverage, 'graph': graph_coverage, 'plan_links': link_coverage,
               'interviews': interview_coverage}
        refs = [{'kind': 'goal', 'id': scope.goal_id}] + [{'kind': 'source', 'id': s['source_id'], 'updated_at': s['updated_at']} for s in sources]
        day = as_of.astimezone(LOCAL_ZONE).date().isoformat()
        revision = digest({'scope': resolved.model_dump(), 'study_date': day, 'facts': facts, 'coverage': cov})
        return EvidenceSnapshot(scope=resolved, as_of=as_of, study_date=day, evidence_revision=revision,
                                facts=facts, coverage=cov, evidence_refs=refs[:200])
