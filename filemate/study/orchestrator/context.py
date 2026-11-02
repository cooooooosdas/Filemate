"""Bounded stored goal metadata for choosing an explicit learning scope."""

from datetime import date
from typing import Any

from filemate.execution.storage import SQLiteStorage

from .models import GoalChoice, GoalOptionsPage, GoalOptionsRequest, OrchestratorError, ScopeRequest
from .snapshot_queries import object_json


def display_label(value: Any, limit: int, fallback: str) -> str:
    """Keep display metadata bounded without changing the stored record."""
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else fallback


def resolve_scope(read: SQLiteStorage, scope: ScopeRequest) -> tuple:
    """Authorize a scope without reading answer bodies or assembling task evidence."""
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
        source = conn.execute('SELECT source_id,substr(original_name,1,240) AS original_name,updated_at FROM sources WHERE source_id=?', (sid,)).fetchone()
        if source is None:
            raise OrchestratorError('source_not_found', 404)
        sources.append(dict(source))
    resolved = ScopeRequest(goal_id=scope.goal_id, course_id=scope.course_id, source_ids=sorted(ids))
    return resolved, goal, sources, course_ref, shared


def read_goal_options(storage: SQLiteStorage, request: GoalOptionsRequest) -> GoalOptionsPage:
    """Read one metadata page in the caller's existing isolated storage."""
    needle = request.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    label = "coalesce(nullif(trim(title),''),'未命名目标')"
    where = f"artifact_type=? AND {label} LIKE ? ESCAPE '\\'"
    params = ('reverse_goal_plan', '%' + needle + '%')
    with storage.read_snapshot() as read:
        conn = read._conn()
        total = conn.execute(f'SELECT count(*) FROM artifacts WHERE {where}', params).fetchone()[0]
        rows = conn.execute(f'''SELECT artifact_id,substr({label},1,160) AS title,source_id,
            CASE WHEN length(CAST(content AS BLOB))<=1048576 THEN content END AS content
            FROM artifacts WHERE {where} ORDER BY updated_at DESC,artifact_id LIMIT 30 OFFSET ?''',
            (*params, request.offset))
        items = []
        for row in rows:
            goal = object_json(row['content'])
            valid = goal is not None and isinstance(goal.get('tasks', []), list)
            goal = goal or {}
            goal_type = goal.get('goal_type')
            if goal_type not in (None, 'exam', 'competition', 'job', 'postgraduate', 'custom', 'skill'):
                goal_type, valid = None, False
            deadline = goal.get('deadline')
            if deadline is not None:
                try:
                    if not isinstance(deadline, str) or date.fromisoformat(deadline).isoformat() != deadline:
                        raise ValueError('invalid_deadline')
                except ValueError:
                    deadline, valid = None, False
            items.append(GoalChoice(goal_id=row['artifact_id'], title=row['title'], source_id=row['source_id'],
                                    goal_type=goal_type, deadline=deadline, valid=valid))
        return GoalOptionsPage(items=items, total=total, offset=request.offset)
