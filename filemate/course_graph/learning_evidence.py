"""Project actual course training records in one detached SQLite read snapshot."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from filemate.course_graph.models import CourseGraphError, digest
from filemate.course_graph.question_links import _concept, question_digest
from filemate.course_graph.workspace_models import validate_page
from filemate.course_graph.workspace_snapshot import read_workspace_snapshot
from filemate.study.knowledge_graph import _after_question_revision

RULE_VERSION = 'course-training-v1'
STATUSES = frozenset({'no_evidence', 'practiced', 'needs_reinforcement', 'recently_stable'})
SHANGHAI = ZoneInfo('Asia/Shanghai')


def parse_time(value: Any) -> datetime | None:
    """Read legacy UTC timestamps conservatively without treating invalid dates as due."""
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _clock(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise CourseGraphError('aware_clock_required', 422)
    return now.astimezone(timezone.utc)


def _page(items, offset, limit):
    return {'items': items[offset:offset + limit], 'total': len(items), 'offset': offset, 'limit': limit}


def read_learning_projection(read, cid: str, *, now: datetime) -> dict[str, Any]:
    """Batch only explicitly mapped question sets, preserving original member identities."""
    now = _clock(now)
    conn, snapshot = read._conn(), read_workspace_snapshot(read, cid)
    links = [dict(r) for r in conn.execute(
        'SELECT * FROM kg_question_links WHERE course_id=? AND active=1 ORDER BY link_id', (cid,))]
    artifacts = {r['artifact_id']: read._decode_row(r, ('content', 'metadata')) for r in conn.execute('''
        SELECT * FROM artifacts WHERE artifact_id IN
        (SELECT artifact_id FROM kg_question_links WHERE course_id=? AND active=1) ORDER BY artifact_id''', (cid,))}
    # 先限定题目身份，再使用现有artifact索引；无关课程的作答不能驱动内层映射扫描。
    selector = '''WITH mapped AS MATERIALIZED (
        SELECT DISTINCT artifact_id,question_index FROM kg_question_links WHERE course_id=? AND active=1
    ), versions AS MATERIALIZED (
        SELECT a.artifact_id,m.question_index,json_extract(a.metadata,'$.question_revision_parent') AS revision_parent
        FROM mapped m JOIN artifacts a USING(artifact_id)
        UNION
        SELECT a.artifact_id,m.question_index,json_extract(a.metadata,'$.question_revision_parent') AS revision_parent
        FROM artifacts a JOIN mapped m ON m.artifact_id=json_extract(a.metadata,'$.question_revision_parent')
    ), scoped_artifacts AS MATERIALIZED (
        SELECT DISTINCT artifact_id FROM versions
    )'''
    attempts = [dict(r) for r in conn.execute(f'''{selector} SELECT q.rowid AS evidence_sequence,
        q.attempt_id,q.artifact_id,q.question_index,q.is_correct,q.score,q.created_at,
        v.revision_parent FROM scoped_artifacts s CROSS JOIN quiz_attempts q
        ON q.artifact_id=s.artifact_id CROSS JOIN versions v
        ON v.artifact_id=q.artifact_id AND v.question_index=q.question_index
        ORDER BY q.created_at DESC,q.attempt_id''', (cid,))]
    wrongs = [dict(r) for r in conn.execute(f'''{selector} SELECT q.wrong_id,q.artifact_id,q.question_index,q.question,
        q.mastered,q.next_review_at,q.updated_at,
        v.revision_parent FROM scoped_artifacts s CROSS JOIN wrong_questions q
        ON q.artifact_id=s.artifact_id CROSS JOIN versions v
        ON v.artifact_id=q.artifact_id AND v.question_index=q.question_index
        ORDER BY q.updated_at DESC,q.wrong_id''', (cid,))]
    plans = [dict(r) for r in conn.execute('''SELECT l.*,p.status,p.title,p.completed_days,p.updated_at
        FROM kg_course_plan_links l JOIN study_plans p USING(plan_id)
        WHERE l.course_id=? ORDER BY p.updated_at DESC,l.plan_id,l.day_index,l.concept_id''', (cid,))]
    evidence_digest = digest({'rule': RULE_VERSION, 'links': links, 'artifacts': artifacts,
                              'attempts': attempts, 'wrongs': wrongs, 'plans': plans})
    details = {nid: {'question_refs': {}, 'attempts': {}, 'wrongs': {}, 'plans': {}, 'excluded': set()}
               for nid in snapshot.nodes}
    targets, valid, questions = {}, {}, {}
    for link in links:
        root = snapshot.member_to_root.get(link['concept_id'])
        if root is None:
            continue
        key = (link['artifact_id'], link['question_index'])
        targets.setdefault(key, set()).add(root)
        artifact = artifacts.get(key[0])
        question = None
        if (artifact and artifact['artifact_type'] == 'questions'
                and not artifact['metadata'].get('read_only_snapshot')
                and isinstance(artifact['content'], list) and 0 <= key[1] < len(artifact['content'])):
            question = artifact['content'][key[1]]
        try:
            matches = question is not None and question_digest(question) == link['question_digest']
        except (ValueError, TypeError):
            matches = False
        if matches:
            valid.setdefault(key, set()).add(root)
            questions[key] = question
        source = snapshot.sources.get(link['source_id'])
        details[root]['question_refs'][(*key, link['question_digest'])] = {
            'artifact_id': key[0], 'question_index': key[1], 'question_digest': link['question_digest'],
            'source_id': link['source_id'], 'link_valid': bool(matches),
            'source_available': bool(source and source['active']),
            'stem': str(question.get('stem', question.get('question', '')))[:300] if isinstance(question, dict) else '',
        }
    valid_attempt_pairs = set()
    for record in attempts:
        key = (record['revision_parent'] or record['artifact_id'], record['question_index'])
        stamp = parse_time(record['created_at'])
        good = (not record['revision_parent'] and stamp is not None and stamp <= now and key in valid
                and _after_question_revision(record, artifacts[key[0]]))
        if good:
            valid_attempt_pairs.add(key)
        for root in targets.get(key, ()):
            item = details[root]
            if not good or root not in valid.get(key, ()):
                item['excluded'].add(('attempt', record['attempt_id']))
                continue
            item['attempts'][record['attempt_id']] = {
                'attempt_id': record['attempt_id'], 'artifact_id': key[0], 'question_index': key[1],
                'is_correct': bool(record['is_correct']), 'score': record['score'], 'created_at': record['created_at']}
    for record in wrongs:
        key = (record['revision_parent'] or record['artifact_id'], record['question_index'])
        stamp = parse_time(record['updated_at'])
        try:
            matches = key in valid and question_digest(json.loads(record['question'])) == question_digest(questions[key])
        except (ValueError, TypeError):
            matches = False
        good = (not record['revision_parent'] and matches and stamp is not None
                and stamp <= now and key in valid_attempt_pairs)
        for root in targets.get(key, ()):
            item = details[root]
            if not good or root not in valid.get(key, ()):
                item['excluded'].add(('wrong', record['wrong_id']))
                continue
            due = parse_time(record['next_review_at'])
            item['wrongs'][record['wrong_id']] = {
                'wrong_id': record['wrong_id'], 'artifact_id': key[0], 'question_index': key[1],
                'mastered': bool(record['mastered']), 'next_review_at': record['next_review_at'],
                'updated_at': record['updated_at'], 'due': not record['mastered'] and due is not None and due <= now,
            }
    for plan in plans:
        root = snapshot.member_to_root.get(plan['concept_id'])
        if root is not None:
            details[root]['plans'][(plan['plan_id'], plan['day_index'])] = {
                'plan_id': plan['plan_id'], 'day_index': plan['day_index'], 'title': plan['title'],
                'status': plan['status'], 'completed': plan['day_index'] in json.loads(plan['completed_days']),
                'updated_at': plan['updated_at']}
    summaries = {}
    for nid, node in snapshot.nodes.items():
        item = details[nid]
        all_attempts = list(item['attempts'].values())
        recent = [a for a in all_attempts if parse_time(a['created_at']) >= now - timedelta(days=30)]
        correct = [a for a in recent if a['is_correct']]
        recent_wrong = [a['attempt_id'] for a in all_attempts if not a['is_correct']
                        and parse_time(a['created_at']) >= now - timedelta(days=7)]
        due = [w['wrong_id'] for w in item['wrongs'].values() if w['due']]
        correct_questions = {(a['artifact_id'], a['question_index']) for a in correct}
        correct_days = {parse_time(a['created_at']).astimezone(SHANGHAI).date() for a in correct}
        status = ('needs_reinforcement' if recent_wrong or due else
                  'recently_stable' if len(correct_questions) >= 3 and len(correct_days) >= 2 else
                  'practiced' if all_attempts else 'no_evidence')
        summaries[nid] = {'concept_id': nid, 'label': node['label'], 'status': status,
            'active_support': node['source_status'] == 'available',
            'counts': {'attempts': len(all_attempts), 'attempts_30d': len(recent),
                       'correct_questions_30d': len(correct_questions), 'correct_days_30d': len(correct_days),
                       'wrong_attempts_7d': len(recent_wrong), 'due_reviews': len(due),
                       'linked_questions': sum(q['link_valid'] and q['source_available'] for q in item['question_refs'].values()),
                       'completed_plan_days': sum(p['completed'] for p in item['plans'].values())},
            'reasons': {'recent_wrong_attempt_ids': recent_wrong[:50], 'due_wrong_ids': due[:50],
                        'truncated': len(recent_wrong) > 50 or len(due) > 50},
            'excluded_count': len(item['excluded']), 'rule_version': RULE_VERSION}
    evidence_digest = digest({'records': evidence_digest, 'windowed_training': summaries})
    return {'course_id': cid, 'graph_digest': snapshot.graph_digest, 'evidence_digest': evidence_digest,
            'rule_version': RULE_VERSION, 'as_of': now.isoformat(), 'nodes': summaries,
            '_snapshot': snapshot, '_details': details}


def learning_snapshot(storage, cid: str, *, now: datetime) -> dict[str, Any]:
    """Return real training summaries without answer bodies or a mastery percentage."""
    with storage.read_snapshot() as read:
        result = read_learning_projection(read, cid, now=now)
    return {key: value for key, value in result.items() if not key.startswith('_')}


def node_learning_evidence(storage, cid: str, nid: str, *, now: datetime,
                           offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """Page versioned question identities and actual attempt, review and plan records."""
    validate_page(limit, offset)
    with storage.read_snapshot() as read:
        projection = read_learning_projection(read, cid, now=now)
    root = _concept(projection['_snapshot'], nid)
    item = projection['_details'][root]
    return {**projection['nodes'][root], 'course_id': cid,
            'graph_digest': projection['graph_digest'], 'evidence_digest': projection['evidence_digest'],
            'as_of': projection['as_of'], 'windows': {
                'recent_wrong_from': (_clock(now) - timedelta(days=7)).isoformat(),
                'correct_from': (_clock(now) - timedelta(days=30)).isoformat(),
                'through': projection['as_of'], 'calendar_timezone': 'Asia/Shanghai', 'inclusive': True},
            **{name: _page(list(item[name].values()), offset, limit)
               for name in ('question_refs', 'attempts', 'wrongs', 'plans')}}


def list_learning_nodes(storage, cid: str, *, now: datetime, status: str | None = None,
                         offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """Page course summaries with an explicit conservative status filter."""
    validate_page(limit, offset)
    if status is not None and status not in STATUSES:
        raise CourseGraphError('invalid_training_status', 422)
    projection = learning_snapshot(storage, cid, now=now)
    items = [node for node in projection.pop('nodes').values() if status is None or node['status'] == status]
    return {**projection, **_page(items, offset, limit)}
