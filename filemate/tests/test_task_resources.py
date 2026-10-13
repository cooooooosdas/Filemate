# ruff: noqa: F811
"""合成回归：任务及代码执行的日预算、跨进程竞争、恢复和拒绝边界。"""

import ast
import json
import multiprocessing
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from filemate.career.catalog import CATALOG
from filemate.career.planning import CareerPlans
from filemate.career.repository import CareerRepository
from filemate.execution.storage import SQLiteStorage
from filemate.operations import backup
from filemate.programming import service
from filemate.programming.problems import get_problem
from filemate.programming.repository import CodingRepository
from filemate.programming.windows_sandbox import SandboxUnavailable
from filemate.runtime_governance import (
    _SCHEMA,
    BudgetExceeded,
    BudgetStore,
    GovernanceUnavailable,
    Policy,
    ResourceLimits,
    owner_digest,
    resource_schema_version,
    resource_scope,
)
from filemate.task_resources import admit_tasks, execution_budget, task_inventory
from filemate.tests.test_p1_semester import CONFIG
from filemate.tests.test_server_persistence import server_module  # noqa: F401

OWNER_A = 'u_' + 'a' * 32
OWNER_B = 'u_' + 'b' * 32


@pytest.fixture
def resources(tmp_path):
    business = SQLiteStorage(tmp_path / 'business.db')
    business.init_schema()
    store = BudgetStore(tmp_path / 'control/resource-governance.db')
    yield business, store
    business.close()


def limited(store, tasks=10, executions=2, concurrent=1):
    limits = ResourceLimits(tasks, executions, concurrent)
    store.policy = replace(store.policy, resources_account=limits, resources_local=limits)


def plan(tasks):
    return {'daily_plan': [{'day': 1, 'date': '2026-10-11', 'tasks': tasks}],
            'title': 'Synthetic plan', 'exam_date': '2026-10-20', 'daily_minutes': 30}


def _child_admission(path, queue):
    store = BudgetStore(Path(path), Policy(resources_account=ResourceLimits(3, 1, 1)))
    try:
        with resource_scope(store, OWNER_A, 'account') as scope:
            store.admit_resource(scope, 'tasks')
        queue.put('admitted')
    except BudgetExceeded:
        queue.put('denied')


def test_v1_migration_preserves_daily_model_budget_and_coverage(resources):
    _, store = resources
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        conn.execute('INSERT INTO resource_schema_migrations VALUES(1,12345)')
        conn.execute("INSERT INTO resource_daily VALUES('synthetic-owner','2026-10-11',7,321)")
        assert resource_schema_version(conn) == 1
    before = backup._database_facts(store.path)
    assert before['schema_version'] == 1
    store.initialize()
    store.initialize()
    with sqlite3.connect(store.path) as conn:
        assert conn.execute('SELECT * FROM resource_daily').fetchone() == ('synthetic-owner', '2026-10-11', 7, 321, 0, 0)
        assert conn.execute('SELECT applied_at FROM resource_schema_migrations WHERE version=1').fetchone() == (12345,)
        assert resource_schema_version(conn) == 2
    assert backup._database_facts(store.path)['schema_version'] == 2


def test_broken_v1_migration_rolls_back_without_partial_columns(resources):
    _, store = resources
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        conn.execute('INSERT INTO resource_schema_migrations VALUES(1,12345)')
        conn.execute('ALTER TABLE resource_daily ADD COLUMN execution_admissions INTEGER DEFAULT 0')
    with pytest.raises(sqlite3.OperationalError):
        store.initialize()
    with sqlite3.connect(store.path) as conn:
        assert 'task_admissions' not in {row[1] for row in conn.execute('PRAGMA table_info(resource_daily)')}
        assert conn.execute('SELECT version FROM resource_schema_migrations').fetchall() == [(1,)]


@pytest.mark.parametrize('field,value', [('task_admissions', 0), ('execution_admissions', -1),
                                        ('execution_concurrent', True), ('execution_concurrent', 17)])
def test_resource_configuration_rejects_unbounded_or_disabled_limits(field, value):
    with pytest.raises(ValueError):
        Policy(resources_guest=replace(ResourceLimits(2, 2, 1), **{field: value}))


def test_resource_environment_contract(monkeypatch):
    monkeypatch.setenv('FILEMATE_RESOURCE_GUEST_DAILY_TASKS', '1501')
    monkeypatch.setenv('FILEMATE_RESOURCE_GLOBAL_DAILY_EXECUTIONS', '11')
    policy = Policy.from_env()
    assert policy.resources_guest.task_admissions == 1501
    assert policy.resources_global.execution_admissions == 11


def test_task_batch_is_atomic_and_failed_admission_changes_no_business_data(resources):
    business, store = resources
    limited(store, tasks=2)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        with pytest.raises(BudgetExceeded):
            business.save_artifact(artifact_type='study_plan', content=plan(['one', 'two', 'three']))
        assert business.list_artifacts() == []
        assert store.view(scope)['resources']['task_admissions'] == 0
        identifier = business.save_artifact(artifact_type='study_plan', content=plan(['one', 'two']))
        before = business.get_artifact(identifier)
        with pytest.raises(BudgetExceeded):
            business.update_artifact(identifier, title='rejected', content=plan(['one', 'two', 'three']))
        assert business.get_artifact(identifier) == before
        assert store.view(scope)['resources']['task_admissions'] == 2


def test_completion_and_duplicate_tasks_have_correct_creation_counts(resources):
    business, store = resources
    limited(store, tasks=2)
    body = {'tasks': [{'task_id': 'same-id', 'title': 'same title', 'status': 'pending'}] * 2}
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        aid = business.save_artifact(artifact_type='reverse_goal_plan', content=body)
        updated = deepcopy(body)
        updated['tasks'][0]['status'] = 'completed'
        business.update_artifact(aid, title='renamed', content=updated)
        assert store.view(scope)['resources']['task_admissions'] == 2
        assert sum(task_inventory(updated).values()) == 2
        updated['tasks'].append({'task_id': 'same-id', 'title': 'same title', 'status': 'pending'})
        with pytest.raises(BudgetExceeded):
            business.update_artifact(aid, title='same', content=updated)


def test_artifact_and_plan_record_are_not_double_charged(resources):
    business, store = resources
    limited(store, tasks=1)
    data = plan(['one'])
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        aid = business.save_artifact(artifact_type='study_plan', content=data)
        saved = business.create_study_plan(artifact_id=aid, source_id=None, plan=data)
        assert business.create_study_plan(artifact_id=aid, source_id=None, plan=data) == saved
        assert store.view(scope)['resources']['task_admissions'] == 1


def test_file_processing_sessions_are_bounded_and_idempotent(resources):
    business, store = resources
    limited(store, tasks=1)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        business.create_session('synthetic-session', 'synthetic-private-file.txt')
        business.create_session('synthetic-session', 'synthetic-private-file.txt')
        with pytest.raises(BudgetExceeded):
            business.create_session('rejected-session', 'another-file.txt')
        assert business.get_session('rejected-session') is None
        business.update_session('synthetic-session', status='skipped')
        assert store.view(scope)['resources']['task_admissions'] == 1


def test_cross_process_daily_task_limit_is_shared(resources):
    _, store = resources
    context = multiprocessing.get_context('spawn')
    queue = context.Queue()
    children = [context.Process(target=_child_admission, args=(str(store.path), queue)) for _ in range(6)]
    for child in children:
        child.start()
    results = [queue.get(timeout=60) for _ in children]
    for child in children:
        child.join(timeout=10)
        assert child.exitcode == 0
    assert results.count('admitted') == 3 and results.count('denied') == 3
    with resource_scope(store, OWNER_A, 'account') as scope:
        assert store.view(scope)['resources']['task_admissions'] == 3


def test_global_task_budget_survives_owner_erasure(resources):
    _, store = resources
    store.policy = replace(store.policy, resources_global=ResourceLimits(2, 10, 2))
    with resource_scope(store, OWNER_A, 'account') as scope:
        store.admit_resource(scope, 'tasks', 2)
        store.purge_owner_hash(scope.owner_hash)
        assert store.export(scope)['resource_events'] == []
    with resource_scope(store, OWNER_B, 'account') as scope, pytest.raises(BudgetExceeded):
        store.admit_resource(scope, 'tasks')


def test_wrong_database_and_unbound_production_operations_are_rejected(resources, monkeypatch):
    business, store = resources
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path), pytest.raises(GovernanceUnavailable, match='不一致'):
        admit_tasks(business.db_path.parent / 'someone-else.db', 1)
    monkeypatch.setenv('FILEMATE_ENV', 'production')
    with pytest.raises(GovernanceUnavailable):
        admit_tasks(business.db_path, 1)
    with resource_scope(store, OWNER_A, 'account'), pytest.raises(GovernanceUnavailable, match='绑定'):
        admit_tasks(business.db_path, 1)


def test_privacy_audit_records_do_not_depend_on_quotas(resources, monkeypatch):
    business, store = resources
    store.path.parent.mkdir(parents=True)
    store.path.write_bytes(b'corrupt ledger')
    monkeypatch.setenv('FILEMATE_ENV', 'production')
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path):
        for kind in ('memory_deletion', 'source_rights'):
            assert business.create_agent_run(task_type=kind, goal='Synthetic privacy action', selected_agents=[])['run_id']
        with pytest.raises(GovernanceUnavailable):
            business.create_agent_run(task_type='study_plan', goal='new task', selected_agents=[])
        assert len(business.list_agent_runs()) == 2


def test_execution_failure_releases_concurrency_but_not_daily_counter(resources):
    business, store = resources
    limited(store, executions=1)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        with pytest.raises(RuntimeError), execution_budget(business.db_path):
            raise RuntimeError('Synthetic private code must not be retained')
        report = store.export(scope)
        assert report['resources']['execution_admissions'] == 1
        assert report['resource_events'][0]['status'] == 'failed'
        assert report['resource_events'][0]['error_code'] == 'RuntimeError'
        assert 'private code' not in json.dumps(report)
        with pytest.raises(BudgetExceeded), execution_budget(business.db_path):
            pytest.fail('quota should deny before execution')


def test_execution_concurrency_shared_between_stores(resources):
    business, store = resources
    limited(store, executions=3)
    second = BudgetStore(store.path, store.policy)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path):
        with execution_budget(business.db_path):  # noqa: SIM117 -- 内层完成后验证并发位恢复。
            with resource_scope(second, OWNER_A, 'account', managed_db_path=business.db_path), pytest.raises(BudgetExceeded):
                with execution_budget(business.db_path):
                    pytest.fail('shared concurrency should deny')
        with execution_budget(business.db_path):
            pass


def test_windows_forced_selftest_cannot_bypass_execution_budget(resources, monkeypatch):
    business, store = resources
    limited(store, executions=1)
    calls = []

    class Probe:
        def __init__(self, _root):
            pass

        def ready(self):
            return True

        def judge(self, *args):
            calls.append('selftest')
            return {'verdict': 'AC'}

    monkeypatch.setattr(service, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(service, 'toolchain_root', lambda: business.db_path.parent)
    monkeypatch.setattr(service, 'discover_msvc', lambda: None)
    monkeypatch.setattr(service, 'network_isolation_available', lambda: True)
    monkeypatch.setattr(service, 'WindowsCppJudge', Probe)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path):
        assert service.status(force=True)['ready']
        assert service.status()['ready']
        with pytest.raises(BudgetExceeded):
            service.status(force=True)
        assert calls == ['selftest']


def test_failed_execution_settlement_keeps_lease_until_maintenance(resources, monkeypatch):
    business, store = resources
    limited(store, executions=3)
    original = store._settle
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        monkeypatch.setattr(store, '_settle', lambda *args: (_ for _ in ()).throw(GovernanceUnavailable('synthetic outage')))
        with execution_budget(business.db_path):
            pass
        assert len(store._pending) == 1
        with sqlite3.connect(store.path) as conn:
            assert conn.execute("SELECT status FROM resource_events WHERE kind='execution'").fetchone() == ('inflight',)
        monkeypatch.setattr(store, '_settle', original)
        store.maintain()
        assert store._pending == {}
        assert store.export(scope)['resource_events'][0]['status'] == 'success'
        with execution_budget(business.db_path):
            pass


def test_ten_thousand_terminal_events_do_not_force_inflight_table_scan(resources):
    _, store = resources
    store.initialize()
    now = time.time()
    with store._connection() as conn:
        conn.executemany("""INSERT INTO resource_events(event_id,trace_id,owner_hash,day,operation,kind,amount,
            started_at,finished_at,status,pid,process_started_at) VALUES(?,?,?,?,?,'tasks',1,?,?,'admitted',1,1)""",
                         [(f'{index:032x}', 'synthetic-load', owner_digest(OWNER_B), store._day(now),
                           'synthetic.load', now, now) for index in range(10000)])
        trace = []
        conn.set_trace_callback(trace.append)
        store._cleanup(conn, now, store.policy.retention_days)
        conn.set_trace_callback(None)
        query = next(sql for sql in trace if 'SELECT DISTINCT pid,process_started_at FROM resource_events' in sql)
        strategy = conn.execute('EXPLAIN QUERY PLAN ' + query).fetchall()
        assert any('SEARCH resource_events USING INDEX' in row[3] for row in strategy)
        assert conn.execute('SELECT COUNT(*) FROM resource_events').fetchone()[0] == 10000


def test_dead_execution_lease_is_reclaimed_but_live_lease_never_expires(resources, monkeypatch):
    business, store = resources
    limited(store, executions=3)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        lease = store.admit_resource(scope, 'execution')
        with store._connection() as conn:
            conn.execute('UPDATE resource_events SET started_at=? WHERE event_id=?', (time.time() - 100 * 86400, lease.identifier))
        with pytest.raises(BudgetExceeded):
            store.admit_resource(scope, 'execution')
        with store._connection() as conn:
            conn.execute('UPDATE resource_events SET pid=2147483647 WHERE event_id=?', (lease.identifier,))
        assert store.export(scope)['resource_events'][0]['status'] == 'abandoned'
        with execution_budget(business.db_path):
            pass


def test_personal_restore_does_not_replenish_task_or_execution_budget(server_module):
    module, business = server_module
    limited(module._model_budget, tasks=1, executions=1)
    with TestClient(module.app) as client:
        raw = client.get('/api/privacy/export').content
        preview = client.post('/api/privacy/restore-preview', files={'file': ('synthetic.zip', raw)}).json()['data']
        with resource_scope(module._model_budget, 'local', 'local', managed_db_path=business.db_path):
            admit_tasks(business.db_path, 1)
            with execution_budget(business.db_path):
                pass
        restored = client.post('/api/privacy/restore', json={'backup_id': preview['backup_id'],
                               'confirmation_token': preview['confirmation_token'], 'confirmed': True})
        assert restored.status_code == 200 and restored.json()['data']['restored']
        report = client.get('/api/llm/usage').json()['data']['resources']
        assert report['task_admissions'] == 1 and report['execution_admissions'] == 1
        with resource_scope(module._model_budget, 'local', 'local', managed_db_path=business.db_path), pytest.raises(BudgetExceeded):
            admit_tasks(business.db_path, 1)


def test_compiler_failure_then_daily_denial_preserves_queued_code(resources, monkeypatch):
    business, store = resources
    limited(store, tasks=10, executions=1)
    repo = CodingRepository(business)
    calls = []

    class BrokenJudge:
        def judge(self, *args):
            calls.append('called')
            raise SandboxUnavailable('Synthetic unavailable compiler')

    monkeypatch.setattr(service, 'WindowsCppJudge', BrokenJudge)
    monkeypatch.setattr(service, 'LinuxCppJudge', BrokenJudge)
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path):
        first = repo.create(get_problem('array-sum'), 'int main(){}', 'first-key-12345678')
        with pytest.raises(SandboxUnavailable):
            service.execute(repo, first['submission_id'])
        assert repo.get(first['submission_id'])['status'] == 'failed'
        second = repo.create(get_problem('array-sum'), 'int main(){return 1;}', 'second-key-12345678')
        with pytest.raises(BudgetExceeded):
            service.execute(repo, second['submission_id'])
        preserved = repo.get(second['submission_id'])
        assert preserved['status'] == 'queued' and preserved['code'] == second['code']
        assert calls == ['called']
        assert repo.transition(second['submission_id'], 'cancel')['status'] == 'cancelled'


def test_two_connections_claim_same_submission_only_once(resources):
    business, _ = resources
    repo = CodingRepository(business)
    row = repo.create(get_problem('array-sum'), 'int main(){}', 'atomic-claim-key')
    barrier = threading.Barrier(2)

    def claim():
        store = SQLiteStorage(business.db_path)
        try:
            barrier.wait(timeout=10)
            return CodingRepository(store).start(row['submission_id'])[1]
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: claim(), range(2))) == [False, True]
    assert sum(event['action'] == 'started' for event in repo.events()) == 1


def test_semester_batch_denial_preserves_confirmation_and_idempotence(server_module):
    module, business = server_module
    limited(module._model_budget, tasks=4)
    with TestClient(module.app) as client:
        preview = client.post('/api/semester/preview', json=CONFIG).json()['data']
        request = {'config': CONFIG, 'confirmed': True, 'confirmation_token': preview['confirmation_token']}
        assert client.post('/api/semester/confirm', json=request).status_code == 429
        assert client.get('/api/semester').json()['data'] is None
        assert client.get('/api/llm/usage').json()['data']['resources']['task_admissions'] == 0
        limited(module._model_budget, tasks=5)
        first = client.post('/api/semester/confirm', json=request)
        assert first.status_code == 200
        assert client.post('/api/semester/confirm', json=request).json() == first.json()
        assert client.get('/api/llm/usage').json()['data']['resources']['task_admissions'] == 5
        task = client.get('/api/semester').json()['data']['tasks'][0]
        assert client.patch(f"/api/semester/tasks/{task['task_id']}", json={'revision': 1, 'completed': True}).status_code == 200
        assert client.get('/api/llm/usage?offset=9999999999999999999999').status_code == 422
    assert business._conn().execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type='semester'").fetchone()[0] == 1


def test_career_training_and_plan_confirmations_count_once(resources):
    business, store = resources
    career = CareerRepository(business)
    row = career.create(CATALOG[0] | {'source_kind': 'user_import', 'source': 'Synthetic fixture'}, 'synthetic-position-key')
    with resource_scope(store, OWNER_A, 'account', managed_db_path=business.db_path) as scope:
        trained = career.start(row['position_id'], 'written', 'synthetic-training-key', row['revision'])
        assert career.start(row['position_id'], 'written', 'synthetic-training-key', row['revision']) == trained
        planner = CareerPlans(career)
        preview = planner.preview(row['position_id'])
        expected = 1 + sum(task_inventory(preview['plan']).values())
        saved = planner.save(row['position_id'], preview['evidence_revision'])
        assert planner.save(row['position_id'], preview['evidence_revision']) == saved
        assert store.view(scope)['resources']['task_admissions'] == expected


def test_deployment_facts_reads_both_control_versions_without_migrating(resources):
    _, store = resources
    source = Path('scripts/deploy_existing.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'database_facts')
    from contextlib import closing
    namespace = {'Path': Path, 'Any': object, 'closing': closing, 'sqlite3': sqlite3}
    exec(compile(ast.Module(body=[node], type_ignores=[]), source, 'exec'), namespace)  # noqa: S102 -- 仅载入当前仓库受信的只读校验函数。
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as conn:
        for statement in _SCHEMA:
            conn.execute(statement)
        conn.execute('INSERT INTO resource_schema_migrations VALUES(1,12345)')
    assert namespace['database_facts'](store.path)['schema_version'] == 1
    store.initialize()
    assert namespace['database_facts'](store.path)['schema_version'] == 2
