"""One read transaction for scope authorization and all evidence projections."""

from datetime import datetime

from filemate.execution.data_actions import digest
from filemate.wrongbook.queries import ReviewFilter, ReviewQueries

from .models import (
    LOCAL_ZONE,
    Clock,
    EvidenceSnapshot,
    OrchestratorError,
    ScopeRequest,
    aware,
    utc_now,
)
from .snapshot_queries import (
    coverage,
    object_json,
    read_evidence,
    read_interviews,
    read_plan_links,
    read_plans,
    read_semester,
    safe_task,
)


class SnapshotReader:
    def __init__(self, storage, *, clock: Clock | None = None):
        self.storage = storage
        self.clock = clock or utc_now

    def read(self, scope: ScopeRequest) -> EvidenceSnapshot:
        as_of = aware(self.clock())
        with self.storage.read_snapshot() as read:
            return self.read_in_transaction(read, scope, as_of=as_of)

    def read_in_transaction(self, read, scope: ScopeRequest, *, as_of: datetime) -> EvidenceSnapshot:
        as_of = aware(as_of)
        conn = read._conn()
        row = conn.execute("SELECT source_id,CASE WHEN length(content)<=1048576 THEN content END AS content FROM artifacts WHERE artifact_id=? AND artifact_type='reverse_goal_plan'", (scope.goal_id,)).fetchone()
        if row is None:
            raise OrchestratorError('goal_not_found', 404)
        goal = object_json(row['content'])
        if goal is None or not isinstance(goal.get('tasks', []), list):
            raise OrchestratorError('invalid_goal_evidence')
        ids = scope.source_ids or ([row['source_id']] if row['source_id'] else [])
        if row['source_id'] and row['source_id'] not in ids:
            raise OrchestratorError('goal_source_outside_scope', 422)
        if not scope.course_id and len(ids) > 1:
            raise OrchestratorError('explicit_course_required', 422)
        shared = [r[0] for r in conn.execute(
            'SELECT s.source_id FROM kg_course_sources s JOIN kg_courses c ON c.course_id=s.course_id '
            'WHERE s.active=1 AND c.archived=0 AND s.source_id IN (' + ','.join('?' for _ in ids)
            + ') GROUP BY s.source_id HAVING count(*)>1 ORDER BY s.source_id', ids)] if ids else []
        if shared and not scope.course_id:
            raise OrchestratorError('explicit_course_required', 422)
        course_ref = None
        if scope.course_id:
            course = conn.execute('SELECT revision FROM kg_courses WHERE course_id=? AND archived=0', (scope.course_id,)).fetchone()
            if course is None:
                raise OrchestratorError('course_not_found', 404)
            members = {r['source_id'] for r in conn.execute('SELECT source_id FROM kg_course_sources WHERE course_id=? AND active=1', (scope.course_id,))}
            if not set(ids) <= members:
                raise OrchestratorError('source_outside_course', 422)
            course_ref = {'course_id': scope.course_id, 'revision': course['revision']}
        sources = []
        for sid in sorted(ids):
            source = conn.execute('SELECT source_id,updated_at FROM sources WHERE source_id=?', (sid,)).fetchone()
            if source is None:
                raise OrchestratorError('source_not_found', 404)
            sources.append(dict(source))
        resolved = ScopeRequest(goal_id=scope.goal_id, course_id=scope.course_id, source_ids=sorted(ids))
        plans, plan_coverage = read_plans(conn, ids)
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
        facts = {'goal': {'goal_id': scope.goal_id, 'source_id': row['source_id'],
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
