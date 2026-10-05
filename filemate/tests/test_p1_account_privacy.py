# ruff: noqa: F811
"""真实账号注销、空间隔离和两阶段中断恢复的合成回归。"""

import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from filemate.tests.test_accounts import (  # noqa: F401
    HEADERS,
    PASSWORD,
    account_server,
    login,
    register,
)


def proposal(client):
    response = client.get('/api/auth/delete-preview')
    assert response.status_code == 200, response.text
    return {'confirmed': True, 'password': PASSWORD, 'confirmation_token': response.json()['data']['confirmation_token']}


def test_account_erasure_isolated_revokes_all_devices_and_idempotent(account_server):
    module = account_server
    with TestClient(module.app) as owner, TestClient(module.app) as device, TestClient(module.app) as other:
        registered = register(owner).json()['data']; code = registered['recovery_code']
        assert login(device).status_code == 200
        assert register(other, email='other@example.invalid').status_code == 200
        sid = owner.post('/knowledge/import', files={'file': ('owned.txt', b'Synthetic owned lesson')}).json()['data']['source_id']
        owner.get('/api/privacy/export')
        workspace = module._accounts.resolve_session(owner.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        root = module.DATA_DIR / 'users' / workspace
        assert root.exists() and (root / 'filemate.backup-secret').exists()
        assert other.post('/knowledge/import', files={'file': ('other.txt', b'Other synthetic lesson')}).status_code == 200
        p = proposal(owner)
        assert owner.post('/api/auth/delete', headers=HEADERS, json={**p, 'confirmed': False}).status_code == 422
        assert owner.post('/api/auth/delete', headers=HEADERS, json={**p, 'password': 'wrongpassword1'}).status_code == 401
        assert owner.get(f'/knowledge/sources/{sid}').status_code == 200
        assert other.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 409
        response = owner.post('/api/auth/delete', headers=HEADERS, json=p)
        assert response.status_code == 200, response.text
        assert response.json()['data'] == {'deleted': True, 'cleanup_pending': False}
        assert not root.exists()
        assert module._workspace_deletion.blocked(workspace)
        assert device.get('/knowledge/sources').status_code == 401
        assert login(device).status_code == 401
        assert device.post('/api/auth/recover', headers=HEADERS, json={'email': 'synthetic@example.invalid', 'recovery_code': code, 'password': PASSWORD}).status_code == 401
        assert owner.post('/api/auth/delete', headers=HEADERS, json=p).json()['data']['deleted']
        assert len(other.get('/knowledge/sources').json()['data']) == 1
        with module._accounts._connection() as conn:
            assert conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 1
        final = [json.loads(path.read_text(encoding='utf-8'))['record'] for path in module._workspace_deletion.actions.glob('*.json')]
        assert len(final) == 1 and 'account_id' not in final[0] and 'workspace_id' not in final[0]


def test_account_preview_revision_and_active_requests(account_server):
    module = account_server
    with TestClient(module.app) as client:
        assert register(client).status_code == 200
        p = proposal(client)
        assert client.post('/knowledge/import', files={'file': ('later.txt', b'Synthetic new data')}).status_code == 200
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 409
        p = proposal(client)
        owner = module._accounts.resolve_session(client.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        module._active_tenants[owner] = 1
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 409
        module._active_tenants.pop(owner)
        assert client.get('/api/auth/me').json()['data']['user']


def test_primary_delete_failure_restores_account_and_files(account_server):
    module = account_server
    with TestClient(module.app) as client:
        assert register(client).status_code == 200
        sid = client.post('/knowledge/import', files={'file': ('owned.txt', b'Synthetic owned lesson')}).json()['data']['source_id']
        p = proposal(client)
        owner = module._accounts.resolve_session(client.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        with module._accounts._connection() as conn:
            conn.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON accounts BEGIN SELECT RAISE(ABORT,'injected'); END")
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 503
        assert not module._workspace_deletion.blocked(owner)
        assert client.get(f'/knowledge/sources/{sid}').json()['data']['raw_text'] == 'Synthetic owned lesson'
        assert login(client).status_code == 200
        assert not module._exclusive_tenants


def test_directory_stage_failure_preserves_account(account_server, monkeypatch):
    module = account_server
    with TestClient(module.app) as client:
        register(client); p = proposal(client)
        original = Path.rename
        def fail_stage(path, target):
            if path.parent.name == 'users':
                raise OSError('injected stage failure')
            return original(path, target)
        monkeypatch.setattr(Path, 'rename', fail_stage)
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 409
        assert login(client).status_code == 200


@pytest.mark.parametrize('committed', [False, True])
def test_crash_recovery_uses_primary_commit_and_honors_erasure_ledger(account_server, committed):
    module = account_server
    with TestClient(module.app) as client:
        data = register(client).json()['data']; proposal(client)
        account = module._accounts.resolve_session(client.cookies.get(module.ACCOUNT_COOKIE_NAME))
        owner = account['workspace_id']; root = module.DATA_DIR / 'users' / owner
        module._close_tenant_storages()
        token = secrets.token_hex(32)
        with module._accounts._connection() as conn:
            original_account = dict(conn.execute('SELECT * FROM accounts').fetchone())
        module._workspace_deletion.stage(owner, token, data['user']['account_id'], {'sources': 0})
        assert not root.exists()
        if committed:
            with module._accounts._connection() as conn:
                conn.execute('DELETE FROM account_sessions'); conn.execute('DELETE FROM accounts')
        result = module._workspace_deletion.recover(module._accounts)
        assert root.exists() is not committed
        assert module._workspace_deletion.blocked(owner) is committed
        assert result['completed' if committed else 'rolled_back'] == 1
        if committed:
            root.mkdir(); (root / 'old-backup.txt').write_text('synthetic recovered secret', encoding='utf-8')
            with module._accounts._connection() as conn:
                names = ','.join(original_account); placeholders = ','.join('?' for _ in original_account)
                conn.execute(f'INSERT INTO accounts({names}) VALUES({placeholders})', list(original_account.values()))
            assert login(client).status_code == 401
            module._workspace_deletion.recover(module._accounts)
            assert not root.exists()
            with module._accounts._connection() as conn:
                assert conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0


def test_erasure_cleanup_failure_reports_pending_and_retry(account_server, monkeypatch):
    module = account_server
    import filemate.operations.workspace_privacy as implementation
    with TestClient(module.app) as client:
        register(client); p = proposal(client)
        original = implementation._remove_tree
        monkeypatch.setattr(implementation, '_remove_tree', lambda *args: (_ for _ in ()).throw(OSError('injected cleanup failure')))
        response = client.post('/api/auth/delete', headers=HEADERS, json=p)
        assert response.status_code == 200 and response.json()['data']['cleanup_pending']
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).json()['data']['cleanup_pending']
        assert login(client).status_code == 401
        monkeypatch.setattr(implementation, '_remove_tree', original)
        assert module._workspace_deletion.recover(module._accounts)['completed'] == 1
        assert not module._workspace_deletion.receipt(p['confirmation_token'])['cleanup_pending']


@pytest.mark.parametrize('environment_identity', [False, True])
def test_admin_restore_preserves_newer_erasure_and_personal_signing_key(account_server, tmp_path, monkeypatch, environment_identity):
    module = account_server
    from filemate.accounts import AccountStore
    from filemate.operations import backup
    from filemate.operations.workspace_privacy import WorkspaceDeletion
    if environment_identity:
        monkeypatch.setenv('FILEMATE_IDENTITY_SECRET', module._identity_secret.decode())
        (module.DATA_DIR / 'identity.secret').unlink(missing_ok=True)
    with TestClient(module.app) as client:
        register(client)
        client.post('/knowledge/import', files={'file': ('owned.txt', b'Synthetic owned lesson')})
        client.get('/api/privacy/export')
        owner = module._accounts.resolve_session(client.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        module._close_tenant_storages(); module._local_storage.close()
        snapshot = tmp_path / 'admin-snapshot'
        plan = backup.plan_backup(module.DATA_DIR)
        assert any(entry['path'].endswith('filemate.backup-secret') for entry in plan['entries'])
        backup.create_backup(module.DATA_DIR, snapshot, plan['confirmation'], quiesced=True)
        p = proposal(client)
        assert client.post('/api/auth/delete', headers=HEADERS, json=p).status_code == 200
        target = tmp_path / 'restored'
        restore_plan = backup.plan_restore(snapshot, target)
        assert len(restore_plan['preserved_erasure_ledger']) == 1
        assert backup.restore_backup(snapshot, target, restore_plan['confirmation'])['preserved_erasure_count'] == 1
        restored_accounts = AccountStore(target / 'filemate.db')
        restored_deletion = WorkspaceDeletion(target, (target / 'identity.secret').read_bytes().strip())
        assert restored_deletion.blocked(owner)
        restored_deletion.recover(restored_accounts)
        assert not (target / 'users' / owner).exists()
        with restored_accounts._connection() as conn:
            assert conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] == 0
