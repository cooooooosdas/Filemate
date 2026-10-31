"""Bounded SQL projections without raw answers, quotations or model scores."""

import json
from typing import Any


def object_json(raw: Any, expected=dict):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, expected) else None
    except (ValueError, TypeError, RecursionError):
        return None


def coverage(total: int, returned: int) -> dict:
    return {'total': total, 'returned': returned, 'truncated': returned < total}


def safe_task(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    # 不复制自由格式的模型说明、答案或任意跳转地址。
    keys = ('task_id', 'title', 'status', 'due_date', 'completed', 'completed_at',
            'minutes', 'duration_minutes', 'focus_wrong_id', 'action', 'next_review_at')
    return {k: v for k, v in item.items() if k in keys and isinstance(v, (str, int, bool, type(None)))
            and (not isinstance(v, str) or len(v) <= 300)}


def read_plans(conn, source_ids: list[str]) -> tuple[list[dict], dict]:
    if not source_ids:
        return [], coverage(0, 0)
    where = 'source_id IN (' + ','.join('?' for _ in source_ids) + ')'
    total = conn.execute('SELECT COUNT(*) FROM study_plans WHERE ' + where, source_ids).fetchone()[0]
    rows = conn.execute('SELECT plan_id,source_id,exam_date,daily_minutes,status,completed_days,'
                        'CASE WHEN length(plan_data)<=1048576 THEN plan_data END AS plan_data '
                        'FROM study_plans WHERE ' + where + ' ORDER BY plan_id LIMIT 100', source_ids).fetchall()
    result, remaining, invalid = [], 200, 0
    for row in rows:
        plan = dict(row)
        content = object_json(plan.pop('plan_data'))
        completed = object_json(plan.pop('completed_days'), list)
        if content is None or completed is None or not isinstance(content.get('days', []), list):
            invalid += 1
            continue
        days = content.get('days', [])
        compact = []
        for i, day in enumerate(days[:remaining]):
            if not isinstance(day, dict):
                invalid += 1
                continue
            compact.append({'day_index': i, 'day': day.get('day', i + 1),
                            'date': day.get('date'), 'duration_minutes': day.get('duration_minutes', plan['daily_minutes']),
                            'completed': day.get('day', i + 1) in completed,
                            'composite': True})
        remaining -= len(compact)
        result.append(plan | {'days': compact, 'day_total': len(days)})
    return result, coverage(total, len(result)) | {'invalid': invalid, 'days_truncated': any(p['day_total'] > len(p['days']) for p in result)}


def read_semester(conn, source_ids: list[str]) -> tuple[list[dict], dict]:
    if not source_ids:
        return [], coverage(0, 0)
    row = conn.execute("SELECT artifact_id,CASE WHEN length(content)<=1048576 THEN content END AS content FROM artifacts WHERE artifact_id='personal-semester-v1' AND artifact_type='semester'").fetchone()
    if row is None:
        return [], coverage(0, 0)
    content = object_json(row['content'])
    if not content or not isinstance(content.get('config'), dict) or not isinstance(content.get('tasks'), list):
        return [], coverage(1, 0) | {'invalid': 1}
    courses = content['config'].get('courses', [])
    allowed = {c.get('course_id') for c in courses if isinstance(c, dict) and c.get('source_id') in source_ids}
    tasks = [safe_task(t) | {'artifact_id': row['artifact_id']} for t in content['tasks']
             if isinstance(t, dict) and t.get('course_id') in allowed and safe_task(t)]
    return tasks[:200], coverage(len(tasks), min(200, len(tasks)))


def read_evidence(read, source_ids: list[str], course_id: str | None):
    conn = read._conn()
    if not source_ids:
        return [], coverage(0, 0), [], coverage(0, 0)
    slots = ','.join('?' for _ in source_ids)
    total = conn.execute(f'SELECT COUNT(*) FROM quiz_attempts WHERE source_id IN ({slots})', source_ids).fetchone()[0]
    attempts = [dict(r) for r in conn.execute(f'''SELECT attempt_id,artifact_id,source_id,question_index,
        is_correct,purpose,judgement_method,judgement_status,question_digest,created_at
        FROM quiz_attempts WHERE source_id IN ({slots}) ORDER BY created_at DESC,attempt_id LIMIT 100''', source_ids)]
    graph, graph_cov = [], coverage(0, 0)
    if course_id:
        from filemate.course_graph.projection import valid_evidence
        where = f"course_id=? AND source_id IN ({slots}) AND status='confirmed'"
        params = [course_id, *source_ids]
        total_graph = conn.execute('SELECT COUNT(*) FROM kg_evidence WHERE ' + where, params).fetchone()[0]
        rows = conn.execute('SELECT evidence_id,source_id,source_revision,concept_id,relation_id,status FROM kg_evidence WHERE ' + where + ' ORDER BY evidence_id LIMIT 200', params)
        cache = {}
        for row in rows:
            if valid_evidence(read, conn, course_id, row, cache):
                graph.append(dict(row))
        graph_cov = coverage(total_graph, len(graph))
    return attempts, coverage(total, len(attempts)), graph, graph_cov
