"""Reviewed cross-course navigation without transferring learning evidence."""

from uuid import NAMESPACE_URL, uuid4, uuid5

from filemate.course_graph.fusion import _check_preview, _used_receipt
from filemate.course_graph.learning_commands import target_states
from filemate.course_graph.models import CourseGraphError, digest, now_iso, request_key_valid
from filemate.course_graph.question_links import _concept
from filemate.course_graph.repository import get_request, record_change, require_course, transaction
from filemate.course_graph.workspace_models import validate_page
from filemate.course_graph.workspace_snapshot import read_workspace_snapshot
from filemate.execution import data_actions


def _context(storage, conn, cid, nid, other_course_id, other_concept_id, active, relation):
    if type(active) is not bool or relation != 'related' or cid == other_course_id:
        raise CourseGraphError('invalid_cross_course_link', 422)
    first = read_workspace_snapshot(storage, cid)
    second = read_workspace_snapshot(storage, other_course_id)
    _concept(first, nid)
    _concept(second, other_concept_id)
    pair = sorted([(cid, nid), (other_course_id, other_concept_id)])
    lid = uuid5(NAMESPACE_URL, 'course-related:' + digest(pair)).hex
    row = conn.execute('SELECT * FROM kg_cross_links WHERE link_id=?', (lid,)).fetchone()
    selection = digest({'pair': pair, 'active': active, 'relation': relation})
    revision = digest({'selection': selection, 'graphs': sorted([first.graph_digest, second.graph_digest]),
                       'row': dict(row) if row else None})
    return lid, pair, row, selection, revision


def preview_cross_link(storage, cid: str, nid: str, other_course_id: str, other_concept_id: str,
                       active: bool = True, relation: str = 'related') -> dict:
    """Check both tenant-owned endpoints before issuing a version-bound preview."""
    with transaction(storage) as conn:
        lid, _, row, _, revision = _context(storage, conn, cid, nid, other_course_id, other_concept_id, active, relation)
        return {'confirmation_token': data_actions.issue(conn, 'course_graph_learning_cross', lid, revision),
                'link_id': lid, 'active': active, 'relation': relation, 'affects_learning': False,
                'changed_count': int(bool(row and row['active']) != active)}


def confirm_cross_link(storage, cid: str, nid: str, other_course_id: str, other_concept_id: str,
                       active: bool, relation: str, confirmation_token: str, request_key: str,
                       confirmed: bool) -> dict:
    """Persist one canonical pair; inverse commands retain original concept identities."""
    request_key_valid(request_key)
    if confirmed is not True:
        raise CourseGraphError('confirmation_required', 422)
    with transaction(storage) as conn:
        require_course(conn, cid)
        # Validate the target even on retries so receipts never reveal another tenant.
        lid, pair, row, selection, revision = _context(
            storage, conn, cid, nid, other_course_id, other_concept_id, active, relation)
        command = digest({'selection': selection, 'token': confirmation_token})
        previous = get_request(conn, cid, request_key, 'learning_cross', command)
        if previous:
            return previous['metadata']['receipt']
        used = _used_receipt(conn, 'course_graph_learning_cross', lid, confirmation_token)
        if used:
            if used['selection_digest'] != selection:
                raise CourseGraphError('request_key_conflict')
            record_change(conn, cid, request_key, 'learning_cross', command,
                          {'receipt': used, 'alias_of': used['operation_id']})
            return used
        _check_preview(conn, 'course_graph_learning_cross', lid, confirmation_token, revision)
        before, targets = int(bool(row and row['active'])), []
        if before != int(active):
            conn.execute('''INSERT INTO kg_cross_links(link_id,from_course_id,from_concept_id,
                to_course_id,to_concept_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(link_id) DO UPDATE SET active=excluded.active,
                revision=kg_cross_links.revision+1,updated_at=excluded.updated_at''',
                (lid, *pair[0], *pair[1], int(active), now_iso(), now_iso()))
            targets = [{'table': 'kg_cross_links', 'id': lid, 'before': before, 'after': int(active)}]
        oid = str(uuid4())
        receipt = {'operation_id': oid, 'link_id': lid, 'selection_digest': selection,
                   'affected': {'learning_links': len(targets)}, 'affects_learning': False}
        record_change(conn, cid, request_key, 'learning_cross', command,
                      {'receipt': receipt, 'targets': targets, 'expected': digest(target_states(conn, targets))}, oid)
        data_actions.finish(conn, 'course_graph_learning_cross', lid, confirmation_token, receipt)
        return receipt


def list_cross_links(storage, cid: str, nid: str, *, offset: int = 0, limit: int = 50) -> dict:
    """Page manual relations independently of prerequisites, questions and statistics."""
    validate_page(limit, offset)
    with storage.read_snapshot() as read:
        snapshot = read_workspace_snapshot(read, cid)
        root = _concept(snapshot, nid)
        members = {m for m, r in snapshot.member_to_root.items() if r == root}
        rows = read._conn().execute('''SELECT * FROM kg_cross_links WHERE active=1
            AND (from_course_id=? OR to_course_id=?) ORDER BY link_id''', (cid, cid))
        selected = []
        for row in rows:
            side = 'from' if row['from_course_id'] == cid else 'to'
            if row[side + '_concept_id'] in members:
                selected.append(dict(row))
        items = []
        for row in selected[offset:offset + limit]:
            side = 'to' if row['from_course_id'] == cid else 'from'
            target_cid, target_nid = row[side + '_course_id'], row[side + '_concept_id']
            target = read._conn().execute('''SELECT c.name,n.label FROM kg_courses c
                JOIN kg_concepts n ON n.course_id=c.course_id WHERE c.course_id=? AND n.concept_id=?''',
                                         (target_cid, target_nid)).fetchone()
            items.append({'link_id': row['link_id'], 'course_id': target_cid, 'concept_id': target_nid,
                          'course_name': target['name'], 'label': target['label'], 'relation': 'related',
                          'affects_learning': False,
                          'route': f'/knowledge-graph?graph_scope=course&course={target_cid}&node={target_nid}'})
        return {'course_id': cid, 'concept_id': root, 'items': items, 'total': len(selected),
                'limit': limit, 'offset': offset}
