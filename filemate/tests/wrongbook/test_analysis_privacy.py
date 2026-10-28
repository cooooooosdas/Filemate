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
