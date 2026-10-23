"""Human-reviewed question mappings to stable course concepts."""

import re
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from filemate.course_graph.fusion import _check_preview, _used_receipt
from filemate.course_graph.learning_commands import target_states
from filemate.course_graph.models import CourseGraphError, digest, now_iso, request_key_valid
from filemate.course_graph.repository import get_request, record_change, transaction
from filemate.course_graph.workspace_models import validate_page
from filemate.course_graph.workspace_snapshot import read_workspace_snapshot
from filemate.execution import data_actions
from filemate.study.question_validation import validate_question


def question_digest(question: dict[str, Any]) -> str:
    """Version a validated question independently of its label candidate."""
    return digest(validate_question(question, legacy=True))


def _concept(snapshot, nid):
    if nid not in snapshot.member_to_root:
        raise CourseGraphError('concept_not_found', 404)
    return snapshot.member_to_root[nid]


def _selection(items, active):
    if type(active) is not bool or not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise CourseGraphError('invalid_question_selection', 422)
    result, seen = [], set()
    for item in items:
        if (not isinstance(item, dict) or set(item) != {'artifact_id', 'question_index', 'question_digest'}
                or not isinstance(item['artifact_id'], str) or not 1 <= len(item['artifact_id']) <= 120
                or type(item['question_index']) is not int or not 0 <= item['question_index'] <= 100_000
                or not isinstance(item['question_digest'], str)
                or not re.fullmatch('[a-f0-9]{64}', item['question_digest'])):
            raise CourseGraphError('invalid_question_selection', 422)
        key = (item['artifact_id'], item['question_index'], item['question_digest'])
        if key in seen:
            raise CourseGraphError('duplicate_question_selection', 422)
        seen.add(key)
        result.append(dict(item))
    return sorted(result, key=lambda i: (i['artifact_id'], i['question_index'], i['question_digest']))


def _question(storage, conn, cid, item):
    artifact = storage.get_artifact(item['artifact_id'])
    if (not artifact or artifact['artifact_type'] != 'questions'
            or artifact.get('metadata', {}).get('read_only_snapshot')
            or not conn.execute('SELECT 1 FROM kg_course_sources WHERE course_id=? AND source_id=? AND active=1',
                                (cid, artifact['source_id'])).fetchone()):
        raise CourseGraphError('question_not_in_course', 404)
    questions = artifact['content']
    if not isinstance(questions, list) or item['question_index'] >= len(questions):
        raise CourseGraphError('question_changed')
    try:
        actual = question_digest(questions[item['question_index']])
    except (ValueError, TypeError):
        raise CourseGraphError('invalid_question', 422) from None
    if actual != item['question_digest']:
        raise CourseGraphError('question_changed')
    return artifact


def question_candidates(storage, cid: str, nid: str, *, q: str = '', offset: int = 0,
                        limit: int = 50) -> dict[str, Any]:
    """Page valid course questions without inferring mappings from text occurrence."""
    validate_page(limit, offset)
    if not isinstance(q, str) or len(q) > 160:
        raise CourseGraphError('invalid_query', 422)
    with storage.read_snapshot() as read:
        snapshot = read_workspace_snapshot(read, cid)
        root = _concept(snapshot, nid)
        conn, members = read._conn(), {m for m, r in snapshot.member_to_root.items() if r == root}
        linked = {(r['artifact_id'], r['question_index'], r['question_digest']) for r in conn.execute(
            'SELECT * FROM kg_question_links WHERE course_id=? AND active=1', (cid,)) if r['concept_id'] in members}
        total, result = 0, []
        for row in conn.execute('''SELECT a.* FROM artifacts a JOIN kg_course_sources m USING(source_id)
                WHERE m.course_id=? AND m.active=1 AND a.artifact_type='questions' ORDER BY a.artifact_id''', (cid,)):
            artifact = read._decode_row(row, ('content', 'metadata'))
            if artifact['metadata'].get('read_only_snapshot') or not isinstance(artifact['content'], list):
                continue
            for index, question in enumerate(artifact['content']):
                try:
                    normalized = validate_question(question, legacy=True)
                except (ValueError, TypeError):
                    continue
                if q.casefold() not in normalized['stem'].casefold():
                    continue
                if offset <= total < offset + limit:
                    hashed = question_digest(question)
                    result.append({'artifact_id': artifact['artifact_id'], 'source_id': artifact['source_id'],
                        'question_index': index, 'question_digest': hashed, 'question': question,
                        'linked': (artifact['artifact_id'], index, hashed) in linked})
                total += 1
        return {'course_id': cid, 'concept_id': root, 'graph_digest': snapshot.graph_digest,
                'items': result, 'total': total, 'offset': offset, 'limit': limit}


def _context(storage, conn, cid, nid, items, active):
    snapshot = read_workspace_snapshot(storage, cid)
    _concept(snapshot, nid)
    rows = []
    for item in items:
        artifact = _question(storage, conn, cid, item)
        lid = uuid5(NAMESPACE_URL, f'course-question:{cid}:{nid}:{item["artifact_id"]}:{item["question_index"]}:{item["question_digest"]}').hex
        row = conn.execute('SELECT * FROM kg_question_links WHERE link_id=?', (lid,)).fetchone()
        rows.append({'id': lid, 'source_id': artifact['source_id'], 'item': item, 'previous': dict(row) if row else None})
    selection = digest({'node': nid, 'items': items, 'active': active})
    revision = digest({'graph': snapshot.graph_digest, 'selection': selection,
                       'rows': [r['previous'] for r in rows]})
    return rows, revision, selection


def preview_question_links(storage, cid: str, nid: str, items: list[dict[str, Any]],
                            active: bool = True) -> dict[str, Any]:
    """Bind a human's selected question versions to the current course snapshot."""
    items = _selection(items, active)
    with transaction(storage) as conn:
        rows, revision, _ = _context(storage, conn, cid, nid, items, active)
        token = data_actions.issue(conn, 'course_graph_learning_links', f'{cid}:{nid}', revision)
        return {'confirmation_token': token, 'concept_id': nid, 'items': items, 'active': active,
                'changed_count': sum(bool(r['previous'] and r['previous']['active']) != active for r in rows)}


def confirm_question_links(storage, cid: str, nid: str, items: list[dict[str, Any]], active: bool,
                            confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]:
    """Create explicit links atomically; a duplicate token never creates a second change."""
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError('confirmation_required', 422)
    items = _selection(items, active)
    selection = digest({'node': nid, 'items': items, 'active': active})
    command = digest({'selection': selection, 'token': confirmation_token})
    resource = f'{cid}:{nid}'
    with transaction(storage) as conn:
        from filemate.course_graph.repository import require_course
        require_course(conn, cid)
        previous = get_request(conn, cid, request_key, 'learning_links', command)
        if previous:
            return previous['metadata']['receipt']
        used = _used_receipt(conn, 'course_graph_learning_links', resource, confirmation_token)
        if used:
            if used['selection_digest'] != selection:
                raise CourseGraphError('request_key_conflict')
            record_change(conn, cid, request_key, 'learning_links', command,
                          {'receipt': used, 'alias_of': used['operation_id']})
            return used
        rows, revision, _ = _context(storage, conn, cid, nid, items, active)
        _check_preview(conn, 'course_graph_learning_links', resource, confirmation_token, revision)
        targets = []
        for row in rows:
            old = row['previous']
            before = int(bool(old and old['active']))
            if before == int(active):
                continue
            item, stamp = row['item'], now_iso()
            conn.execute('''INSERT INTO kg_question_links(link_id,course_id,concept_id,artifact_id,source_id,
                            question_index,question_digest,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(link_id) DO UPDATE SET active=excluded.active,
                            revision=kg_question_links.revision+1,updated_at=excluded.updated_at''',
                         (row['id'], cid, nid, item['artifact_id'], row['source_id'], item['question_index'],
                          item['question_digest'], int(active), stamp, stamp))
            targets.append({'table': 'kg_question_links', 'id': row['id'], 'before': before, 'after': int(active)})
        oid = str(uuid4())
        receipt = {'operation_id': oid, 'selection_digest': selection, 'affected': {'learning_links': len(targets)}}
        record_change(conn, cid, request_key, 'learning_links', command,
            {'receipt': receipt, 'targets': targets, 'expected': digest(target_states(conn, targets))}, oid)
        data_actions.finish(conn, 'course_graph_learning_links', resource, confirmation_token, receipt)
        return receipt
