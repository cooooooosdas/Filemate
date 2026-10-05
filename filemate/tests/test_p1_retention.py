# ruff: noqa: F811
"""恢复副本清理和匿名宽限期只影响合成独立空间。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from filemate.operations.personal_backup import PersonalBackup
from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401


def test_restore_cancel_and_expired_cleanup_keeps_business(server_module):
    module, store = server_module
    repo = PersonalBackup(store, 'local', module.UPLOAD_ROOT, module.ARCHIVE_DIR)
    with TestClient(module.app) as client:
        aid = store.save_artifact(artifact_type='notes', content='原创合成测试笔记')
        raw = repo.export(); p = repo.preview(raw)
        assert repo.cleanup()['files_removed'] == 0
        response = client.request('DELETE', '/api/privacy/restore-preview', json={'backup_id': p['backup_id'], 'confirmation_token': p['confirmation_token']})
        assert response.status_code == 200 and not response.json()['data']['cleanup_pending']
        assert not list(repo.cache.glob('*.zip'))
        assert store.get_artifact(aid)['content'] == '原创合成测试笔记'
        p = repo.preview(raw)
        assert repo.cleanup(int(time.time()) + 901)['files_removed'] == 1
        with pytest.raises(ValueError):
            repo.restore(p['backup_id'], p['confirmation_token'])


def test_failed_cleanup_receipt_stays_pending_until_verified_cleanup(server_module, monkeypatch):
    module, store = server_module
    repo = PersonalBackup(store, 'local', module.UPLOAD_ROOT, module.ARCHIVE_DIR)
    module.UPLOAD_ROOT.mkdir(parents=True); (module.UPLOAD_ROOT / 'synthetic.txt').write_text('synthetic', encoding='utf-8')
    p = repo.preview(repo.export())
    import filemate.operations.personal_backup as implementation
    original = implementation._remove_tree
    def fail_old(path, boundary):
        if path.name.startswith('.personal-rollback-'):
            raise OSError('injected cleanup failure')
        return original(path, boundary)
    monkeypatch.setattr(implementation, '_remove_tree', fail_old)
    assert repo.restore(p['backup_id'], p['confirmation_token'])['cleanup_pending']
    assert repo.restore(p['backup_id'], p['confirmation_token'])['cleanup_pending']
    assert repo.cleanup()['pending'] > 0
    monkeypatch.setattr(implementation, '_remove_tree', original)
    assert repo.cleanup()['directories_removed'] == 1
    assert not repo.restore(p['backup_id'], p['confirmation_token'])['cleanup_pending']
    assert (module.UPLOAD_ROOT / 'synthetic.txt').exists()


def test_cleanup_registry_tampering_never_deletes_external_data(server_module, tmp_path):
    module, store = server_module
    repo = PersonalBackup(store, 'local', module.UPLOAD_ROOT, module.ARCHIVE_DIR)
    repo.preview(repo.export())
    external = tmp_path / 'outside'; external.mkdir(); (external / 'keep.txt').write_text('keep', encoding='utf-8')
    (repo.cache / 'cleanup.json').write_text(json.dumps({'records': [{'path': str(external), 'boundary': str(tmp_path), 'token_hash': '0' * 64}], 'signature': 'forged'}), encoding='utf-8')
    with pytest.raises(ValueError, match='签名'):
        repo.cleanup()
    assert (external / 'keep.txt').exists()


def test_retention_grace_registered_and_active_protection(account_server):
    module = account_server; now = int(time.time())
    with TestClient(module.app) as guest, TestClient(module.app) as account:
        guest.post('/knowledge/import', files={'file': ('guest.txt', b'Synthetic anonymous lesson')})
        guest_owner = module._verify_identity_cookie(guest.cookies.get(module.IDENTITY_COOKIE_NAME))
        register(account)
        account_owner = module._accounts.resolve_session(account.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        account.get('/knowledge/sources')
        marker = module._retention.activity / (__import__('hashlib').sha256(guest_owner.encode()).hexdigest() + '.json')
        marker.unlink()
        with module._tenant_storage_lock:
            assert module._retention.run(module._tenant_storages, {}, set(), module._tenant_storage, now)['legacy_grace_started'] == 1
            assert module._retention.run(module._tenant_storages, {guest_owner: 1}, set(), module._tenant_storage, now + 91 * 86400)['guests_deleted'] == 0
            result = module._retention.run(module._tenant_storages, {}, set(), module._tenant_storage, now + 91 * 86400)
            assert result['guests_deleted'] == 1
        assert not (module.DATA_DIR / 'users' / guest_owner).exists()
        assert (module.DATA_DIR / 'users' / account_owner).exists()
        assert guest.get('/knowledge/sources').json()['data'] == []
        assert module._verify_identity_cookie(guest.cookies.get(module.IDENTITY_COOKIE_NAME)) != guest_owner
        assert account.get('/api/auth/me').json()['data']['user']


def test_activity_write_failure_is_recoverable_and_releases_active_request(account_server, monkeypatch):
    module = account_server
    with TestClient(module.app) as client:
        assert client.get('/knowledge/sources').status_code == 200
        original = module._retention.touch
        def fail_touch(*args):
            raise OSError('injected metadata write failure')
        monkeypatch.setattr(module._retention, 'touch', fail_touch)
        response = client.post('/knowledge/import', files={'file': ('owned.txt', b'Synthetic lesson')})
        assert response.status_code == 503
        assert not module._active_tenants
        monkeypatch.setattr(module._retention, 'touch', original)
        assert client.get('/knowledge/sources').json()['data'] == []
        assert client.post('/knowledge/import', files={'file': ('owned.txt', b'Synthetic lesson')}).status_code == 200
