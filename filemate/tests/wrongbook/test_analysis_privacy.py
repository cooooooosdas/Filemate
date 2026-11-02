"""Conservative source erasure and append-only migration safety."""
# ruff: noqa: F811

import sqlite3

import pytest

from filemate.execution import storage as storage_module
from filemate.execution.storage import SQLiteStorage
from filemate.tests.wrongbook.test_analysis_repository import (  # noqa: F401
    analysis_case,
    repository,
)


def test_source_preview_counts_analysis_cascaded_from_multisource_questions(analysis_case):
    store, clock, context = analysis_case
    other = store.save_source(original_name='合成第二来源', source_path='synthetic-second.txt')
    with store._conn() as conn:
        conn.execute('INSERT INTO kg_learning_artifact_sources VALUES(?,?)',
            (context['ref']['artifact_id'], other))
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-transitive-delete-0001')
    assert repo.finish(view['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {})
    before = store.preview_source_deletion(other)['affected']
    assert before['wrong_review_analyses'] == 1
    assert before['artifacts'] == 2
    store.delete_source(other)
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_review_analyses').fetchone()[0] == 0


@pytest.mark.parametrize('operation', ['plan', 'adopt', 'undo'])
def test_learning_previews_never_persist_copies_of_private_text(analysis_case, operation):
    from filemate.tests.wrongbook.test_analysis_adoption import commands, supported
    from filemate.tests.wrongbook.test_learning_plans import selection

    store, clock, context = analysis_case
    api, wid = commands(store, clock), context['ref']['wrong_id']
    marker = 'PRIVATE_SOURCE_SENTENCE'
    if operation == 'plan':
        body = selection(api, context)
        body['tasks'][0]['instructions'] = marker
        preview = api.preview_plan(wid, body)
        api.confirm_plan(wid, body, preview['confirmation_token'], 'synthetic-private-plan-0001', True)
    else:
        aid, revision = supported(analysis_case)
        with store._conn() as conn:
            conn.execute('UPDATE wrong_questions SET error_cause_note=? WHERE wrong_id=?', (marker, wid))
        body = {'selected_causes': ['concept_gap'], 'expected_revision': revision}
        # 支持函数已绑定原备注，修改备注后需建立当前分析。
        from filemate.wrongbook.learning_context import ReviewLearningContext
        current = ReviewLearningContext(store, lambda: clock[0]).build(wid, context['attempt']['attempt_id'])
        repo = repository(store, clock)
        view, _, epoch = repo.claim(current, 'synthetic-private-analysis-0001')
        assert repo.finish(view['analysis_id'], epoch, {'kind': 'supported_hypotheses',
            'possible_causes': [{'cause_code': 'concept_gap', 'hypothesis': '候选原因'}]}, {})
        aid = view['analysis_id']
        preview = api.preview_adoption(wid, aid, body)
        if operation == 'undo':
            receipt = api.confirm_adoption(wid, aid, body, preview['confirmation_token'], 'synthetic-private-adopt-0001', True)
            api.preview_undo(wid, receipt['review_event_id'])
    rows = store._conn().execute("SELECT revision,result FROM data_action_previews WHERE action LIKE 'review_learning_%'").fetchall()
    assert rows and all(marker not in str(tuple(row)) for row in rows)
    store.delete_source(context['_source_dependencies'][0]['source_id'])
    assert all(marker not in row[0] for row in store._conn().execute('SELECT revision FROM data_action_previews'))


def test_history_detail_uses_its_own_bounded_source_quotes(analysis_case):
    store, clock, context = analysis_case
    repo = repository(store, clock)
    context['source_evidence'] = [{'evidence_id': 'original', 'source_id': context['_source_dependencies'][0]['source_id'],
        'quote': '当时实际发送的合成原文', 'start': 0, 'end': 11}]
    view, _, epoch = repo.claim(context, 'synthetic-history-quotes-0001')
    assert repo.finish(view['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {})
    detail = repo.get(context['ref']['wrong_id'], view['analysis_id'])
    assert detail['source_evidence'] == context['source_evidence']
    assert 'source_evidence' not in repo.page(context['ref']['wrong_id'])['items'][0]


def test_delete_every_input_source_purges_snapshot_and_artifact(analysis_case):
    store, clock, context = analysis_case
    other = store.save_source(original_name='仅贡献标签的合成资料', source_path='synthetic-other.txt')
    # 在仓储边界注入第二个真实来源依赖，验证清理不依赖最终模型引用。
    context['_source_dependencies'].append({'source_id': other,
        'source_revision': store.get_source_revision(other), 'membership_revision': None})
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-delete-key-0001')
    assert repo.finish(view['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {})
    before = store.preview_source_deletion(other)
    assert before['affected']['wrong_review_analyses'] == 1
    assert before['affected']['artifacts'] == 1
    result_id = repo.get(context['ref']['wrong_id'], view['analysis_id'])['result_artifact_id']
    store.delete_source(other)
    assert store.get_artifact(result_id) is None
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_review_analyses').fetchone()[0] == 0
    with pytest.raises(LookupError, match='deleted'):
        repo.find_request('synthetic-delete-key-0001')
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []


def test_delete_wrong_or_attempt_cannot_leave_orphan_analysis_body(analysis_case):
    store, clock, context = analysis_case
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-cascade-key-0001')
    assert repo.finish(view['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {})
    with store._conn() as conn:
        conn.execute('DELETE FROM quiz_attempts WHERE attempt_id=?', (context['attempt']['attempt_id'],))
    assert store._conn().execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='wrong_review_analysis'").fetchone()[0] == 0
    with pytest.raises(LookupError):
        repo.find_request('synthetic-cascade-key-0001')


def test_upgrade35_preserves_nullable_attempts_and_rolls_back_failure(tmp_path, monkeypatch):
    store = SQLiteStorage(tmp_path/'upgrade35.db')
    old = tuple(m for m in storage_module._MIGRATIONS if m[0] <= 35)
    with monkeypatch.context() as patch:
        patch.setattr(storage_module, '_MIGRATIONS', old)
        store.init_schema()
    sid = store.save_source(original_name='合成', source_path='synthetic.txt')
    aid = store.save_artifact(source_id=sid, artifact_type='questions', content=[])
    with store._conn() as conn:
        conn.execute("INSERT INTO quiz_attempts(rowid,attempt_id,artifact_id,question_index,user_answer,is_correct,score) VALUES(57,'old',?,0,'保留',NULL,NULL)", (aid,))
    assert storage_module._MIGRATIONS[-1][0] == 36
    version, name, sql = storage_module._MIGRATIONS[-1]
    with monkeypatch.context() as patch:
        patch.setattr(storage_module, '_MIGRATIONS', (*old, (version, name, sql+'\nINVALID SQL;')))
        with pytest.raises(sqlite3.Error):
            store.init_schema()
    assert store.get_schema_version() == 35
    assert store._conn().execute("SELECT name FROM sqlite_master WHERE name='wrong_review_analyses'").fetchone() is None
    store.init_schema()
    assert store.get_schema_version() == 36
    assert store._conn().execute('SELECT rowid,is_correct,score FROM quiz_attempts').fetchone()[:] == (57, None, None)
    assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
    assert store._conn().execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    store.close()


def test_personal_restore_keeps_governance_admissions_and_never_resumes_claim(analysis_case):
    from filemate.operations.personal_backup import PersonalBackup
    from filemate.runtime_governance import default_scope

    store, clock, context = analysis_case
    inbox, archive = store.db_path.parent/'inbox', store.db_path.parent/'archive'
    inbox.mkdir()
    source_file = inbox/'original.txt'
    source_file.write_text('原创合成', encoding='utf-8')
    with store._conn() as conn:
        conn.execute('UPDATE sources SET source_path=?', (str(source_file),))
    repo = repository(store, clock)
    view, _, epoch = repo.claim(context, 'synthetic-restore-key-0001')
    backup = PersonalBackup(store, 'local', inbox, archive)
    raw = backup.export()
    preview = backup.preview(raw)
    scope = default_scope()
    with scope.store._connection() as conn:
        before = conn.execute('SELECT COUNT(*) FROM learning_admissions').fetchone()[0]
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    assert repo.get(context['ref']['wrong_id'], view['analysis_id'])['status'] == 'interrupted'
    assert not repo.finish(view['analysis_id'], epoch, {'kind': 'insufficient_evidence'}, {})
    with scope.store._connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM learning_admissions').fetchone()[0] == before


def test_restore_older_than_claim_does_not_refund_or_recall_model(analysis_case):
    from filemate.operations.personal_backup import PersonalBackup

    store, clock, context = analysis_case
    inbox, archive = store.db_path.parent/'inbox', store.db_path.parent/'archive'
    inbox.mkdir()
    (inbox/'synthetic.txt').write_text('合成资料', encoding='utf-8')
    with store._conn() as conn:
        conn.execute('UPDATE sources SET source_path=?', (str(inbox/'synthetic.txt'),))
    backup = PersonalBackup(store, 'local', inbox, archive)
    raw = backup.export()
    repo = repository(store, clock)
    repo.claim(context, 'synthetic-before-restore-0001')
    preview = backup.preview(raw)
    backup.restore(preview['backup_id'], preview['confirmation_token'])
    with pytest.raises(LookupError, match='deleted_or_restored'):
        repo.claim(context, 'synthetic-before-restore-0001')
