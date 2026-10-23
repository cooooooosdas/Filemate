"""Synthetic course question mapping, migration and deletion contracts."""

import importlib
import json
from uuid import uuid4

import pytest

from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.privacy import normalize_restored_course_graph
from filemate.execution import storage as storage_module
from filemate.execution.storage import SQLiteStorage
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.course_graph.test_review import accept_nodes, draft, publish


def links():
    return importlib.import_module('filemate.course_graph.question_links')


@pytest.fixture
def learning_context(course_context):
    store, _, cid, sid = course_context
    publish(course_context, accept_nodes(course_context, draft(course_context), True))
    nid = store._conn().execute("SELECT concept_id FROM kg_concepts WHERE label='栈'").fetchone()[0]
    question = {'question_type': 'fill', 'stem': '栈的出入顺序是____。', 'answer': '后进先出',
                'analysis': '依课程原文。', 'knowledge_point': '栈'}
    aid = store.save_artifact(artifact_type='questions', source_id=sid, content=[question])
    return store, cid, sid, nid, aid, question


def selection(context):
    store, cid, _, nid, *_ = context
    row = links().question_candidates(store, cid, nid)['items'][0]
    return [{key: row[key] for key in ('artifact_id', 'question_index', 'question_digest')}]


def confirm(context, items=None, *, active=True, key='learning_link_00001', token=None):
    store, cid, _, nid, *_ = context
    items = selection(context) if items is None else items
    preview = links().preview_question_links(store, cid, nid, items, active)
    return links().confirm_question_links(store, cid, nid, items, active,
        token or preview['confirmation_token'], key, True)


def test_schema_31_upgrade_preserves_old_rows(tmp_path, monkeypatch):
    migrations = storage_module._MIGRATIONS
    monkeypatch.setattr(storage_module, '_MIGRATIONS', tuple(m for m in migrations if m[0] <= 31))
    store = SQLiteStorage(tmp_path / 'old.sqlite')
    store.init_schema()
    sid = store.save_source(original_name='old.txt', source_path='old.txt', raw_text='原有资料')
    aid = store.save_artifact(artifact_type='notes', source_id=sid, content='旧笔记')
    before = store.get_source(sid), store.get_artifact(aid)
    monkeypatch.setattr(storage_module, '_MIGRATIONS', migrations)
    store.init_schema()
    assert store.get_schema_version() == 34
    assert (store.get_source(sid), store.get_artifact(aid)) == before
    tables = {r[0] for r in store._conn().execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'kg_question_links', 'kg_cross_links', 'kg_course_plan_links',
            'kg_learning_work', 'kg_learning_work_sources'} <= tables
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
    assert store._conn().execute('PRAGMA foreign_key_list(kg_question_links)').fetchall()
    store.close()


def test_candidates_do_not_link_by_matching_word(learning_context):
    store, cid, _, nid, *_ = learning_context
    page = links().question_candidates(store, cid, nid)
    assert page['total'] == 1 and page['items'][0]['linked'] is False
    assert store._conn().execute('SELECT COUNT(*) FROM kg_question_links').fetchone()[0] == 0


def test_link_requires_preview_and_current_question(learning_context):
    store, cid, _, nid, aid, question = learning_context
    items = selection(learning_context)
    with pytest.raises(CourseGraphError) as missing:
        links().confirm_question_links(store, cid, nid, items, True, '', 'learning_link_00001', False)
    assert missing.value.status_code == 422
    preview = links().preview_question_links(store, cid, nid, items)
    store.update_artifact(aid, title='修订', content=[{**question, 'answer': '新参考答案'}])
    with pytest.raises(CourseGraphError, match='question_changed'):
        links().confirm_question_links(store, cid, nid, items, True,
            preview['confirmation_token'], 'learning_link_00002', True)
    assert store._conn().execute('SELECT COUNT(*) FROM kg_question_links').fetchone()[0] == 0


def test_duplicate_confirmation_is_single_receipt(learning_context):
    store, cid, _, nid, *_ = learning_context
    items = selection(learning_context)
    token = links().preview_question_links(store, cid, nid, items)['confirmation_token']
    first = links().confirm_question_links(store, cid, nid, items, True, token, 'learning_link_00001', True)
    second = links().confirm_question_links(store, cid, nid, items, True, token, 'learning_link_00001', True)
    alias = links().confirm_question_links(store, cid, nid, items, True, token, 'learning_link_00002', True)
    assert first == second == alias
    assert store._conn().execute('SELECT COUNT(*) FROM kg_question_links WHERE active=1').fetchone()[0] == 1
    assert store._conn().execute("SELECT COUNT(*) FROM data_action_audit WHERE action='course_graph_learning_links'").fetchone()[0] == 1
    assert '栈的出入顺序' not in ''.join(r[0] for r in store._conn().execute('SELECT metadata FROM kg_changes'))
    with pytest.raises(CourseGraphError, match='request_key_conflict'):
        links().confirm_question_links(store, cid, nid, items, False, token, 'learning_link_00003', True)


def test_foreign_course_and_artifact_refused(learning_context):
    store, cid, _, nid, *_ = learning_context
    foreign = store.save_source(original_name='other.txt', source_path='other.txt', raw_text='不属于这门课')
    aid = store.save_artifact(artifact_type='questions', source_id=foreign,
        content=[{'question_type': 'fill', 'stem': '栈____', 'answer': '其他'}])
    with pytest.raises(CourseGraphError, match='question_not_in_course'):
        links().preview_question_links(store, cid, nid,
            [{'artifact_id': aid, 'question_index': 0, 'question_digest': 'a' * 64}])
    with pytest.raises(CourseGraphError, match='course_not_found'):
        links().question_candidates(store, 'foreign-course', nid)


def test_unlink_undo_preserves_attempts(learning_context):
    store, cid, _, _, aid, *_ = learning_context
    confirm(learning_context)
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer='不会',
        is_correct=False, score=0, feedback='复习')
    removed = confirm(learning_context, active=False, key='learning_unlink_001')
    commands = importlib.import_module('filemate.course_graph.learning_commands')
    preview = commands.preview_learning_transition(store, cid, removed['operation_id'], 'undo')
    receipt = commands.transition_learning_operation(store, cid, removed['operation_id'], 'undo',
        preview['confirmation_token'], 'learning_undo_0001', True)
    assert receipt['status'] == 'undone'
    assert store._conn().execute('SELECT active FROM kg_question_links').fetchone()[0] == 1
    assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_questions').fetchone()[0] == 1


def test_modified_link_rejects_older_inverse(learning_context):
    store, cid, *_ = learning_context
    first = confirm(learning_context)
    confirm(learning_context, active=False, key='learning_unlink_001')
    commands = importlib.import_module('filemate.course_graph.learning_commands')
    with pytest.raises(CourseGraphError, match='operation_conflict'):
        commands.preview_learning_transition(store, cid, first['operation_id'], 'undo')


def seed_work(store, cid, source_ids, *, status='ready'):
    wid = str(uuid4())
    with store._conn() as conn:
        conn.execute('''INSERT INTO kg_learning_work(work_id,course_id,kind,request_key,input_digest,
            graph_digest,evidence_digest,status,epoch,payload,created_at,updated_at)
            VALUES(?,?,'answer',?,'input','graph','evidence',?,7,?,'2026-10-23','2026-10-23')''',
            (wid, cid, uuid4().hex, status, json.dumps({'answer': '第二来源私有片段'})))
        conn.executemany('INSERT INTO kg_learning_work_sources VALUES(?,?)', [(wid, sid) for sid in source_ids])
    return wid


def test_delete_any_work_source_removes_answer_and_preview_tracks_changes(learning_context):
    store, cid, sid, *_ = learning_context
    second = store.save_source(original_name='second.txt', source_path='second.txt', raw_text='第二来源私有片段')
    before = store._source_deletion_revision(second)
    wid = seed_work(store, cid, [sid, second])
    assert store._source_deletion_revision(second) != before
    impact = store.source_deletion_preview(second)
    assert impact['affected']['course_learning_work'] == 1
    store.delete_source(second)
    assert store._conn().execute('SELECT * FROM kg_learning_work WHERE work_id=?', (wid,)).fetchone() is None
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_restore_interrupts_work_and_invalidates_preview(learning_context):
    store, cid, sid, *_ = learning_context
    wid = seed_work(store, cid, [sid], status='running')
    from filemate.execution import data_actions
    with store._conn() as conn:
        data_actions.issue(conn, 'course_graph_learning_links', cid, 'revision')
        normalize_restored_course_graph(conn)
    row = dict(store._conn().execute('SELECT * FROM kg_learning_work WHERE work_id=?', (wid,)).fetchone())
    assert row['status'] == 'interrupted' and row['epoch'] != 7
    assert row['error_code'] == 'backup_restored' and row['lease_until'] is None
    assert store._conn().execute('SELECT COUNT(*) FROM data_action_previews').fetchone()[0] == 0


def test_personal_backup_restores_nonempty_learning_tables(learning_context, tmp_path):
    store, cid, sid, *_ = learning_context
    confirm(learning_context)
    wid = seed_work(store, cid, [sid], status='running')
    before = tuple(store._conn().execute('SELECT * FROM kg_question_links').fetchone())
    backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
    raw = backup.export()
    confirm(learning_context, active=False, key='learning_unlink_001')
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert tuple(store._conn().execute('SELECT * FROM kg_question_links').fetchone()) == before
    work = dict(store._conn().execute('SELECT * FROM kg_learning_work WHERE work_id=?', (wid,)).fetchone())
    assert work['status'] == 'interrupted' and work['epoch'] != 7
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_removed_source_cannot_create_new_mapping(learning_context):
    store, cid, sid, nid, *_ = learning_context
    items = selection(learning_context)
    with store._conn() as conn:
        conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, sid))
    assert links().question_candidates(store, cid, nid)['total'] == 0
    with pytest.raises(CourseGraphError, match='question_not_in_course'):
        links().preview_question_links(store, cid, nid, items)


@pytest.mark.parametrize('items', [[], [{}] * 21, [{'artifact_id': 'a', 'question_index': True, 'question_digest': 'a' * 64}]])
def test_mapping_selection_is_bounded_and_strict(learning_context, items):
    store, cid, _, nid, *_ = learning_context
    with pytest.raises(CourseGraphError) as error:
        links().preview_question_links(store, cid, nid, items)
    assert error.value.status_code == 422
