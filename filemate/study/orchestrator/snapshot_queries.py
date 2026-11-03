"""Bounded SQL projections without raw answers, quotations or model scores."""

import json
from typing import Any


def object_json(raw: Any, expected=dict):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, expected) else None
    except (ValueError, TypeError, RecursionError):
        return None


def read_interviews(conn, goal_id, source_ids):
    needles = [json.dumps({'goal_id': goal_id}, ensure_ascii=False)[1:-1],
               json.dumps({'goal_id': goal_id}, ensure_ascii=False, separators=(',', ':'))[1:-1]]
    where = '(instr(r.context_refs,?)>0 OR instr(r.context_refs,?)>0)'
    joined = 'interview_sessions i JOIN agent_runs r ON r.run_id=i.agent_run_id'
    total = conn.execute(f'SELECT count(*) FROM {joined} WHERE {where}', needles).fetchone()[0]
    rows = conn.execute(f'''SELECT i.interview_id,i.status,i.updated_at,
        CASE WHEN length(r.context_refs)<=65536 THEN r.context_refs END AS context_refs,
        (SELECT count(*) FROM interview_turns t WHERE t.interview_id=i.interview_id) AS turn_count
        FROM {joined} WHERE {where} ORDER BY i.updated_at DESC,i.interview_id LIMIT 20''', needles)
    result, excluded = [], 0
    for row in rows:
        refs = object_json(row['context_refs'])
        if (refs is None or refs.get('goal_id') != goal_id
                or refs.get('source_id') not in [None, *source_ids]):
            excluded += 1
            continue
        result.append({'interview_id': row['interview_id'], 'source_id': refs.get('source_id'),
                       'goal_id': goal_id, 'status': row['status'], 'updated_at': row['updated_at'],
                       'turn_count': row['turn_count']})
    cov = coverage(total, len(result)) | {'excluded': excluded}
    if not total:
        cov['status'] = 'no_explicit_link'
    return result, cov


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


def _plan_course(raw, kind):
    data = object_json(raw) if isinstance(raw, str) and len(raw) <= 1048576 else None
    if data is None:
        return None
    ref = data.get('course_learning') if kind == 'plan' else data
    if ref is None:
        return ''
    if not isinstance(ref, dict):
        return None
    cid = ref.get('course_id')
    return '' if cid is None else cid if isinstance(cid, str) else None


def _coach_goal(raw):
    metadata = object_json(raw) if isinstance(raw, str) and len(raw) <= 1048576 else None
    if metadata is None:
        return None
    coach = metadata.get('learning_coach')
    if coach is None:
        return ''
    return coach.get('goal_id') if isinstance(coach, dict) and isinstance(coach.get('goal_id'), str) else None


def _coach_course(raw):
    metadata = object_json(raw) if isinstance(raw, str) and len(raw) <= 1048576 else None
    coach = metadata.get('learning_coach') if metadata else None
    if not isinstance(coach, dict):
        return None
    course = coach.get('course_id')
    return '' if course is None else course if isinstance(course, str) else None


def _read_source_plans(conn, source_ids: list[str], course_id=None, *, exclude_coach=False) -> tuple[list[dict], dict]:
    if not source_ids:
        return [], coverage(0, 0)
    conn.create_function('filemate_orchestrator_course', 2, _plan_course)
    conn.create_function('filemate_coach_goal', 1, _coach_goal)
    slots = ','.join('?' for _ in source_ids)
    source_where = 'p.source_id IN (' + slots + ')'
    candidates = conn.execute('SELECT COUNT(*) FROM study_plans p WHERE ' + source_where, source_ids).fetchone()[0]
    where = source_where + ''' AND filemate_orchestrator_course(p.plan_data,'plan') IN ('',?)
        AND filemate_orchestrator_course(COALESCE(a.metadata,'{}'),'metadata') IN ('',?)
        AND NOT EXISTS(SELECT 1 FROM kg_course_plan_links l WHERE l.plan_id=p.plan_id AND l.course_id!=?)
        AND NOT EXISTS(SELECT 1 FROM kg_learning_artifact_sources r WHERE r.artifact_id=p.artifact_id
            AND r.source_id NOT IN (''' + slots + '))'
    params = [*source_ids, course_id or '', course_id or '', course_id or '', *source_ids]
    if exclude_coach:
        where += " AND filemate_coach_goal(COALESCE(a.metadata,'{}'))=''"
    joined = 'study_plans p LEFT JOIN artifacts a ON a.artifact_id=p.artifact_id'
    total = conn.execute('SELECT COUNT(*) FROM ' + joined + ' WHERE ' + where, params).fetchone()[0]
    rows = conn.execute('SELECT p.plan_id,p.source_id,p.exam_date,p.daily_minutes,p.status,p.completed_days,'
                        "CASE WHEN length(a.metadata)<=1048576 THEN a.metadata END AS metadata,"
                        'CASE WHEN length(p.plan_data)<=1048576 THEN p.plan_data END AS plan_data '
                        'FROM ' + joined + ' WHERE ' + where + ' ORDER BY p.plan_id LIMIT 100', params).fetchall()
    return _project_plans(rows, total, candidates=candidates)


def _project_plans(rows, total, *, candidates=None):
    result, remaining, invalid = [], 200, 0
    for row in rows:
        plan = dict(row)
        content = object_json(plan.pop('plan_data'))
        metadata = object_json(plan.pop('metadata', '{}'))
        completed = object_json(plan.pop('completed_days'), list)
        if content is None or completed is None or not isinstance(content.get('daily_plan'), list):
            invalid += 1
            continue
        days = content['daily_plan']
        compact = []
        for i, day in enumerate(days[:remaining]):
            if not isinstance(day, dict):
                invalid += 1
                continue
            compact.append({'day_index': i, 'day': day.get('day', i + 1),
                            'date': day.get('date'), 'duration_minutes': day.get('duration_minutes', plan['daily_minutes']),
                            'completed': i in completed,
                            'composite': True})
            if metadata and content.get('learning_coach'):
                from .coach.plans import projected_group
                keys = projected_group(content, metadata, i)
                if keys:
                    compact[-1].update(coach_group=True, coach_action_keys=keys)
        remaining -= len(compact)
        result.append(plan | {'days': compact, 'day_total': len(days)})
    return result, coverage(total, len(result)) | {'invalid': invalid, 'scope_excluded': (candidates - total) if candidates is not None else 0,
        'days_truncated': any(p['day_total'] > len(p['days']) for p in result)}


def read_goal_plans(conn, goal_id: str, source_ids: list[str], course_id: str | None) -> tuple[list[dict], dict]:
    """Read only plans explicitly linked to this goal and entirely inside its scope."""
    conn.create_function('filemate_coach_goal', 1, _coach_goal)
    conn.create_function('filemate_coach_course', 1, _coach_course)
    conn.create_function('filemate_orchestrator_course', 2, _plan_course)
    slots = ','.join('?' for _ in source_ids) or 'NULL'
    where = f"""a.artifact_type='study_plan' AND filemate_coach_goal(a.metadata)=?
        AND (p.source_id IS NULL OR p.source_id IN ({slots}))
        AND filemate_orchestrator_course(p.plan_data,'plan') IN ('',?)
        AND filemate_orchestrator_course(a.metadata,'metadata') IN ('',?)
        AND filemate_coach_course(a.metadata) IN ('',?)
        AND NOT EXISTS(SELECT 1 FROM kg_course_plan_links l WHERE l.plan_id=p.plan_id AND l.course_id!=?)
        AND NOT EXISTS(SELECT 1 FROM kg_learning_artifact_sources d WHERE d.artifact_id=p.artifact_id
            AND d.source_id NOT IN ({slots}))"""
    # NOT IN(NULL) is UNKNOWN, so an empty scope needs an explicit dependency ban.
    if not source_ids:
        where += ' AND NOT EXISTS(SELECT 1 FROM kg_learning_artifact_sources d WHERE d.artifact_id=p.artifact_id)'
    args = [goal_id, *source_ids, *([course_id or ''] * 4), *source_ids]
    joined = 'study_plans p JOIN artifacts a ON a.artifact_id=p.artifact_id'
    total = conn.execute('SELECT count(*) FROM ' + joined + ' WHERE ' + where, args).fetchone()[0]
    rows = conn.execute('SELECT p.plan_id,p.source_id,p.exam_date,p.daily_minutes,p.status,p.completed_days,'
                        "CASE WHEN length(a.metadata)<=1048576 THEN a.metadata END AS metadata,"
                        'CASE WHEN length(p.plan_data)<=1048576 THEN p.plan_data END AS plan_data '
                        'FROM ' + joined + ' WHERE ' + where + ' ORDER BY p.plan_id LIMIT 100', args).fetchall()
    return _project_plans(rows, total)


def read_plans(conn, source_ids: list[str], course_id=None, *, goal_id=None) -> tuple[list[dict], dict]:
    plans, cov = _read_source_plans(conn, source_ids, course_id, exclude_coach=goal_id is not None)
    if goal_id is None:
        return plans, cov
    linked, linked_cov = read_goal_plans(conn, goal_id, source_ids, course_id)
    return plans + linked, {'total': cov['total'] + linked_cov['total'], 'returned': len(plans) + len(linked),
        'truncated': cov['truncated'] or linked_cov['truncated'], 'invalid': cov.get('invalid', 0) + linked_cov['invalid'],
        'scope_excluded': cov.get('scope_excluded', 0), 'days_truncated': cov.get('days_truncated', False) or linked_cov['days_truncated']}


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
                item = dict(row)
                if row['relation_id']:
                    relation = conn.execute("SELECT COALESCE(a.canonical_id,a.concept_id) AS from_id,COALESCE(b.canonical_id,b.concept_id) AS to_id,r.type FROM kg_relations r JOIN kg_concepts a ON a.concept_id=r.from_id AND a.course_id=r.course_id JOIN kg_concepts b ON b.concept_id=r.to_id AND b.course_id=r.course_id WHERE r.course_id=? AND r.relation_id=? AND r.status='confirmed' AND a.status='confirmed' AND b.status='confirmed'", (course_id, row['relation_id'])).fetchone()
                    if relation:
                        item['relation'] = dict(relation)
                if row['concept_id']:
                    concept = conn.execute("SELECT COALESCE(canonical_id,concept_id) FROM kg_concepts WHERE course_id=? AND concept_id=? AND status='confirmed'", (course_id, row['concept_id'])).fetchone()
                    item['concept_id'] = concept[0] if concept else None
                graph.append(item)
        graph_cov = coverage(total_graph, len(graph))
    return attempts, coverage(total, len(attempts)), graph, graph_cov


def read_plan_links(conn, source_ids, course_id):
    if not course_id or not source_ids:
        return [], coverage(0, 0)
    slots = ','.join('?' for _ in source_ids)
    base = f''' FROM kg_course_plan_links l JOIN study_plans p ON p.plan_id=l.plan_id
        JOIN kg_concepts c ON c.course_id=l.course_id AND c.concept_id=l.concept_id
        WHERE l.course_id=? AND p.source_id IN ({slots}) AND c.status='confirmed' '''
    params = [course_id, *source_ids]
    total = conn.execute('SELECT COUNT(*)' + base, params).fetchone()[0]
    rows = [dict(r) for r in conn.execute('SELECT l.plan_id,l.day_index,COALESCE(c.canonical_id,c.concept_id) AS concept_id' + base + 'ORDER BY l.plan_id,l.day_index,l.concept_id LIMIT 200', params)]
    return rows, coverage(total, len(rows))
