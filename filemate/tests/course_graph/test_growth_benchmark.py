"""Synthetic benchmark fixtures never target or overwrite an existing learning space."""

import importlib
from pathlib import Path

import pytest

from filemate.execution.storage import SQLiteStorage


def test_growth_fixture_is_exact_and_non_destructive(tmp_path):
    module = importlib.import_module('scripts.acceptance.course_growth_benchmark')
    root = tmp_path / 'new-benchmark'
    result = module.prepare_growth(root, [10, 100], attempts=10000)
    assert result['synthetic'] is True
    assert result['dense_attempts'] == 10000
    for case in result['cases']:
        store = SQLiteStorage(Path(case['database']))
        try:
            assert store._conn().execute('SELECT COUNT(*) FROM kg_concepts').fetchone()[0] == case['total_nodes']
            assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 10000
            assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
        finally:
            store.close()
    with pytest.raises(ValueError):
        module.prepare_growth(root, [10], attempts=1)
    with pytest.raises(ValueError):
        module.prepare_growth(Path('relative-target'), [10], attempts=1)


def test_schema31_personal_backup_is_readable_after_upgrade(tmp_path, monkeypatch):
    from filemate.execution import storage as implementation
    from filemate.operations.personal_backup import PersonalBackup
    migrations = implementation._MIGRATIONS
    monkeypatch.setattr(implementation, '_MIGRATIONS', tuple(m for m in migrations if m[0] <= 31))
    store = SQLiteStorage(tmp_path / 'old.db')
    try:
        store.init_schema()
        sid = store.save_source(original_name='旧版原创.txt', source_path='synthetic.txt', raw_text='旧版合成资料')
        aid = store.save_artifact(artifact_type='notes', source_id=sid, content={'text': '原有学习笔记'})
        backup = PersonalBackup(store, 'local', tmp_path / 'inbox', tmp_path / 'archive')
        raw = backup.export()
        monkeypatch.setattr(implementation, '_MIGRATIONS', migrations)
        store.init_schema()
        preview = backup.preview(raw)
        backup.restore(preview['backup_id'], preview['confirmation_token'])
        assert store.get_schema_version() == 33
        assert store.get_artifact(aid)['content'] == {'text': '原有学习笔记'}
        assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
    finally:
        store.close()


def test_control_v2_upgrade_and_owner_erasure(tmp_path):
    import sqlite3

    from filemate.runtime_governance import (
        _MIGRATION_2,
        _SCHEMA,
        BudgetStore,
        resource_schema_version,
        resource_scope,
    )
    path = tmp_path / 'control.db'
    with sqlite3.connect(path) as conn:
        for statement in (*_SCHEMA, *_MIGRATION_2):
            conn.execute(statement)
        conn.executemany('INSERT INTO resource_schema_migrations VALUES(?,?)', [(1, 123), (2, 456)])
    store = BudgetStore(path)
    with resource_scope(store, 'local', 'local') as scope:
        assert store.admit_learning(scope, 'course', 'request', 'input', now=1000)
        assert not store.admit_learning(scope, 'course', 'request', 'input', now=1000)
        assert len(store.export(scope)['learning_admissions']) == 1
        assert scope.owner_hash in store.owner_hashes()
        store.purge_owner_hash(scope.owner_hash)
        assert store.export(scope)['learning_admissions'] == []
    with sqlite3.connect(path) as conn:
        assert resource_schema_version(conn) == 3
        assert conn.execute('SELECT applied_at FROM resource_schema_migrations WHERE version=2').fetchone()[0] == 456
