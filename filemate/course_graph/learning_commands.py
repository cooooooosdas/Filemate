"""Revision-bound inverse operations for explicit learning changes."""

import json
from typing import Any
from uuid import uuid4

from filemate.course_graph.fusion import _check_preview, _used_receipt
from filemate.course_graph.models import CourseGraphError, digest, now_iso, request_key_valid
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.execution import data_actions

LINK_TABLES = frozenset({'kg_question_links', 'kg_cross_links'})


def target_states(conn, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve whitelisted identities without copying learning content into logs."""
    result = []
    for target in targets:
        table = target['table']
        if table not in LINK_TABLES:
            raise CourseGraphError('unsupported_learning_operation')
        row = conn.execute(f'SELECT link_id,active,revision FROM {table} WHERE link_id=?',
                           (target['id'],)).fetchone()
        result.append(dict(row) if row else {'link_id': target['id'], 'missing': True})
    return result


def _operation(conn, cid, oid, action):
    require_course(conn, cid)
    if action not in {'undo', 'restore'}:
        raise CourseGraphError('invalid_action', 422)
    row = conn.execute("SELECT * FROM kg_changes WHERE course_id=? AND operation_id=?",
                       (cid, oid)).fetchone()
    if row is None or not row['kind'].startswith('learning_'):
        raise CourseGraphError('operation_not_found', 404)
    metadata = json.loads(row['metadata'])
    if 'targets' not in metadata:
        raise CourseGraphError('unsupported_learning_operation')
    desired = 'undone' if action == 'undo' else 'applied'
    states = target_states(conn, metadata['targets'])
    if digest(states) != metadata['expected']:
        raise CourseGraphError('operation_conflict')
    revision = digest({'operation_id': oid, 'status': row['status'], 'expected': metadata['expected'], 'action': action})
    return row, metadata, desired, revision


def preview_learning_transition(storage, cid: str, operation_id: str, action: str) -> dict[str, Any]:
    """Preview one inverse without changing plans, attempts or other operations."""
    with transaction(storage) as conn:
        row, metadata, desired, revision = _operation(conn, cid, operation_id, action)
        resource = f'{cid}:{operation_id}:{action}'
        token = data_actions.issue(conn, 'course_graph_learning_transition', resource, revision)
        return {'operation_id': operation_id, 'status': row['status'], 'target_status': desired,
                'affected_count': len(metadata['targets']), 'confirmation_token': token}


def transition_learning_operation(storage, cid: str, operation_id: str, action: str,
                                  confirmation_token: str, request_key: str, confirmed: bool) -> dict[str, Any]:
    """Apply an idempotent, checked inverse while preserving learning history."""
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError('confirmation_required', 422)
    hashed = digest({'operation_id': operation_id, 'action': action, 'token': confirmation_token})
    resource = f'{cid}:{operation_id}:{action}'
    kind = 'learning_transition'
    with transaction(storage) as conn:
        require_course(conn, cid)
        previous = get_request(conn, cid, request_key, kind, hashed)
        if previous:
            return previous['metadata']['receipt']
        used = _used_receipt(conn, 'course_graph_learning_transition', resource, confirmation_token)
        if used:
            record_change(conn, cid, request_key, kind, hashed, {'receipt': used, 'alias_of': used['operation_id']})
            return used
        row, metadata, desired, revision = _operation(conn, cid, operation_id, action)
        _check_preview(conn, 'course_graph_learning_transition', resource, confirmation_token, revision)
        if row['status'] != desired:
            value = 'before' if action == 'undo' else 'after'
            for target in metadata['targets']:
                conn.execute(f"UPDATE {target['table']} SET active=?,revision=revision+1,updated_at=? WHERE link_id=?",
                             (target[value], now_iso(), target['id']))
            metadata['expected'] = digest(target_states(conn, metadata['targets']))
            conn.execute('UPDATE kg_changes SET status=?,metadata=?,updated_at=? WHERE operation_id=?',
                         (desired, json.dumps(metadata, ensure_ascii=False), now_iso(), operation_id))
        oid = str(uuid4())
        receipt = {'operation_id': oid, 'target_operation_id': operation_id, 'status': desired,
                   'affected': {'learning_links': len(metadata['targets']) if row['status'] != desired else 0}}
        record_change(conn, cid, request_key, kind, hashed, {'receipt': receipt}, oid)
        data_actions.finish(conn, 'course_graph_learning_transition', resource, confirmation_token, receipt)
        return receipt
