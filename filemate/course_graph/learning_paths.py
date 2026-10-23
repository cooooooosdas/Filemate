"""Explainable, bounded course paths that add rather than overwrite study plans."""

import heapq
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import uuid4

from filemate.course_graph.fusion import _check_preview, _used_receipt
from filemate.course_graph.learning_commands import target_states
from filemate.course_graph.learning_evidence import SHANGHAI, read_learning_projection
from filemate.course_graph.models import CourseGraphError, bounded_text, digest, request_key_valid
from filemate.course_graph.question_links import _concept
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.execution import data_actions
from filemate.task_resources import admit_plan

FIELDS = frozenset({'goal', 'concept_ids', 'chapter_id', 'goal_id', 'daily_minutes', 'days'})


def _options(options):
    if not isinstance(options, dict) or set(options) - FIELDS or 'goal' not in options:
        raise CourseGraphError('invalid_path_options', 422)
    result = {'concept_ids': None, 'chapter_id': None, 'goal_id': None,
              'daily_minutes': 20, 'days': 7, **options}
    result['goal'] = bounded_text(result['goal'], 500)
    if (type(result['daily_minutes']) is not int or not 5 <= result['daily_minutes'] <= 180
            or type(result['days']) is not int or not 1 <= result['days'] <= 7):
        raise CourseGraphError('invalid_path_budget', 422)
    for key in ('chapter_id', 'goal_id'):
        if result[key] is not None:
            result[key] = bounded_text(result[key], 120)
    ids = result['concept_ids']
    if ids is not None:
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 30
                or any(not isinstance(i, str) or not 1 <= len(i) <= 120 for i in ids)
                or len(set(ids)) != len(ids)):
            raise CourseGraphError('invalid_path_selection', 422)
        result['concept_ids'] = sorted(ids)
    return result


def _dependencies(snapshot, eligible):
    if len(snapshot.nodes) > 10_000 or len(snapshot.relations) > 30_000:
        raise CourseGraphError('dependency_check_limit')
    predecessors, successors, reasons = {}, {}, {}
    for edge in snapshot.relations:
        if (edge['status'] != 'confirmed' or edge['type'] not in {'prerequisite', 'depends_on'}
                or not snapshot.relation_refs.get(edge['relation_id'])):
            continue
        a, b = snapshot.member_to_root.get(edge['from_id']), snapshot.member_to_root.get(edge['to_id'])
        if a not in eligible or b not in eligible or a == b:
            continue
        if edge['type'] == 'depends_on':
            a, b = b, a
        predecessors.setdefault(b, set()).add(a)
        successors.setdefault(a, set()).add(b)
        reasons.setdefault(a, set()).add(edge['relation_id'])
        reasons.setdefault(b, set()).add(edge['relation_id'])
    degree = {nid: len(predecessors.get(nid, ())) for nid in eligible}
    queue = [nid for nid, value in degree.items() if value == 0]
    heapq.heapify(queue)
    visited = 0
    while queue:
        nid = heapq.heappop(queue)
        visited += 1
        for child in successors.get(nid, ()):
            degree[child] -= 1
            if degree[child] == 0:
                heapq.heappush(queue, child)
    if visited != len(eligible):
        raise CourseGraphError('dependency_cycle')
    return predecessors, successors, reasons


def _build(read, cid, options, now):
    projection = read_learning_projection(read, cid, now=now)
    snapshot, nodes = projection['_snapshot'], projection['nodes']
    eligible = {nid for nid, node in nodes.items() if node['active_support']}
    selected = ({_concept(snapshot, nid) for nid in options['concept_ids']}
                if options['concept_ids'] is not None else set(nodes))
    chapter = options['chapter_id']
    if chapter is not None:
        if chapter not in snapshot.groups:
            raise CourseGraphError('chapter_not_found', 404)
        selected &= snapshot.group_members[chapter]
        eligible &= snapshot.group_members[chapter]
    requested_count = len(selected)
    selected &= eligible
    if not selected:
        raise CourseGraphError('path_no_supported_concepts', 422)
    goal_artifact, goal_digest = None, None
    if options['goal_id']:
        goal_artifact = read.get_artifact(options['goal_id'])
        if not goal_artifact or goal_artifact['artifact_type'] != 'reverse_goal_plan':
            raise CourseGraphError('goal_not_found', 404)
        sid = goal_artifact['source_id']
        if sid is not None and not snapshot.fingerprints.get(sid):
            raise CourseGraphError('goal_not_in_course', 404)
        goal_digest = digest(goal_artifact)
    predecessors, successors, relations = _dependencies(snapshot, eligible)
    closure, pending = set(selected), list(selected)
    while pending:
        for parent in predecessors.get(pending.pop(), ()):
            if parent not in closure:
                closure.add(parent)
                pending.append(parent)

    def rank(nid):
        count = nodes[nid]['counts']
        return (0 if count['due_reviews'] else 1 if count['wrong_attempts_7d'] else 2 if nid in selected else 3,
                tuple(snapshot.nodes[nid]['chapter_ids']), nodes[nid]['label'], nid)

    degree = {nid: len(predecessors.get(nid, set()) & closure) for nid in closure}
    queue = [(rank(nid), nid) for nid, value in degree.items() if value == 0]
    heapq.heapify(queue)
    ordered = []
    while queue:
        _, nid = heapq.heappop(queue)
        ordered.append(nid)
        for child in successors.get(nid, set()) & closure:
            degree[child] -= 1
            if degree[child] == 0:
                heapq.heappush(queue, (rank(child), child))
    tasks, start = [], now.astimezone(SHANGHAI).date()
    for i, nid in enumerate(ordered[:options['days']]):
        node = nodes[nid]
        due, wrong = node['reasons']['due_wrong_ids'], node['reasons']['recent_wrong_attempt_ids']
        kind = 'review' if due or wrong else 'practice' if node['counts']['linked_questions'] else 'read'
        why = ('存在已到期且未掌握的错题' if due else '近7天有真实错答' if wrong else
               '为已确认的前置知识补充训练' if nid not in selected else '按所选目标范围安排下一步')
        reason_ids = sorted(relations.get(nid, ()))
        tasks.append({'concept_id': nid, 'label': node['label'], 'day_index': i, 'date': (start + timedelta(days=i)).isoformat(),
            'kind': kind, 'duration_minutes': min(options['daily_minutes'], 20 if kind == 'practice' else 15),
            'reason': why, 'reasons': {'wrong_ids': due, 'attempt_ids': wrong, 'relation_ids': reason_ids[:12],
                'relation_ids_truncated': len(reason_ids) > 12, 'goal_id': options['goal_id'],
                'rule_version': projection['rule_version']},
            'route': '/knowledge-graph?' + urlencode({'graph_scope': 'course', 'course': cid, 'node': nid, 'view': 'graph'})})
    sources = {ref['source_id'] for t in tasks for ref in snapshot.refs.get(t['concept_id'], [])}
    sources.update(ref['source_id'] for t in tasks for rid in t['reasons']['relation_ids']
                   for ref in snapshot.relation_refs.get(rid, []))
    if goal_artifact and goal_artifact['source_id']:
        sources.add(goal_artifact['source_id'])
    result = {'course_id': cid, 'course_name': snapshot.course['name'], 'options': options,
              'graph_digest': projection['graph_digest'], 'evidence_digest': projection['evidence_digest'],
              'rule_version': projection['rule_version'], 'start_date': start.isoformat(), 'tasks': tasks,
              'omitted_count': len(closure) - len(tasks), 'unsupported_count': requested_count - len(selected),
              'scope_expanded_count': len(closure - selected), 'goal_id': options['goal_id'],
              'goal_title': (goal_artifact.get('content') or {}).get('title') if goal_artifact else None,
              '_source_ids': sorted(sources), '_goal_digest': goal_digest}
    result['_revision'] = digest(result)
    return result


def _public(result):
    return {k: v for k, v in result.items() if not k.startswith('_')}


def suggest_path(storage, cid, goal, *, concept_ids=None, chapter_id=None, goal_id=None,
                   daily_minutes=20, days=7, now):
    """Read a bounded prerequisite-aware path without making tasks or invoking a model."""
    options = _options({'goal': goal, 'concept_ids': concept_ids, 'chapter_id': chapter_id,
                        'goal_id': goal_id, 'daily_minutes': daily_minutes, 'days': days})
    with storage.read_snapshot() as read:
        return _public(_build(read, cid, options, now))


def preview_path(storage, cid, options, *, now=None):
    """Bind goal, graph, training evidence and time budget to a confirmation token."""
    options, now = _options(options), now or datetime.now(timezone.utc)
    with transaction(storage) as conn:
        result = _build(storage, cid, options, now)
        token = data_actions.issue(conn, 'course_graph_learning_path', cid, result['_revision'])
        return {**_public(result), 'confirmation_token': token}


def _plan(path):
    options, tasks = path['options'], path['tasks']
    return {'title': f"{path['course_name']} · {options['goal'][:40]}", 'exam_date': tasks[-1]['date'],
        'total_days': len(tasks), 'daily_minutes': options['daily_minutes'], 'goal': options['goal'],
        'strategy': '按真实错题、目标范围与已确认前置关系安排；完成计划不代表答对或掌握。',
        'topics': [{'name': t['label'], 'priority': 'high' if t['kind'] == 'review' else 'normal',
                    'reason': t['reason']} for t in tasks], 'checkpoints': [],
        'daily_plan': [{'date': t['date'], 'focus': t['label'], 'duration_minutes': t['duration_minutes'],
            'review_method': {'review': '核对原作答并复习', 'practice': '独立作答后核对', 'read': '阅读原文并主动回忆'}[t['kind']],
            'tasks': [f"{t['label']}：{t['reason']}"], 'training_actions': [{'label': '打开知识点训练', 'route': t['route']}]}
            for t in tasks], 'course_learning': {'course_id': path['course_id'], 'tasks': tasks,
                'graph_digest': path['graph_digest'], 'evidence_digest': path['evidence_digest'],
                'rule_version': path['rule_version']}}


def confirm_path(storage, cid, options, confirmation_token, request_key, confirmed, *, now=None):
    """Add one existing-format StudyPlan atomically, preserving every manual plan."""
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError('confirmation_required', 422)
    options, now = _options(options), now or datetime.now(timezone.utc)
    selection = digest(options)
    hashed = digest({'options': selection, 'token': confirmation_token})
    with transaction(storage) as conn:
        require_course(conn, cid)
        previous = get_request(conn, cid, request_key, 'learning_path', hashed)
        if previous:
            return previous['metadata']['receipt']
        used = _used_receipt(conn, 'course_graph_learning_path', cid, confirmation_token)
        if used:
            if used['options_digest'] != selection:
                raise CourseGraphError('request_key_conflict')
            record_change(conn, cid, request_key, 'learning_path', hashed,
                          {'receipt': used, 'alias_of': used['operation_id']})
            return used
        path = _build(storage, cid, options, now)
        _check_preview(conn, 'course_graph_learning_path', cid, confirmation_token, path['_revision'])
        plan = _plan(path)
        pid, aid, oid = uuid4().hex, uuid4().hex, str(uuid4())
        content = json.dumps(plan, ensure_ascii=False)
        sid = path['_source_ids'][0]
        admit_plan(storage.db_path, 'study_plan', plan)
        conn.execute('''INSERT INTO artifacts(artifact_id,source_id,artifact_type,title,content,metadata)
            VALUES(?,?,'study_plan',?,?,?)''', (aid, sid, plan['title'], content,
            json.dumps({'course_id': cid, 'course_learning_path': oid})))
        conn.execute('''INSERT INTO study_plans(plan_id,artifact_id,source_id,title,exam_date,daily_minutes,goal,plan_data)
            VALUES(?,?,?,?,?,?,?,?)''', (pid, aid, sid, plan['title'], plan['exam_date'],
            options['daily_minutes'], options['goal'], content))
        conn.executemany('INSERT INTO kg_learning_artifact_sources VALUES(?,?)', [(aid, s) for s in path['_source_ids']])
        conn.executemany('INSERT INTO kg_course_plan_links VALUES(?,?,?,?)',
                         [(pid, cid, t['concept_id'], t['day_index']) for t in path['tasks']])
        targets = [{'table': 'study_plans', 'id': pid, 'before': 0, 'after': 1}]
        receipt = {'operation_id': oid, 'plan_id': pid, 'artifact_id': aid, 'options_digest': selection,
                   'route': f'/study-plan?plan={pid}', 'affected': {'plans': 1, 'tasks': len(path['tasks'])}}
        record_change(conn, cid, request_key, 'learning_path', hashed, {'receipt': receipt,
            'targets': targets, 'expected': digest(target_states(conn, targets))}, oid)
        data_actions.finish(conn, 'course_graph_learning_path', cid, confirmation_token, receipt)
        return receipt
