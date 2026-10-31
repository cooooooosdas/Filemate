"""Real transactional retry, concurrency, rollback and undo regressions."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

from .conftest import module, scope, snapshot


def command(world, store=None):
    return module('commands').OrchestratorCommands(store or world['store'], clock=lambda: world['now'][0])


def prepared(world, minutes=30):
    models = module('models')
    request = models.PreviewRequest(scope=scope(world), expected_evidence_revision=snapshot(world).evidence_revision,
                                    options=models.ScheduleOptions(available_minutes=minutes))
    preview = command(world).preview(request)
    return models.ConfirmRequest(**request.model_dump(), confirmation_token=preview.confirmation_token,
                                 request_key='synthetic-confirm-0001', confirmed=True)


def test_preview_only_persists_token_not_tasks(world):
    store = world['store']
    count = store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
    prepared(world)
    assert store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == count
    assert store._conn().execute('SELECT COUNT(*) FROM data_action_previews').fetchone()[0] == 1


def test_today_preserves_confirmed_user_time_estimate(world):
    models = module('models')
    tid = f"goal:{world['goal']}:review-source"
    request = models.PreviewRequest(scope=scope(world), expected_evidence_revision=snapshot(world).evidence_revision,
        options=models.ScheduleOptions(available_minutes=30, minute_overrides={tid: 7}))
    preview = command(world).preview(request)
    command(world).confirm(models.ConfirmRequest(**request.model_dump(), confirmation_token=preview.confirmation_token,
        request_key='synthetic-override-confirm', confirmed=True))
    day = module('repository').OrchestratorRepository(world['store'], clock=lambda: world['now'][0]).today(date(2026, 10, 31))
    saved = next(t for t in day.selected if t.task_id == tid)
    assert (saved.estimated_minutes, saved.estimate_source) == (7, 'user_estimate')


def test_confirm_replay_and_changed_body(world):
    request = prepared(world)
    cmd = command(world)
    first = cmd.confirm(request)
    assert cmd.confirm(request) == first
    assert module('repository').OrchestratorRepository(world['store']).find_request(request.request_key) == first
    changed = request.model_copy(update={'options': module('models').ScheduleOptions(available_minutes=0)})
    with pytest.raises(module('models').OrchestratorError):
        cmd.confirm(changed)


def test_two_storage_instances_only_one_revision_wins(world):
    from filemate.execution.storage import SQLiteStorage
    request = prepared(world)
    second_request = prepared(world, 20).model_copy(update={'request_key': 'synthetic-confirm-0002'})
    other = SQLiteStorage(world['store'].db_path)

    def attempt(pair):
        store, body = pair
        try:
            return command(world, store).confirm(body).status
        except module('models').OrchestratorError:
            return 'conflict'
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [(world['store'], request), (other, second_request)]))
        assert sorted(results) == ['confirmed', 'conflict']
    finally:
        other.close()


def test_lost_response_recovers_without_second_apply(world):
    request = prepared(world)
    first = command(world).confirm(request)
    recovered = module('repository').OrchestratorRepository(world['store']).find_request(request.request_key)
    assert recovered == first
    assert world['store']._conn().execute("SELECT COUNT(*) FROM data_action_audit WHERE action='orchestrator_confirm'").fetchone()[0] == 1


def test_undo_preserves_new_completion(world):
    request = prepared(world)
    cmd = command(world)
    receipt = cmd.confirm(request)
    goal = world['store'].get_artifact(world['goal'])
    goal['content']['tasks'][0]['status'] = 'completed'
    world['store'].update_artifact(world['goal'], title='', content=goal['content'])
    token = cmd.preview_undo(receipt.operation_id).confirmation_token
    cmd.confirm_undo(receipt.operation_id, module('models').UndoConfirmRequest(confirmation_token=token, request_key='synthetic-undo-000001', confirmed=True))
    assert world['store'].get_artifact(world['goal'])['content']['tasks'][0]['status'] == 'completed'
    assert module('repository').OrchestratorRepository(world['store']).today(date(2026, 10, 31)).status == 'not_confirmed'


def test_retry_after_undo_never_reapplies(world):
    request = prepared(world)
    cmd = command(world)
    original = cmd.confirm(request)
    token = cmd.preview_undo(original.operation_id).confirmation_token
    undo = module('models').UndoConfirmRequest(confirmation_token=token, request_key='synthetic-undo-000001', confirmed=True)
    first = cmd.confirm_undo(original.operation_id, undo)
    assert cmd.confirm_undo(original.operation_id, undo) == first
    assert cmd.confirm(request).status == 'undone'


def test_source_delete_or_midnight_invalidates_preview(world):
    request = prepared(world)
    world['now'][0] += timedelta(days=1)
    with pytest.raises(module('models').OrchestratorError):
        command(world).confirm(request)
    world['now'][0] -= timedelta(days=1)
    conn = world['store']._conn()
    conn.execute('DELETE FROM sources WHERE source_id=?', (world['sources'][0],)); conn.commit()
    with pytest.raises(module('models').OrchestratorError):
        command(world).confirm(request)


def test_write_failure_rolls_back_artifact_token_and_audit(world):
    request = prepared(world)
    conn = world['store']._conn()
    conn.execute("CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON data_action_audit BEGIN SELECT RAISE(ABORT,'synthetic'); END")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        command(world).confirm(request)
    assert conn.execute("SELECT COUNT(*) FROM artifacts WHERE artifact_type LIKE 'learning_orchestration_%'").fetchone()[0] == 0
    assert conn.execute('SELECT result FROM data_action_previews').fetchone()[0] is None


def test_reserved_artifacts_cannot_be_edited_or_retyped(world):
    receipt = command(world).confirm(prepared(world))
    store = world['store']
    for kind in ('learning_orchestration_day', 'learning_orchestration_operation'):
        with pytest.raises(ValueError):
            store.save_artifact(artifact_type=kind, content={})
    for mutation in (lambda: store.update_artifact(receipt.operation_id, title='changed', content={}),
                     lambda: store.save_artifact(artifact_id=receipt.operation_id, artifact_type='summary', content={})):
        with pytest.raises(ValueError):
            mutation()


def test_receipt_replay_next_day_does_not_apply_again(world):
    request = prepared(world)
    first = command(world).confirm(request)
    world['now'][0] += timedelta(days=1)
    assert command(world).confirm(request) == first


def test_generic_save_cannot_win_retyping_race(world, monkeypatch):
    from filemate.execution.storage import SQLiteStorage
    store = world['store']
    other = SQLiteStorage(store.db_path)
    original = store.get_artifact
    target = 'synthetic-reserved-race'
    def raced(identifier):
        if identifier == target:
            with other._conn() as conn:
                conn.execute("INSERT INTO artifacts(artifact_id,artifact_type,content) VALUES(?,'learning_orchestration_day','{}')", (target,))
            return None
        return original(identifier)
    monkeypatch.setattr(store, 'get_artifact', raced)
    try:
        with pytest.raises(ValueError):
            store.save_artifact(artifact_id=target, artifact_type='summary', content={'tampered': True})
        assert other.get_artifact(target)['artifact_type'] == 'learning_orchestration_day'
    finally:
        other.close()
