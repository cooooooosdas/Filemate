# ruff: noqa: F811
"""Synthetic workspace labels, bounded goal browsing and durable receipts."""

import json
import sqlite3
from datetime import date

import pytest

from filemate.execution.storage import SQLiteStorage

from .conftest import module, snapshot
from .test_api import account_server, client  # noqa: F401
from .test_commands import command, prepared

ROOT = '/api/learning/orchestrator'


def fingerprint(store):
    return {table: [tuple(row) for row in store._conn().execute(f'SELECT * FROM {table} ORDER BY rowid')]
            for table in ('artifacts', 'sources', 'quiz_attempts', 'wrong_questions', 'study_plans')}


def test_goal_options_are_paged_and_private(client, world):
    store = world['store']
    for index in range(65):
        store.save_artifact(artifact_type='reverse_goal_plan', title=f'目录合成目标{index:02}',
                            content={'goal_type': 'exam', 'deadline': '2026-11-05', 'tasks': [],
                                     'gaps': ['synthetic-private-answer'], 'evidence_snapshot': {'score': 99}})
    store.save_artifact(artifact_type='notes', title='目录合成非目标', content='synthetic-private-answer')
    before = fingerprint(store)
    pages = [client.post(ROOT + '/goal-options', json={'q': '目录合成', 'offset': offset})
             for offset in (0, 30, 60)]
    assert [r.status_code for r in pages] == [200, 200, 200]
    data = [r.json()['data'] for r in pages]
    assert [len(p['items']) for p in data] == [30, 30, 5]
    assert all(p['total'] == 65 and p['limit'] == 30 for p in data)
    assert data[1]['offset'] == 30
    ids = [item['goal_id'] for page in data for item in page['items']]
    assert len(set(ids)) == 65
    assert all(item['valid'] is True for page in data for item in page['items'])
    assert all(set(item) == {'goal_id', 'title', 'goal_type', 'deadline', 'source_id', 'valid'}
               for page in data for item in page['items'])
    assert all('synthetic-private-answer' not in r.text and r.headers['cache-control'] == 'no-store' for r in pages)
    assert fingerprint(store) == before


@pytest.mark.parametrize('needle', ['100%', 'x_y', r'a\b', "x' OR 1=1 --"])
def test_goal_search_treats_wildcards_as_literal_text(client, world, needle):
    wanted = world['store'].save_artifact(artifact_type='reverse_goal_plan', title='检索-' + needle,
                                          content={'tasks': []})
    world['store'].save_artifact(artifact_type='reverse_goal_plan', title='检索-100xxx-xay-ab', content={'tasks': []})
    response = client.post(ROOT + '/goal-options', json={'q': needle})
    assert response.status_code == 200
    assert response.json()['data']['total'] == 1
    assert [item['goal_id'] for item in response.json()['data']['items']] == [wanted]


def test_damaged_goals_do_not_block_the_directory(client, world):
    store = world['store']
    damaged = []
    for value in ('{broken', '[]', '{"tasks":{}}', '{"tasks":[],"blob":"' + 'x' * 1048576 + '"}'):
        identifier = store.save_artifact(artifact_type='reverse_goal_plan', title='损坏合成目标', content={})
        store._conn().execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (value, identifier))
        damaged.append(identifier)
    store._conn().commit()
    response = client.post(ROOT + '/goal-options', json={'q': '损坏合成'})
    assert response.status_code == 200
    data = response.json()['data']
    assert data['total'] == 4
    assert {item['goal_id'] for item in data['items']} == set(damaged)
    assert all(item['valid'] is False and item['title'] == '损坏合成目标' for item in data['items'])


@pytest.mark.parametrize('body', [{'offset': -1}, {'offset': 1000001}, {'offset': True}, {'offset': 1.5},
                                 {'q': 'x' * 121}, {'q': None}, {'limit': 100}, {'workspace_id': 'foreign'}])
def test_goal_options_validate_the_own_contract(client, body):
    response = client.post(ROOT + '/goal-options', json=body)
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'no-store'


def test_goal_options_obey_capabilities_and_disabled_history(client, world, monkeypatch):
    assert client.get(ROOT + '/capabilities').json()['data'].get('ui_contract') == 'today-workspace-v1'
    monkeypatch.setenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR', '0')
    assert client.post(ROOT + '/goal-options', json={}).status_code == 503
    assert client.get(ROOT + '/today').status_code == 200


def test_goal_options_use_existing_account_space(account_server, monkeypatch):
    from fastapi.testclient import TestClient

    from filemate.tests.test_accounts import register

    monkeypatch.setenv('FILEMATE_ENABLE_LEARNING_ORCHESTRATOR', '1')
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice, keep_guest_data=False).status_code == 200
        created = alice.post('/goals/reverse-plan', json={
            'title': '仅甲账号合成目标', 'goal_type': 'exam', 'deadline': '2026-12-31',
        })
        assert created.status_code == 200
        mine = alice.post(ROOT + '/goal-options', json={'q': '仅甲账号'})
        other = bob.post(ROOT + '/goal-options', json={'q': '仅甲账号'})
        assert mine.status_code == other.status_code == 200
        assert mine.json()['data']['total'] == 1 and other.json()['data']['items'] == []
        alice.cookies.set(account_server.ACCOUNT_COOKIE_NAME, 'expired-synthetic', domain='testserver.local', path='/')
        assert alice.post(ROOT + '/goal-options', json={}).status_code == 401


def test_snapshot_labels_are_bounded_without_old_profile(world):
    store = world['store']
    artifact = store.get_artifact(world['goal'])
    artifact['content']['title'] = '目标' * 200
    artifact['content']['evidence_snapshot'] = {'private_score': 99}
    store.update_artifact(world['goal'], title='目标' * 200, content=artifact['content'])
    store._conn().execute('UPDATE sources SET original_name=? WHERE source_id=?', ('资料' * 200, world['sources'][0]))
    store._conn().commit()
    before = fingerprint(store)
    result = snapshot(world)
    assert result.facts['goal'].get('title') == '目标' * 80
    assert result.facts['sources'][0].get('original_name') == '资料' * 120
    assert 'private_score' not in result.model_dump_json()
    assert fingerprint(store) == before


def test_goal_rename_invalidates_an_old_preview(world):
    old = prepared(world)
    first = snapshot(world)
    artifact = world['store'].get_artifact(world['goal'])
    artifact['content']['title'] = '改名后的合成目标'
    world['store'].update_artifact(world['goal'], title='改名后的合成目标', content=artifact['content'])
    second = snapshot(world)
    assert first.evidence_revision != second.evidence_revision
    with pytest.raises(module('models').OrchestratorError):
        command(world).confirm(old)


def day(world, store=None):
    return module('repository').OrchestratorRepository(store or world['store'], clock=lambda: world['now'][0]).today(date(2026, 10, 31))


def test_day_receipt_pointer_is_atomic_and_backward_readable(world):
    result = command(world).confirm(prepared(world))
    reopened = SQLiteStorage(world['store'].db_path)
    try:
        assert day(world, reopened).model_dump().get('latest_operation') == result.model_dump()
    finally:
        reopened.close()
    repository = module('repository')
    conn = world['store']._conn()
    saved = repository.load(conn, repository.day_id('2026-10-31'), repository.DAY_TYPE)
    saved.pop('last_operation_id', None)
    conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps(saved), repository.day_id('2026-10-31')))
    conn.commit()
    assert day(world).status == 'confirmed'
    assert day(world).model_dump().get('latest_operation') is None
    assert repository.OrchestratorRepository(world['store']).find_request(result.request_key) == result


def test_undo_receipt_survives_even_when_day_has_no_config(world):
    cmd = command(world)
    result = cmd.confirm(prepared(world))
    token = cmd.preview_undo(result.operation_id).confirmation_token
    undone = cmd.confirm_undo(result.operation_id, module('models').UndoConfirmRequest(
        confirmation_token=token, request_key='synthetic-c-context-undo', confirmed=True))
    assert day(world).status == 'not_confirmed'
    assert day(world).model_dump().get('latest_operation') == undone.model_dump()


@pytest.mark.parametrize('damage', ['missing', 'wrong_type', 'bad_json', 'wrong_day', 'wrong_revision', 'wrong_id', 'wrong_key'])
def test_bad_receipt_pointer_only_disables_undo_not_the_day(world, damage):
    cmd = command(world)
    result = cmd.confirm(prepared(world))
    repository = module('repository')
    conn = world['store']._conn()
    saved = repository.load(conn, repository.day_id('2026-10-31'), repository.DAY_TYPE)
    saved['last_operation_id'] = result.operation_id
    record = repository.load(conn, result.operation_id, repository.OP_TYPE)
    if damage == 'missing':
        saved['last_operation_id'] = 'missing-operation'
    elif damage == 'wrong_type':
        saved['last_operation_id'] = world['goal']
    elif damage == 'bad_json':
        conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', ('{broken', result.operation_id))
    else:
        field, value = {'wrong_day': ('study_date', '2026-10-30'), 'wrong_revision': ('revision', 99),
                        'wrong_id': ('operation_id', 'another-operation'), 'wrong_key': ('request_key', 'another-request-key')}[damage]
        record['receipt'][field] = value
        conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps(record), result.operation_id))
    conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps(saved), repository.day_id('2026-10-31')))
    conn.commit()
    result_day = day(world)
    assert result_day.status == 'confirmed' and result_day.selected
    assert result_day.model_dump().get('latest_operation') is None


def test_day_pointer_and_receipt_roll_back_together(world):
    request = prepared(world)
    conn = world['store']._conn()
    conn.execute("CREATE TRIGGER synthetic_receipt_failure BEFORE INSERT ON artifacts WHEN NEW.artifact_type='learning_orchestration_operation' BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        command(world).confirm(request)
    assert day(world).status == 'not_confirmed'
    assert day(world).model_dump().get('latest_operation') is None
    assert conn.execute("SELECT count(*) FROM artifacts WHERE artifact_type LIKE 'learning_orchestration_%'").fetchone()[0] == 0
    assert conn.execute('SELECT result FROM data_action_previews').fetchone()[0] is None
