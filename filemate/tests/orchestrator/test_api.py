# ruff: noqa: F811
"""HTTP contracts, existing authentication and isolated learning spaces."""

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401

from .conftest import module, scope, snapshot

ROOT = '/api/learning/orchestrator'


@pytest.fixture
def client(world, monkeypatch):
    monkeypatch.setenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR', '1')
    app = FastAPI()
    api = module('api')
    monkeypatch.setattr(api, 'utc_now', lambda: world['now'][0])
    app.include_router(api.create_router(lambda: world['store']))
    with TestClient(app) as c:
        yield c


def preview_body(world):
    return {'scope': scope(world).model_dump(), 'expected_evidence_revision': snapshot(world).evidence_revision,
            'options': {'available_minutes': 30}}


def test_strict_json_and_unknown_or_repeated_query(client, world):
    assert client.post(ROOT + '/snapshot', content=b'x' * 262145).status_code == 413
    for suffix in ('?unknown=1', '?x=1&x=2'):
        assert client.get(ROOT + '/capabilities' + suffix).status_code == 422
    for changes in ({'unexpected': 1}, {'options': {'available_minutes': True}}, {'scope': {'goal_id': world['goal'], 'workspace_id': 'other'}}):
        response = client.post(ROOT + '/preview', json=preview_body(world) | changes)
        assert response.status_code == 422 and response.headers['cache-control'] == 'no-store'
    assert client.post(ROOT + '/snapshot', content='{"goal_id":"a","goal_id":"b"}', headers={'Content-Type': 'application/json'}).status_code == 422


def test_disabled_keeps_history_readable(client, world, monkeypatch):
    monkeypatch.delenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR')
    assert client.get(ROOT + '/capabilities').json()['data']['enabled'] is False
    assert client.get(ROOT + '/today').status_code == 200
    assert client.post(ROOT + '/snapshot', json=scope(world).model_dump()).status_code == 503
    assert client.post(ROOT + '/preview', json=preview_body(world)).status_code == 503


def test_stale_scope_409_and_storage_503(client, world, monkeypatch):
    body = preview_body(world) | {'expected_evidence_revision': '0' * 64}
    assert client.post(ROOT + '/preview', json=body).status_code == 409

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError('synthetic-private-db-path.sql')
    monkeypatch.setattr(module('snapshot').SnapshotReader, 'read', broken)
    response = client.post(ROOT + '/snapshot', json=scope(world).model_dump())
    assert response.status_code == 503
    assert 'private' not in response.text and response.json()['success'] is False


def test_preview_and_operation_quotas_429(client, world):
    from filemate.execution.data_actions import issue
    from filemate.study.orchestrator.repository import day_id

    from .conftest import snapshot as current
    conn = world['store']._conn()
    for _ in range(100):
        issue(conn, 'orchestrator_confirm', day_id(current(world).study_date), 'synthetic')
    conn.commit()
    assert client.post(ROOT + '/preview', json=preview_body(world)).status_code == 429


def test_api_prefix_uses_existing_gateway_rules(client, world):
    for accept in ('application/json', 'text/html'):
        response = client.post(ROOT + '/snapshot', headers={'Accept': accept}, json=scope(world).model_dump())
        assert response.status_code == 200 and 'application/json' in response.headers['content-type']
        assert response.json()['data']['snapshot']['scope']['goal_id'] == world['goal']


def test_auth_and_tenant_boundaries(account_server, monkeypatch):
    monkeypatch.setenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR', '1')
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice, keep_guest_data=False).status_code == 200
        goal = alice.post('/goals/reverse-plan', json={'title': '原创合成目标', 'goal_type': 'exam', 'deadline': '2026-12-31', 'target_score': 80}).json()['data']['goal_id']
        assert alice.post(ROOT + '/snapshot', json={'goal_id': goal}).status_code == 200
        assert bob.post(ROOT + '/snapshot', json={'goal_id': goal}).status_code == 404
        alice.cookies.set(account_server.ACCOUNT_COOKIE_NAME, 'expired-synthetic', domain='testserver.local', path='/')
        assert alice.get(ROOT + '/today').status_code == 401


def test_generic_artifact_patch_rejects_reserved_types(server_module):
    server, store = server_module
    models = module('models')
    goal = store.save_artifact(artifact_type='reverse_goal_plan', content={'tasks': []})
    snap = module('snapshot').SnapshotReader(store).read(models.ScopeRequest(goal_id=goal))
    body = models.PreviewRequest(scope=snap.scope, expected_evidence_revision=snap.evidence_revision,
                                 options=models.ScheduleOptions(available_minutes=0))
    commands = module('commands').OrchestratorCommands(store)
    token = commands.preview(body).confirmation_token
    receipt = commands.confirm(models.ConfirmRequest(**body.model_dump(), confirmation_token=token, request_key='synthetic-api-reserved', confirmed=True))
    with TestClient(server.app) as client:
        response = client.patch('/knowledge/artifacts/' + receipt.operation_id, json={'title': 'tamper', 'content': {}})
        assert response.status_code in (409, 422)
        assert store.get_artifact(receipt.operation_id)['content']['receipt']['status'] == 'confirmed'


def test_confirm_quota_preserves_last_receipt(client, world):
    from .test_commands import command, prepared
    for i in range(100):
        request = prepared(world).model_copy(update={'request_key': f'synthetic-quota-{i:04}'})
        last = command(world).confirm(request)
    request = prepared(world).model_copy(update={'request_key': 'synthetic-over-quota'})
    response = client.post(ROOT + '/confirm', json=request.model_dump(mode='json'))
    assert response.status_code == 429
    assert client.get(ROOT + '/operations/' + last.request_key).json()['data']['operation_id'] == last.operation_id



def test_concurrent_undo_rejection_exposes_public_machine_error(client, world):
    from .test_commands import command, prepared

    first = command(world).confirm(prepared(world))
    preview = client.post(ROOT + f'/operations/{first.operation_id}/undo-preview', json={})
    assert preview.status_code == 200
    command(world).confirm(prepared(world).model_copy(update={'request_key': 'synthetic-later-arrangement'}))
    response = client.post(ROOT + f'/operations/{first.operation_id}/undo-confirm', json={
        'confirmation_token': preview.json()['data']['confirmation_token'],
        'request_key': 'synthetic-definite-undo-rejection', 'confirmed': True,
    })
    assert response.status_code == 409
    assert response.json() == {'success': False, 'data': {
        'error_code': 'schedule_changed_since_operation'}, 'error': 'schedule_changed_since_operation'}
    assert client.get(ROOT + '/operations/synthetic-definite-undo-rejection').status_code == 404
