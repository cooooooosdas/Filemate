"""Short atomic commands with bound tokens, CAS, replay and reversible preferences."""

import time

from filemate.execution import data_actions

from .models import (
    LOCAL_ZONE,
    ConfirmRequest,
    OperationReceipt,
    OrchestratorError,
    PreviewRequest,
    SchedulePreview,
    UndoConfirmRequest,
    UndoPreview,
    aware,
    utc_now,
)
from .repository import DAY_TYPE, OP_TYPE, atomic, day_id, load, put, receipt, undone
from .repository import operation_id as operation_key
from .scheduler import build_schedule
from .snapshot import SnapshotReader
from .task_views import project_tasks


def command_digest(request):
    body = request.model_dump(mode='json', exclude={'confirmation_token', 'request_key', 'confirmed'})
    return data_actions.digest(body)


class OrchestratorCommands:
    def __init__(self, storage, *, clock=None):
        self.storage = storage
        self.clock = clock or utc_now

    def _prepare(self, conn, request, as_of):
        try:
            snap = SnapshotReader(self.storage).read_in_transaction(self.storage, request.scope, as_of=as_of)
        except OrchestratorError as exc:
            raise OrchestratorError('scope_changed') from exc
        if snap.evidence_revision != request.expected_evidence_revision:
            raise OrchestratorError('evidence_changed')
        result = build_schedule(snap, project_tasks(snap), request.options)
        saved = load(conn, day_id(snap.study_date), DAY_TYPE)
        revision = saved['revision'] if saved else 0
        legacy = conn.execute('SELECT available_minutes,item_order,updated_at FROM daily_coach_preferences WHERE study_date=?', (snap.study_date,)).fetchone()
        binding = data_actions.digest({'command': command_digest(request), 'day': snap.study_date,
                                      'revision': revision, 'legacy': dict(legacy) if legacy else None,
                                      'result': result.model_dump(mode='json')})
        return snap, result, saved, revision, binding

    @staticmethod
    def _quota(conn, day, *, preview=False):
        if preview:
            count = conn.execute("SELECT COUNT(*) FROM data_action_previews WHERE action LIKE 'orchestrator_%' AND resource_id=? AND result IS NULL AND expires_at>=?", (day_id(day), int(time.time()))).fetchone()[0]
        else:
            count = conn.execute('SELECT COUNT(*) FROM artifacts WHERE artifact_type=? AND title=?', (OP_TYPE, 'confirm:' + day)).fetchone()[0]
        if count >= 100:
            raise OrchestratorError('daily_operation_limit', 429)

    @staticmethod
    def _check(conn, action, resource, token, revision):
        try:
            return data_actions.check(conn, action, resource, token, revision)
        except ValueError:
            raise OrchestratorError('preview_expired_or_changed') from None

    def _replay(self, conn, request, digest, action, resource):
        record = load(conn, operation_key(request.request_key), OP_TYPE)
        if record is None:
            return None
        if record['command_digest'] != digest or record['token_hash'] != data_actions.digest(request.confirmation_token):
            raise OrchestratorError('request_key_conflict')
        prior = self._check(conn, action, day_id(record['receipt']['study_date']), request.confirmation_token, None)
        if not prior or prior.get('operation_id') != record['receipt']['operation_id']:
            raise OrchestratorError('receipt_not_available')
        return receipt(conn, record)

    def preview(self, request: PreviewRequest) -> SchedulePreview:
        as_of = aware(self.clock())
        with atomic(self.storage) as conn:
            snap, result, saved, revision, binding = self._prepare(conn, request, as_of)
            self._quota(conn, snap.study_date, preview=True)
            token = data_actions.issue(conn, 'orchestrator_confirm', day_id(snap.study_date), binding)
            before = saved.get('config') if saved else None
            changes = {'replaces_goal': bool(before and before['scope']['goal_id'] != snap.scope.goal_id),
                       'previous_selected_ids': before['selected_ids'] if before else []}
            return SchedulePreview(**result.model_dump(), scope=snap.scope, study_date=snap.study_date,
                                   as_of=as_of, evidence_revision=snap.evidence_revision, day_revision=revision,
                                   changes=changes, confirmation_token=token)

    def confirm(self, request: ConfirmRequest) -> OperationReceipt:
        as_of = aware(self.clock())
        day = as_of.astimezone(LOCAL_ZONE).date().isoformat()
        hashed = command_digest(request)
        with atomic(self.storage) as conn:
            replay = self._replay(conn, request, hashed, 'orchestrator_confirm', day_id(day))
            if replay:
                return replay
            snap, result, saved, revision, binding = self._prepare(conn, request, as_of)
            if self._check(conn, 'orchestrator_confirm', day_id(day), request.confirmation_token, binding):
                raise OrchestratorError('token_already_used')
            self._quota(conn, day)
            config = {'scope': snap.scope.model_dump(), 'options': request.options.model_dump(),
                      'selected_ids': [t.task_id for t in result.selected], 'rule_version': result.rule_version,
                      'evidence_revision': snap.evidence_revision}
            output = OperationReceipt(operation_id=operation_key(request.request_key), request_key=request.request_key,
                                      study_date=day, revision=revision + 1, status='confirmed')
            record = {'command_digest': hashed, 'token_hash': data_actions.digest(request.confirmation_token),
                      'before': saved.get('config') if saved else None, 'after': config, 'receipt': output.model_dump()}
            put(conn, day_id(day), DAY_TYPE, {'revision': revision + 1, 'config': config,
                                           'last_operation_id': output.operation_id}, replace=True)
            put(conn, output.operation_id, OP_TYPE, record, title='confirm:' + day)
            data_actions.finish(conn, 'orchestrator_confirm', day_id(day), request.confirmation_token, output.model_dump())
            return output

    def _undo_target(self, conn, oid):
        target = load(conn, oid, OP_TYPE)
        if not target or target['receipt']['status'] != 'confirmed':
            raise OrchestratorError('operation_not_found', 404)
        day = target['receipt']['study_date']
        saved = load(conn, day_id(day), DAY_TYPE)
        if undone(conn, oid) or not saved or saved['revision'] != target['receipt']['revision']:
            raise OrchestratorError('schedule_changed_since_operation')
        return target, day, saved['revision']

    def preview_undo(self, operation_id: str) -> UndoPreview:
        with atomic(self.storage) as conn:
            _, day, revision = self._undo_target(conn, operation_id)
            self._quota(conn, day, preview=True)
            token = data_actions.issue(conn, 'orchestrator_undo', day_id(day), data_actions.digest([operation_id, revision, aware(self.clock()).astimezone(LOCAL_ZONE).date().isoformat()]))
            return UndoPreview(operation_id=operation_id, study_date=day, day_revision=revision, confirmation_token=token)

    def confirm_undo(self, operation_id: str, request: UndoConfirmRequest) -> OperationReceipt:
        hashed = data_actions.digest({'undo_of': operation_id})
        with atomic(self.storage) as conn:
            original = load(conn, operation_id, OP_TYPE)
            if not original:
                raise OrchestratorError('operation_not_found', 404)
            day = original['receipt']['study_date']
            replay = self._replay(conn, request, hashed, 'orchestrator_undo', day_id(day))
            if replay:
                return replay
            target, day, revision = self._undo_target(conn, operation_id)
            binding = data_actions.digest([operation_id, revision, aware(self.clock()).astimezone(LOCAL_ZONE).date().isoformat()])
            if self._check(conn, 'orchestrator_undo', day_id(day), request.confirmation_token, binding):
                raise OrchestratorError('token_already_used')
            oid = operation_key(request.request_key)
            output = OperationReceipt(operation_id=oid, request_key=request.request_key, study_date=day, revision=revision + 1, status='undone')
            record = {'command_digest': hashed, 'token_hash': data_actions.digest(request.confirmation_token),
                      'undo_of': operation_id, 'receipt': output.model_dump()}
            put(conn, day_id(day), DAY_TYPE, {'revision': revision + 1, 'config': target['before'],
                                           'last_operation_id': output.operation_id}, replace=True)
            put(conn, oid, OP_TYPE, record, title='undo:' + operation_id)
            data_actions.finish(conn, 'orchestrator_undo', day_id(day), request.confirmation_token, output.model_dump())
            return output
