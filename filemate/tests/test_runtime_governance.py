# ruff: noqa: F811
"""合成回归：模型累计准入、并发、故障和隐私恢复边界。"""

import asyncio
import hashlib
import io
import json
import multiprocessing
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from filemate.llm_client import LLMClient, LLMConfig
from filemate.llm_client.exceptions import LLMAPIError, LLMRateLimitError, LLMTimeoutError
from filemate.llm_client.models.response import LLMResponse
from filemate.operations import backup
from filemate.operations.workspace_privacy import WorkspaceDeletion
from filemate.runtime_governance import (
    BudgetExceeded,
    BudgetStore,
    GovernanceUnavailable,
    Limits,
    Policy,
    default_scope,
    owner_digest,
    resource_scope,
)
from filemate.speech import MicrosoftSpeech, SpeechUnavailable
from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_backup import managed  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401

OWNER_A = 'u_' + 'a' * 32
OWNER_B = 'u_' + 'b' * 32


@pytest.fixture
def store(tmp_path):
    return BudgetStore(tmp_path / 'control/resource-governance.db')


def admit(scope, units=100):
    return scope.store.reserve(scope, provider='synthetic-provider', model='synthetic-model', budget_units=units)


def fake_client(monkeypatch, replies):
    client = LLMClient(LLMConfig(api_key='synthetic-secret-only'))
    calls = []

    def chat(*args, **kwargs):
        calls.append(kwargs)
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat)
    return client, calls


def test_attempts_persist_across_new_clients_and_store_instances(store, monkeypatch):
    store.policy = replace(store.policy, account=Limits(2, 100_000, 2))
    client, calls = fake_client(monkeypatch, [LLMResponse('ok', usage={'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10})] * 2)
    with resource_scope(store, OWNER_A, 'account') as scope:
        assert client.call('Synthetic private input', retry=1) == 'ok'
        assert client.call('Synthetic private input', retry=1) == 'ok'
        assert len(calls) == 2
        actual = store.view(scope)
        assert actual['daily']['attempts'] == 2
        assert actual['daily']['reported_tokens'] == {'prompt_tokens': 14, 'completion_tokens': 6, 'total_tokens': 20}
        assert len({row['trace_id'] for row in actual['items']}) == 1
    reopened = BudgetStore(store.path, store.policy)
    with resource_scope(reopened, OWNER_A, 'account'), pytest.raises(BudgetExceeded):
        client.call(retry=1)
    assert len(calls) == 2


def test_unknown_usage_and_cost_remain_null_and_payload_is_not_recorded(store, monkeypatch):
    client, _ = fake_client(monkeypatch, [LLMResponse('Synthetic private response', request_id='synthetic-secret-only')])
    with resource_scope(store, OWNER_A, 'account') as scope:
        client.call('Synthetic private prompt', retry=1)
        result = store.export(scope)
    assert result['cost'] == {'status': 'not_available', 'amount': None, 'currency': None}
    assert all(value is None for value in result['daily']['reported_tokens'].values())
    row = result['items'][0]
    assert row['status'] == 'success' and row['request_id'] is None
    assert row['prompt_tokens'] is None and row['total_tokens'] is None
    assert row['budget_units'] > 0
    serialized = json.dumps(result)
    assert not any(value in serialized for value in ('synthetic-secret-only', 'Synthetic private prompt', 'Synthetic private response', OWNER_A))
    assert 'synthetic-secret-only' not in repr(client.config)


def test_real_zero_is_distinct_from_unknown_and_higher_usage_blocks_next_attempt(store):
    store.policy = replace(store.policy, account=Limits(10, 100, 2))
    with resource_scope(store, OWNER_A, 'account') as scope:
        first = admit(scope, units=10)
        first.finish(status='success', usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0})
        assert store.view(scope)['daily']['reported_tokens']['total_tokens'] == 0
        second = admit(scope, units=10)
        second.finish(status='success', usage={'prompt_tokens': 150, 'completion_tokens': 10, 'total_tokens': 1})
        assert store.view(scope)['daily']['budget_units'] == 170
        with pytest.raises(BudgetExceeded):
            admit(scope, 1)


@pytest.mark.parametrize('failure,expected', [(LLMTimeoutError('sensitive detail'), 'timeout'),
                                            (LLMRateLimitError('sensitive detail'), 'rate_limit'),
                                            (LLMAPIError('sensitive detail'), 'provider_error')])
def test_failed_attempts_keep_quota_but_not_error_bodies(store, monkeypatch, failure, expected):
    client, _ = fake_client(monkeypatch, [failure])
    with resource_scope(store, OWNER_A, 'account') as scope:
        with pytest.raises(LLMAPIError):
            client.call(retry=1)
        result = store.view(scope)
    assert result['daily']['attempts'] == 1 and result['daily']['budget_units'] > 0
    assert result['items'][0]['error_code'] == expected
    assert 'sensitive detail' not in json.dumps(result)


def test_every_retry_is_admitted_and_account_cap_prevents_second_http_call(store, monkeypatch):
    store.policy = replace(store.policy, account=Limits(1, 10_000, 2))
    client, calls = fake_client(monkeypatch, [LLMTimeoutError(), LLMResponse('unreachable')])
    with resource_scope(store, OWNER_A, 'account') as scope:
        with pytest.raises(BudgetExceeded):
            client.call(retry=2, timeout=5)
        assert store.view(scope)['daily']['attempts'] == 1
    assert len(calls) == 1


def test_json_parse_failure_does_not_erase_provider_usage_or_circumvent_quota(store, monkeypatch):
    client, _ = fake_client(monkeypatch, [LLMResponse('not json', usage={'total_tokens': 20})])
    with resource_scope(store, OWNER_A, 'account') as scope:
        with pytest.raises(LLMAPIError):
            client.call_structured(retry=1)
        result = store.view(scope)
    assert result['items'][0]['status'] == 'success'
    assert result['daily']['reported_tokens']['total_tokens'] == 20


def test_concurrency_is_shared_by_independent_store_objects_and_not_expired_by_time(store, monkeypatch):
    store.policy = replace(store.policy, global_limits=Limits(100, 100_000, 1))
    with resource_scope(store, OWNER_A, 'account') as scope:
        first = admit(scope)
    reopened = BudgetStore(store.path, store.policy)
    with resource_scope(reopened, OWNER_B, 'account') as other:
        with pytest.raises(BudgetExceeded, match='其他请求'):
            admit(other)
        from filemate import runtime_governance as governance
        now = governance.time.time()
        monkeypatch.setattr(governance.time, 'time', lambda: now + 2 * 86400)
        with pytest.raises(BudgetExceeded, match='其他请求'):
            admit(other)
        first.finish(status='failed', error_code='synthetic_cleanup')
        admit(other).finish(status='success')


def test_day_reset_is_utc_plus_eight_and_global_counter_survives_owner_erasure(store, monkeypatch):
    from filemate import runtime_governance as governance
    store.policy = replace(store.policy, account=Limits(1, 1000, 2), global_limits=Limits(2, 10_000, 4))
    midnight = datetime.fromisoformat('2026-10-11T00:00:00+08:00').timestamp()
    monkeypatch.setattr(governance.time, 'time', lambda: midnight - 1)
    with resource_scope(store, OWNER_A, 'account') as scope:
        admit(scope).finish(status='success')
        assert store.view(scope)['day'] == '2026-10-10'
        with pytest.raises(BudgetExceeded):
            admit(scope)
        monkeypatch.setattr(governance.time, 'time', lambda: midnight)
        admit(scope).finish(status='success')
        assert store.view(scope)['day'] == '2026-10-11'
    store.purge_owner_hash(owner_digest(OWNER_A))
    with resource_scope(store, OWNER_B, 'account') as scope:
        admit(scope).finish(status='success')
    store.purge_owner_hash(owner_digest(OWNER_B))
    with resource_scope(store, 'u_' + 'c' * 32, 'account') as scope, pytest.raises(BudgetExceeded):
        admit(scope)


def test_only_dead_process_leases_are_recovered_as_unknown(store, monkeypatch):
    from filemate import runtime_governance as governance
    with resource_scope(store, OWNER_A, 'account') as scope:
        first = admit(scope)
        monkeypatch.setattr(governance, '_alive', lambda *args: False)
        result = store.view(scope)
        assert result['items'][0]['status'] == 'abandoned'
        assert result['items'][0]['error_code'] == 'process_exit'
        assert result['items'][0]['total_tokens'] is None
        first.finish(status='success', usage={'total_tokens': 2})
        assert store.view(scope)['items'][0]['status'] == 'abandoned'


def test_settlement_failure_retains_lease_then_replays_idempotently(store, monkeypatch):
    with resource_scope(store, OWNER_A, 'account') as scope:
        first = admit(scope)
        original = store._settle
        monkeypatch.setattr(store, '_settle', lambda *args: (_ for _ in ()).throw(GovernanceUnavailable('synthetic failure')))
        with pytest.raises(GovernanceUnavailable):
            first.finish(status='success', usage={'total_tokens': 200})
        with pytest.raises(GovernanceUnavailable):
            admit(scope)
        monkeypatch.setattr(store, '_settle', original)
        result = store.view(scope)
        assert result['items'][0]['status'] == 'success'
        assert result['daily']['budget_units'] == 200
        assert result['daily']['attempts'] == 1 and store._pending == {}
        store.flush_pending()
        assert store.view(scope)['daily']['budget_units'] == 200


def test_corrupt_ledger_fails_closed_without_calling_provider(store, monkeypatch):
    store.path.parent.mkdir(parents=True)
    store.path.write_bytes(b'not a database')
    client, calls = fake_client(monkeypatch, [LLMResponse('unreachable')])
    with resource_scope(store, OWNER_A, 'account'), pytest.raises(GovernanceUnavailable):
        client.call(retry=1)
    assert calls == []


def test_future_ledger_version_is_rejected_without_rewriting(store):
    store.initialize()
    with sqlite3.connect(store.path) as connection:
        connection.execute('UPDATE resource_schema_migrations SET version=3 WHERE version=2')
    with resource_scope(store, OWNER_A, 'account') as scope, pytest.raises(GovernanceUnavailable, match='版本'):
        admit(scope)
    with sqlite3.connect(store.path) as connection:
        assert connection.execute('SELECT version FROM resource_schema_migrations ORDER BY version').fetchall() == [(1,), (3,)]


def _process_attempt(path, queue, owner):
    store = BudgetStore(path, Policy(account=Limits(10, 100_000, 10), global_limits=Limits(3, 100_000, 10)))
    try:
        with resource_scope(store, owner, 'account') as scope:
            admit(scope).finish(status='success')
        queue.put('admitted')
    except BudgetExceeded:
        queue.put('denied')


def test_multiple_processes_cannot_overrun_global_daily_budget(store):
    store.initialize()
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    processes = [context.Process(target=_process_attempt, args=(store.path, queue, f'u_{index:032x}')) for index in range(6)]
    try:
        for process in processes:
            process.start()
        results = [queue.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert results.count('admitted') == 3 and results.count('denied') == 3
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
        queue.close()


def test_threaded_admission_is_atomic_with_owner_cap(store):
    store.policy = replace(store.policy, account=Limits(2, 100_000, 10))

    def run(_):
        with resource_scope(store, OWNER_A, 'account') as scope:
            try:
                admit(scope).finish(status='success')
                return True
            except BudgetExceeded:
                return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(run, range(8))) == 2


def test_default_budget_supports_existing_four_worker_agent_flow(store, monkeypatch):
    from contextvars import copy_context
    barrier = threading.Barrier(4)
    client = LLMClient(LLMConfig(api_key='synthetic-only'))

    def chat(*args, **kwargs):
        barrier.wait(timeout=5)
        return LLMResponse('Synthetic successful worker', usage={'total_tokens': 10})

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat)
    with resource_scope(store, OWNER_A, 'guest') as scope, ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(copy_context().run, client.call, retry=1, timeout=10) for _ in range(4)]
        assert [job.result(timeout=15) for job in jobs] == ['Synthetic successful worker'] * 4
        rows = store.view(scope)['items']
        assert len(rows) == 4 and all(row['status'] == 'success' for row in rows)
        assert len({row['trace_id'] for row in rows}) == 1


@pytest.mark.parametrize('invalid', [0, -1, True, 1.2, 100_001])
def test_budget_policy_rejects_disable_values_and_invalid_limits(invalid):
    with pytest.raises(ValueError):
        Policy(account=Limits(invalid, 100, 1))


def test_missing_production_scope_is_rejected_but_local_scope_is_metered(monkeypatch, tmp_path):
    monkeypatch.setenv('FILEMATE_ENV', 'production')
    with pytest.raises(GovernanceUnavailable, match='可信学习空间'):
        default_scope()
    monkeypatch.setenv('FILEMATE_ENV', 'development')
    scope = default_scope()
    admit(scope).finish(status='success')
    assert scope.store.path.is_relative_to(tmp_path)
    assert scope.store.view(scope)['daily']['attempts'] == 1


def test_usage_api_is_owner_bound_paginated_and_rejects_bad_limits(account_server):
    module = account_server
    with resource_scope(module._model_budget, OWNER_A, 'account') as scope:
        admit(scope).finish(status='success')
    with TestClient(module.app) as owner, TestClient(module.app) as other:
        assert register(owner).status_code == 200
        workspace = module._accounts.resolve_session(owner.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        with resource_scope(module._model_budget, workspace, 'account') as scope:
            for _ in range(3):
                admit(scope).finish(status='success', usage={'total_tokens': 10})
        response = owner.get(f'/api/llm/usage?owner={OWNER_A}&limit=1&offset=1')
        assert response.headers['Cache-Control'] == 'no-store'
        page = response.json()['data']
        assert len(page['items']) == 1 and page['total'] == 3
        assert page['daily']['attempts'] == 3
        assert other.get('/api/llm/usage').json()['data']['total'] == 0
        assert owner.get('/api/llm/usage?limit=101').status_code == 422
        assert owner.get('/api/llm/usage?offset=-1').status_code == 422


def test_personal_restore_does_not_reset_budget_or_change_pending_preview(server_module):
    module, _ = server_module
    with TestClient(module.app) as client:
        raw = client.get('/api/privacy/export').content
        preview = client.post('/api/privacy/restore-preview', files={'file': ('own.zip', raw)}).json()['data']
        with resource_scope(module._model_budget, 'local', 'local') as scope:
            admit(scope).finish(status='success', usage={'total_tokens': 9})
        result = client.post('/api/privacy/restore', json={'backup_id': preview['backup_id'], 'confirmation_token': preview['confirmation_token'], 'confirmed': True})
        assert result.status_code == 200 and result.json()['data']['restored']
        assert client.get('/api/llm/usage').json()['data']['daily']['attempts'] == 1
        exported = client.get('/api/privacy/export?format=json').json()
        assert exported['model_usage']['items'][0]['total_tokens'] == 9
        import zipfile
        with zipfile.ZipFile(io.BytesIO(client.get('/api/privacy/export').content)) as archive:
            assert json.loads(archive.read('model-usage.json'))['total'] == 1
            assert not {'ai_attempts', 'resource_daily'} & json.loads(archive.read('personal-data.json'))['tables'].keys()


def test_ledger_outage_does_not_break_health_business_reads_or_core_export(account_server, monkeypatch):
    module = account_server
    monkeypatch.setattr(module._model_budget, 'initialize', lambda: (_ for _ in ()).throw(GovernanceUnavailable('synthetic outage')))
    with TestClient(module.app) as client:
        assert client.get('/api/llm/usage').status_code == 503
        assert client.get('/api/health').status_code == 200
        assert client.get('/knowledge/sources').status_code == 200
        assert client.get('/api/privacy/export?format=json').json()['model_usage'] == {'available': False, 'reason': 'usage_export_unavailable'}


def test_account_erasure_deletes_owned_usage_but_preserves_other_owner_and_global(account_server):
    module = account_server
    from filemate.tests.test_p1_account_privacy import proposal
    with TestClient(module.app) as client:
        assert register(client).status_code == 200
        owner = module._accounts.resolve_session(client.cookies.get(module.ACCOUNT_COOKIE_NAME))['workspace_id']
        with resource_scope(module._model_budget, owner, 'account') as scope:
            admit(scope).finish(status='success')
        with resource_scope(module._model_budget, OWNER_B, 'account') as scope:
            admit(scope).finish(status='success')
        result = client.post('/api/auth/delete', headers={'X-FileMate-Action': 'account'}, json=proposal(client))
        assert result.json()['data'] == {'deleted': True, 'cleanup_pending': False}
    with resource_scope(module._model_budget, owner, 'account') as scope:
        assert module._model_budget.view(scope)['total'] == 0
    with resource_scope(module._model_budget, OWNER_B, 'account') as scope:
        assert module._model_budget.view(scope)['total'] == 1
    with sqlite3.connect(module._model_budget.path) as connection:
        assert connection.execute("SELECT attempts FROM resource_daily WHERE owner_hash='__global__'").fetchone()[0] == 2


def test_failed_ledger_erasure_is_visible_and_retryable(tmp_path):
    failures = []

    def erase(digest):
        failures.append(digest)
        if len(failures) == 1:
            raise GovernanceUnavailable('synthetic failure')

    deletion = WorkspaceDeletion(tmp_path, b'synthetic-privacy-signing-secret-0000', erase)
    identifier = hashlib.sha256(b'synthetic-deletion').hexdigest()
    deletion._write(deletion.actions / (identifier + '.json'), {'state': 'staged', 'workspace_hash': owner_digest(OWNER_A), 'workspace_id': OWNER_A, 'account_id': 'synthetic-account'})
    assert deletion._finish_identifier(identifier) == {'deleted': True, 'cleanup_pending': True}
    assert deletion.retry_cleanup() == 0
    assert failures == [owner_digest(OWNER_A)] * 2


def test_admin_backup_includes_and_restores_ledger_separately(managed, tmp_path):
    store = BudgetStore(managed / 'control/resource-governance.db')
    with resource_scope(store, OWNER_A, 'account') as scope:
        admit(scope).finish(status='success', usage={'total_tokens': 10})
    plan = backup.plan_backup(managed)
    created = backup.create_backup(managed, tmp_path / 'snapshot', plan['confirmation'], quiesced=True)
    assert created['passed']
    assert backup.verify_backup(tmp_path / 'snapshot')['passed']
    restore = backup.plan_restore(tmp_path / 'snapshot', tmp_path / 'restored')
    result = backup.restore_backup(tmp_path / 'snapshot', tmp_path / 'restored', restore['confirmation'])
    assert result['passed']
    restored = BudgetStore(tmp_path / 'restored/control/resource-governance.db')
    with resource_scope(restored, OWNER_A, 'account') as scope:
        assert restored.view(scope)['daily']['attempts'] == 1
    summary = backup._summary(created)
    assert summary['schema_versions'] == [26] and summary['resource_schema_versions'] == [2]


def test_restored_ledger_cannot_resurrect_erased_owner_usage(store, tmp_path):
    with resource_scope(store, OWNER_A, 'account') as scope:
        admit(scope).finish(status='success')
    with resource_scope(store, OWNER_B, 'account') as scope:
        admit(scope).finish(status='success')
    deletion = WorkspaceDeletion(tmp_path, b'synthetic-privacy-signing-secret-0000',
                                 store.purge_owner_hash, store.owner_hashes)
    deletion._write(deletion.tombstones / (owner_digest(OWNER_A) + '.json'),
                    {'state': 'erased', 'action_id': 'a' * 64})
    assert deletion.retry_cleanup() == 0
    with resource_scope(store, OWNER_A, 'account') as scope:
        assert store.view(scope)['total'] == 0
    with resource_scope(store, OWNER_B, 'account') as scope:
        assert store.view(scope)['total'] == 1


def test_retention_removes_only_expired_terminal_records(store, monkeypatch):
    from filemate import runtime_governance as governance
    now = governance.time.time()
    with resource_scope(store, OWNER_A, 'account') as scope:
        admit(scope).finish(status='success')
        live = admit(scope)
        monkeypatch.setattr(governance.time, 'time', lambda: now + 31 * 86400)
        store.maintain()
        result = store.view(scope)
        assert len(result['items']) == 1 and result['items'][0]['status'] == 'inflight'
        assert result['items'][0]['attempt_id'] == live.identifier
        live.finish(status='failed', error_code='synthetic_cleanup')


def test_model_connection_budget_errors_are_not_misclassified_as_invalid_keys(account_server, monkeypatch):
    module = account_server
    from filemate.llm_client import LLMConfig
    monkeypatch.setattr(LLMConfig, 'from_env', lambda: LLMConfig(api_key='synthetic-only'))
    with TestClient(module.app) as client:
        monkeypatch.setattr(LLMClient, 'call', lambda *a, **k: (_ for _ in ()).throw(BudgetExceeded('今日额度已用完')))
        headers = {'Origin': module.CORS_ORIGINS[0], 'X-FileMate-Action': 'model'}
        assert client.post('/api/llm/test', headers=headers).status_code == 429
        monkeypatch.setattr(LLMClient, 'call', lambda *a, **k: (_ for _ in ()).throw(GovernanceUnavailable('账本暂不可用')))
        assert client.post('/api/llm/test', headers=headers).status_code == 503
        assert client.get('/api/health').status_code == 200


@pytest.mark.asyncio
async def test_tts_consumes_attempts_without_fabricated_tokens_and_cancel_releases_lease(store, monkeypatch):
    voice = MicrosoftSpeech()

    async def success(*args):
        return b'synthetic audio'

    monkeypatch.setattr(voice, '_collect', success)
    with resource_scope(store, OWNER_A, 'account') as scope:
        assert await voice.synthesize('Synthetic voice text', 'zh-CN-XiaoxiaoNeural', OWNER_A)
        assert store.view(scope)['daily']['reported_tokens']['total_tokens'] is None
        assert store.view(scope)['daily']['budget_units'] == 0
        started = asyncio.Event()

        async def hold(*args):
            started.set()
            await asyncio.sleep(30)

        monkeypatch.setattr(voice, '_collect', hold)
        task = asyncio.create_task(voice.synthesize('Synthetic voice text', 'zh-CN-YunxiaNeural', OWNER_A))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = store.view(scope)
        assert result['daily']['attempts'] == 2
        assert all(item['status'] != 'inflight' for item in result['items'])
        assert 'Synthetic voice text' not in json.dumps(result)


@pytest.mark.asyncio
async def test_tts_failure_is_metered_and_quota_denial_never_contacts_provider(store, monkeypatch):
    voice, calls = MicrosoftSpeech(), []
    store.policy = replace(store.policy, account=Limits(1, 100, 1))

    async def failure(*args):
        calls.append(1)
        raise RuntimeError('synthetic private error')

    monkeypatch.setattr(voice, '_collect', failure)
    with resource_scope(store, OWNER_A, 'account') as scope:
        with pytest.raises(SpeechUnavailable):
            await voice.synthesize('Synthetic text', 'zh-CN-XiaoxiaoNeural', OWNER_A)
        with pytest.raises(BudgetExceeded):
            await voice.synthesize('Synthetic text', 'zh-CN-XiaoxiaoNeural', OWNER_A)
        assert store.view(scope)['items'][0]['error_code'] == 'speech_error'
    assert calls == [1]
