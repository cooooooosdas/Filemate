# ruff: noqa: F811
"""个人整包导出恢复及归属、损坏、并发、事务故障注入合同。"""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import SQLiteStorage
from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.test_accounts import HEADERS, account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_personal_export_delete_restore_same_space(server_module):
    module, store = server_module
    with TestClient(module.app) as client:
        uploaded = client.post('/knowledge/import', files={'file': ('synthetic.txt', '原创合成课程正文'.encode(), 'text/plain')})
        assert uploaded.status_code == 200
        sid = uploaded.json()['data']['source_id']
        original = store.get_source(sid)
        aid = store.save_artifact(source_id=sid, artifact_type='questions', content=[{'question_type': 'fill', 'stem': '合成课程前提', 'answer': '有序'}])
        assert client.post('/quiz/attempts', json={'artifact_id': aid, 'question_index': 0, 'user_answer': '错误'}).status_code == 200
        backup = client.get('/api/privacy/export').content
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            exported = json.loads(archive.read('personal-data.json'))
            assert not {'accounts', 'account_sessions', 'account_attempts', 'data_action_previews'} & exported['tables'].keys()
            assert len(exported['tables']['sources']) == 1 and len(exported['tables']['quiz_attempts']) == 1
            assert any(name.startswith('files/inbox/') for name in archive.namelist())
        assert client.get('/api/privacy/export?format=json').json()['tables']['sources'][0]['source_id'] == sid
        preview = client.get(f'/knowledge/sources/{sid}/delete-preview').json()['data']
        assert client.request('DELETE', f'/knowledge/sources/{sid}', json={'confirmed': True, 'confirmation_token': preview['confirmation_token']}).status_code == 200
        assert store.get_source(sid) is None
        restore_preview = client.post('/api/privacy/restore-preview', files={'file': ('personal.zip', backup, 'application/zip')})
        assert restore_preview.status_code == 200
        p = restore_preview.json()['data']
        assert p['current_counts']['sources'] == 0 and p['restored_counts']['sources'] == 1
        assert store.get_source(sid) is None
        request = {'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}
        assert client.post('/api/privacy/restore', json={**request, 'confirmed': False}).status_code == 422
        result = client.post('/api/privacy/restore', json=request)
        assert result.status_code == 200, result.text
        assert result.json()['data']['restored'] and not result.json()['data']['cleanup_pending']
        assert store.get_source(sid)['raw_text'] == original['raw_text']
        from pathlib import Path
        assert Path(store.get_source(sid)['source_path']).read_text(encoding='utf-8') == original['raw_text']
        assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 1
        assert store._conn().execute('PRAGMA foreign_key_check').fetchall() == []
        assert client.post('/api/privacy/restore', json=request).json()['data']['restored']
        assert store._conn().execute("SELECT COUNT(*) FROM data_action_audit WHERE action='personal_restore'").fetchone()[0] == 1


def test_personal_restore_tampering_foreign_space_and_changed_preview(server_module, tmp_path):
    module, store = server_module
    with TestClient(module.app) as client:
        raw = client.get('/api/privacy/export').content
        other = SQLiteStorage(tmp_path / 'other' / 'different.db'); other.init_schema()
        with pytest.raises(ValueError, match='备份不属于'):
            PersonalBackup(other, 'another-owner', tmp_path / 'other' / 'inbox', tmp_path / 'other' / 'archive').validate(raw)
        other.close()
        modified = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, zipfile.ZipFile(modified, 'w') as output:
            for name in archive.namelist():
                output.writestr(name, archive.read(name) if name != 'personal-data.json' else b'{"forged":true}')
        assert client.post('/api/privacy/restore-preview', files={'file': ('modified.zip', modified.getvalue())}).status_code == 409
        assert client.post('/api/privacy/restore-preview', files={'file': ('bad.zip', b'not a ZIP')}).status_code == 409
        p = client.post('/api/privacy/restore-preview', files={'file': ('own.zip', raw)}).json()['data']
        store.save_artifact(artifact_type='notes', content={'text': 'preview后新增的合成笔记'})
        assert client.post('/api/privacy/restore', json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}).status_code == 409
        assert store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 1


def test_personal_restore_file_failure_rolls_back_database_and_files(server_module, monkeypatch):
    module, store = server_module
    from pathlib import Path
    inbox = module.UPLOAD_ROOT; inbox.mkdir(parents=True); (inbox / 'before.txt').write_text('合成原文件', encoding='utf-8')
    repo = PersonalBackup(store, 'local', inbox, module.ARCHIVE_DIR)
    raw = repo.export()
    (inbox / 'later.txt').write_text('恢复前新增合成文件', encoding='utf-8')
    aid = store.save_artifact(artifact_type='notes', content='恢复前新增合成笔记')
    p = repo.preview(raw)
    import filemate.operations.personal_backup as implementation
    original_move = implementation.shutil.move
    def fail_second(source, destination):
        if Path(destination) == module.ARCHIVE_DIR.resolve():
            raise OSError('injected archive install failure')
        return original_move(source, destination)
    monkeypatch.setattr(implementation.shutil, 'move', fail_second)
    with pytest.raises(OSError, match='injected'):
        repo.restore(p['backup_id'], p['confirmation_token'])
    assert store.get_artifact(aid)['content'] == '恢复前新增合成笔记'
    assert (inbox / 'before.txt').read_text(encoding='utf-8') == '合成原文件'
    assert (inbox / 'later.txt').exists()
    assert store._conn().execute("SELECT COUNT(*) FROM data_action_audit WHERE action='personal_restore'").fetchone()[0] == 0


def test_personal_restore_blocks_parallel_requests_and_switches(server_module, monkeypatch):
    module, _store = server_module
    with TestClient(module.app) as client:
        raw = client.get('/api/privacy/export').content
        p = client.post('/api/privacy/restore-preview', files={'file': ('own.zip', raw)}).json()['data']
        module._active_tenants['local'] = 1
        assert client.post('/api/privacy/restore', json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}).status_code == 409
        module._active_tenants['local'] = 0
        monkeypatch.setenv('FILEMATE_ENABLE_PERSONAL_DATA', '0')
        assert client.get('/api/privacy/export').status_code == 503
        assert client.get('/knowledge/sources').status_code == 200


def test_personal_restore_database_failure_rolls_back_and_returns_scoped_error(server_module):
    module, store = server_module
    inbox = module.UPLOAD_ROOT; inbox.mkdir(parents=True); (inbox / 'proof.txt').write_text('备份原文', encoding='utf-8')
    aid = store.save_artifact(artifact_type='notes', content='备份原笔记')
    with TestClient(module.app) as client:
        raw = client.get('/api/privacy/export').content
        store.save_artifact(artifact_id=aid, artifact_type='notes', content='当前新笔记')
        (inbox / 'proof.txt').write_text('当前新文件', encoding='utf-8')
        p = client.post('/api/privacy/restore-preview', files={'file': ('own.zip', raw)}).json()['data']
        conn = store._conn()
        conn.execute("CREATE TRIGGER inject_restore_failure BEFORE INSERT ON artifacts WHEN NEW.artifact_type='notes' BEGIN SELECT RAISE(ABORT,'injected database failure'); END"); conn.commit()
        failed = client.post('/api/privacy/restore', json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True})
        assert failed.status_code == 503 and '已回滚' in failed.text
        assert store.get_artifact(aid)['content'] == '当前新笔记'
        assert (inbox / 'proof.txt').read_text(encoding='utf-8') == '当前新文件'
        assert 'local' not in module._exclusive_tenants
        conn.execute('DROP TRIGGER inject_restore_failure'); conn.commit()
        assert client.get('/knowledge/sources').status_code == 200


def test_personal_backup_rejects_hardlinks_and_zip_path_traversal(server_module, tmp_path):
    module, store = server_module
    import os
    inbox = module.UPLOAD_ROOT; inbox.mkdir(parents=True)
    secret = tmp_path / 'outside.txt'; secret.write_text('边界测试合成文本', encoding='utf-8')
    os.link(secret, inbox / 'hardlink.txt')
    with pytest.raises(ValueError, match='硬链接'):
        PersonalBackup(store, 'local', inbox, module.ARCHIVE_DIR).export()
    (inbox / 'hardlink.txt').unlink()
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as archive:
        archive.writestr('manifest.json', '{}'); archive.writestr('../outside.txt', 'invalid')
    with pytest.raises(ValueError, match='边界'):
        PersonalBackup(store, 'local', inbox, module.ARCHIVE_DIR).validate(raw.getvalue())
    assert secret.read_text(encoding='utf-8') == '边界测试合成文本'


def test_accounts_cannot_restore_each_others_data_or_reuse_confirmation(account_server):
    from filemate.tests.test_p1_resume import FACTS
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice).status_code == 200
        assert register(bob, 'bob-synthetic@example.invalid').status_code == 200
        sid = alice.post('/knowledge/import', files={'file': ('private.txt', b'Only Alice synthetic source')}).json()['data']['source_id']
        assert alice.put('/api/resume/profile', headers=HEADERS, json=FACTS).status_code == 200
        assert bob.get('/api/resume/profile').json()['data'] is None
        raw = alice.get('/api/privacy/export').content
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            tables = json.loads(archive.read('personal-data.json'))['tables']
            assert not {'accounts', 'account_sessions'} & tables.keys()
        assert bob.post('/api/privacy/restore-preview', headers=HEADERS, files={'file': ('alice.zip', raw)}).status_code == 409
        p = alice.post('/api/privacy/restore-preview', headers=HEADERS, files={'file': ('own.zip', raw)}).json()['data']
        assert bob.post('/api/privacy/restore', headers=HEADERS, json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token'], 'confirmed': True}).status_code == 409
        assert alice.get(f'/knowledge/sources/{sid}').status_code == 200
        assert bob.get(f'/knowledge/sources/{sid}').status_code == 404
