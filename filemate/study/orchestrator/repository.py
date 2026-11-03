"""Protected schedule references and immutable operation receipts, no new schema."""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Any

from pydantic import ValidationError

from filemate.execution.data_actions import digest

from .models import (
    DayView,
    OperationReceipt,
    OrchestratorError,
    ScheduleOptions,
    ScopeRequest,
    utc_now,
)
from .snapshot import SnapshotReader
from .task_views import project_tasks

DAY_TYPE = 'learning_orchestration_day'
OP_TYPE = 'learning_orchestration_operation'


def day_id(day: str) -> str:
    return 'learning-day-' + day


def operation_id(key: str) -> str:
    return 'learning-operation-' + digest(key)


@contextmanager
def atomic(storage):
    with storage._write_lock:
        conn = storage._conn()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def load(conn, identifier, kind):
    row = conn.execute('SELECT artifact_type,content FROM artifacts WHERE artifact_id=?', (identifier,)).fetchone()
    if row is None:
        return None
    if row['artifact_type'] != kind:
        raise OrchestratorError('reserved_identity_conflict')
    try:
        content = json.loads(row['content'])
        if not isinstance(content, dict):
            raise TypeError()
        return content
    except (ValueError, TypeError):
        raise OrchestratorError('saved_schedule_invalid') from None


def put(conn, identifier, kind, content, *, title='', replace=False):
    if not conn.in_transaction:
        raise RuntimeError('transaction_required')
    if replace:
        load(conn, identifier, kind)
    sql = '''INSERT INTO artifacts(artifact_id,artifact_type,source_id,title,content,metadata)
             VALUES(?,?,NULL,?,?,'{}')'''
    if replace:
        sql += " ON CONFLICT(artifact_id) DO UPDATE SET content=excluded.content,updated_at=strftime('%Y-%m-%dT%H:%M:%S','now')"
    conn.execute(sql, (identifier, kind, title, json.dumps(content, ensure_ascii=False, allow_nan=False)))


def undone(conn, oid):
    return conn.execute('SELECT 1 FROM artifacts WHERE artifact_type=? AND title=? LIMIT 1', (OP_TYPE, 'undo:' + oid)).fetchone() is not None


def receipt(conn, record):
    result = OperationReceipt.model_validate(record['receipt'])
    if result.status == 'confirmed' and undone(conn, result.operation_id):
        result.status = 'undone'
    return result


def latest_operation(conn: sqlite3.Connection, saved: dict[str, Any] | None, day: str) -> OperationReceipt | None:
    """Resolve only a matching persisted pointer, leaving legacy schedules readable."""
    identifier = saved.get('last_operation_id') if saved else None
    if not isinstance(identifier, str):
        return None
    try:
        if identifier.startswith('learning-coach-operation-'):
            from .coach.commands import native_operation_receipt
            return native_operation_receipt(conn, identifier, day, saved['revision'])
        record = load(conn, identifier, OP_TYPE)
        if record is None:
            return None
        result = OperationReceipt.model_validate(record.get('receipt'), strict=True)
        if (result.operation_id != identifier or operation_id(result.request_key) != identifier
                or not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', result.request_key)
                or result.study_date != day or result.revision != saved.get('revision')
                or result.status not in ('confirmed', 'undone')):
            return None
        return receipt(conn, record)
    except (OrchestratorError, ValidationError, ValueError, TypeError, KeyError, RecursionError):
        return None


class OrchestratorRepository:
    def __init__(self, storage, *, clock=None):
        self.storage = storage
        self.clock = clock or utc_now

    def find_request(self, request_key: str) -> OperationReceipt | None:
        with self.storage.read_snapshot() as read:
            record = load(read._conn(), operation_id(request_key), OP_TYPE)
            return receipt(read._conn(), record) if record else None

    def today(self, study_date: date) -> DayView:
        day = study_date.isoformat()
        with self.storage.read_snapshot() as read:
            saved = load(read._conn(), day_id(day), DAY_TYPE)
            latest = latest_operation(read._conn(), saved, day)
            if not saved or saved.get('config') is None:
                return DayView(study_date=day, revision=saved['revision'] if saved else 0, status='not_confirmed', latest_operation=latest)
            config = saved['config']
            if config.get('learning_coach'):
                from .coach.commands import CoachDayReader
                return CoachDayReader(self.storage, clock=self.clock).read_in_transaction(read, day, saved)
            scope = ScopeRequest.model_validate(config['scope'])
            options = ScheduleOptions.model_validate(config['options'])
            try:
                snap = SnapshotReader(read).read_in_transaction(read, scope, as_of=self.clock())
            except OrchestratorError:
                return DayView(study_date=day, revision=saved['revision'], status='stale',
                               scope=scope, options=options, stale_refs=config['selected_ids'], latest_operation=latest)
            projection = project_tasks(snap)
            tasks = {t.task_id: t for t in projection.tasks + projection.completed}
            for tid, minutes in options.minute_overrides.items():
                if tid in tasks:
                    tasks[tid] = tasks[tid].model_copy(update={'estimated_minutes': minutes, 'estimate_source': 'user_estimate'})
            stale = [tid for tid in config['selected_ids'] if tid not in tasks or tasks[tid].eligibility not in ('eligible', 'not_due')]
            if snap.evidence_revision != config['evidence_revision']:
                stale = list(dict.fromkeys([*stale, 'evidence_changed']))
            return DayView(study_date=day, revision=saved['revision'], status='stale' if stale else 'confirmed',
                           scope=scope, options=options, stale_refs=stale, latest_operation=latest,
                           selected=[tasks[tid] for tid in config['selected_ids'] if tid in tasks], completed=projection.completed)
