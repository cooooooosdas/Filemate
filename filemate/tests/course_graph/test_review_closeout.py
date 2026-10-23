# ruff: noqa: F811
"""Synthetic reproductions from the single independent D/E closeout review."""

import importlib
import json
from uuid import uuid4

import pytest

from filemate.course_graph.assistant import GraphAssistant
from filemate.course_graph.models import CourseGraphError
from filemate.course_graph.repository import CourseGraphRepository
from filemate.execution.storage import SQLiteStorage
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.course_graph.test_learning_api import cross_context
from filemate.tests.course_graph.test_learning_evidence import NOW
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401


@pytest.fixture(autouse=True)
def enable_assistant(monkeypatch):
    monkeypatch.setenv('FILEMATE_ENABLE_GRAPH_ASSISTANT', '1')


@pytest.mark.parametrize('method', ['upgrade', 'restore'])
def test_upgrade_backfills_legacy_answer_dependencies(learning_context, tmp_path, method):
    store, cid, sid, nid, *_ = learning_context
    svc = GraphAssistant(store, lambda: None, lambda: NOW)
    work = svc.answer(cid, '解释栈', [nid], None, None, 'rule', uuid4().hex)
    with store._conn() as conn:
        conn.execute('DELETE FROM kg_learning_work_sources WHERE work_id=?', (work['work_id'],))
        conn.execute('DELETE FROM schema_migrations WHERE version=34')
    if method == 'upgrade':
        store.init_schema()
        assert store.get_schema_version() == 34
    else:
        backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
        preview = backup.preview(backup.export())
        backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert store.source_deletion_preview(sid)['affected']['course_learning_work'] == 1
    store.delete_source(sid)
    with pytest.raises(CourseGraphError, match='learning_work_not_found'):
        svc.work.get(cid, work['work_id'])


@pytest.mark.parametrize('inactive', [False, True])
def test_unquoted_and_inactive_source_purge_removes_saved_context(learning_context, inactive):
    store, cid, *_ = learning_context
    repo = CourseGraphRepository(store)
    public_text = '|'.join(f'A{i:02d}' for i in range(12))
    public = store.save_source(original_name='public', source_path='public', raw_text=public_text)
    secret_text = 'Z_PRIVATE_SECOND_SOURCE'
    secret = store.save_source(original_name='secret', source_path='secret', raw_text=secret_text)
    repo.attach_sources(cid, [public, secret], None, repo.get_course(cid)['revision'])
    with store._conn() as conn:
        for i, label in enumerate([f'A{i:02d}' for i in range(12)] + [secret_text]):
            sid = public if i < 12 else secret
            start = public_text.index(label) if i < 12 else 0
            conn.execute('INSERT INTO kg_concepts(concept_id,course_id,label) VALUES(?,?,?)', (f'review-{i}', cid, label))
            conn.execute('''INSERT INTO kg_evidence(evidence_id,course_id,source_id,source_revision,
                concept_id,excerpt,char_start,char_end) VALUES(?,?,?,?,?,?,?,?)''',
                (f'review-ref-{i}', cid, sid, store.get_source_revision(sid), f'review-{i}', label, start, start + len(label)))
        if inactive:
            conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, secret))
    svc = GraphAssistant(store, lambda: None, lambda: NOW)
    work = svc.answer(cid, '学习概念', None, None, None, 'rule', uuid4().hex)
    assert work['status'] == 'ready'
    assert secret_text in json.dumps(work['payload'])
    assert secret not in {q['source_id'] for q in work['payload']['textbook_evidence']}
    store.delete_source(secret)
    with pytest.raises(CourseGraphError, match='learning_work_not_found'):
        svc.work.get(cid, work['work_id'])


@pytest.mark.parametrize('text', ['You answered 100 questions correctly; mastery is 100%.',
                                '你已答对一百题，掌握率百分之百。', '训练统计：累计完成100道题。',
                                '你非常熟悉栈的操作。', 'Your understanding is excellent.'])
def test_valid_citation_cannot_authorize_model_personal_statistics(learning_context, text):
    class Provider:
        def call_structured(self, **kwargs):
            context = json.loads(kwargs['messages'][0]['content'])['context']
            return {'explanation': text, 'citation_ids': [context['textbook_evidence'][0]['evidence_id']],
                    'personal_fact_ids': [], 'suggestions': []}
    store, cid, _, nid, *_ = learning_context
    work = GraphAssistant(store, lambda: Provider(), lambda: NOW).answer(
        cid, '解释栈', [nid], None, None, 'llm', uuid4().hex, True)
    assert work['status'] == 'failed' and work['error_code'] == 'invalid_output'
    assert work['payload'] == {}


@pytest.mark.parametrize('state', ['revoked', 'archived'])
def test_unavailable_cross_course_target_is_labelled_and_can_be_unlinked(learning_context, state):
    module = importlib.import_module('filemate.course_graph.cross_links')
    store, cid, nid, other, target = cross_context(learning_context)
    preview = module.preview_cross_link(store, cid, nid, other, target)
    module.confirm_cross_link(store, cid, nid, other, target, True, 'related', preview['confirmation_token'], uuid4().hex, True)
    with store._conn() as conn:
        if state == 'revoked':
            conn.execute("UPDATE kg_concepts SET status='revoked' WHERE concept_id=?", (target,))
        else:
            conn.execute('UPDATE kg_courses SET archived=1 WHERE course_id=?', (other,))
    item = module.list_cross_links(store, cid, nid)['items'][0]
    assert item['available'] is False and item['unavailable_reason'] and item['route'] is None
    preview = module.preview_cross_link(store, cid, nid, other, target, active=False)
    module.confirm_cross_link(store, cid, nid, other, target, False, 'related', preview['confirmation_token'], uuid4().hex, True)
    assert module.list_cross_links(store, cid, nid)['total'] == 0
    with pytest.raises(CourseGraphError):
        module.preview_cross_link(store, cid, nid, other, target, active=True)


def test_unrelated_attempts_do_not_drive_course_query_work(learning_context):
    module = importlib.import_module('filemate.course_graph.learning_evidence')
    store, cid, sid, nid, *_ = learning_context
    confirm(learning_context)
    with store._conn() as conn:
        conn.executemany('''INSERT INTO kg_question_links(link_id,course_id,concept_id,artifact_id,
            question_index,question_digest,source_id,created_at,updated_at) SELECT ?,course_id,concept_id,artifact_id,?,
            question_digest,source_id,created_at,updated_at FROM kg_question_links LIMIT 1''', [(f'load-link-{i}', i + 1) for i in range(1000)])
    def measured(expected=0):
        ticks = [0]
        with store.read_snapshot() as read:
            def tick():
                ticks[0] += 1
                return 0
            read._conn().set_progress_handler(tick, 1000)
            result = module.read_learning_projection(read, cid, now=NOW)
        assert result['nodes'][nid]['counts']['attempts'] == expected
        return ticks[0]
    baseline = measured()
    unrelated = store.save_artifact(artifact_type='questions', source_id=sid, content=[])
    with store._conn() as conn:
        conn.executemany('''INSERT INTO quiz_attempts(attempt_id,artifact_id,question_index,user_answer,is_correct,score)
            VALUES(?,?,0,'private unrelated answer',1,1)''', [(f'unrelated-{i}', unrelated) for i in range(10000)])
    assert measured() <= baseline + 100
    with store._conn() as conn:
        aid = learning_context[4]
        conn.executemany('''INSERT INTO quiz_attempts(attempt_id,artifact_id,question_index,user_answer,
            is_correct,score,created_at) VALUES(?,?,0,'synthetic',1,1,?)''',
            [(f'relevant-{i}', aid, NOW.isoformat()) for i in range(10000)])
    # Multiple mappings in one Artifact must not rescan its attempt range per question.
    assert measured(expected=10000) <= baseline + 3000


@pytest.mark.parametrize('action', ['preview', 'confirm'])
def test_path_build_does_not_block_another_writer(learning_context, monkeypatch, action):
    module = importlib.import_module('filemate.course_graph.learning_paths')
    store, cid, *_ = learning_context
    options = {'goal': '合成复习', 'concept_ids': [learning_context[3]]}
    token = module.preview_path(store, cid, options, now=NOW)['confirmation_token']
    original = module._build
    other = SQLiteStorage(store.db_path)
    other._conn().execute('PRAGMA busy_timeout=30')
    def build(*args, **kwargs):
        with other._conn() as conn:
            conn.execute("UPDATE kg_courses SET name=name || ' changed' WHERE course_id=?", (cid,))
        return original(*args, **kwargs)
    monkeypatch.setattr(module, '_build', build)
    try:
        # A concurrent commit must invalidate the optimistic read, not publish a stale token/plan.
        with pytest.raises(CourseGraphError, match='input_changed'):
            if action == 'preview':
                module.preview_path(store, cid, options, now=NOW)
            else:
                module.confirm_path(store, cid, options, token, uuid4().hex, True, now=NOW)
        assert store.list_study_plans() == []
    finally:
        other.close()


def test_confirmed_path_alias_retry_reads_receipt_after_scope_changes(learning_context):
    module = importlib.import_module('filemate.course_graph.learning_paths')
    store, cid, sid, nid, *_ = learning_context
    options = {'goal': '保留回执', 'concept_ids': [nid]}
    token = module.preview_path(store, cid, options, now=NOW)['confirmation_token']
    receipt = module.confirm_path(store, cid, options, token, uuid4().hex, True, now=NOW)
    with store._conn() as conn:
        conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, sid))
    assert module.confirm_path(store, cid, options, token, uuid4().hex, True, now=NOW) == receipt
    assert len(store.list_study_plans()) == 1
