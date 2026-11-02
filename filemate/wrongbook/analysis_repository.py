"""Serialize opt-in analysis claims, bounded results and non-replaying receipts."""

import json
import os
import re
from uuid import uuid4

from filemate.execution.data_actions import digest
from filemate.execution.storage import QuestionRevisionConflict
from filemate.task_resources import admit_learning
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.repository import ReviewRepository

ERROR_CODES = frozenset({'timeout', 'cancelled', 'backup_restored', 'input_changed', 'disabled',
    'invalid_output', 'provider_unavailable', 'credentials_missing', 'quota_exceeded', 'interrupted', 'network_error'})


class AnalysisGone(LookupError):
    """Identify a deleted receipt without permitting another external call."""


def enabled() -> bool:
    return all(os.getenv(name, '0') == '1' for name in ('FILEMATE_ENABLE_WRONGBOOK_V2', 'FILEMATE_ENABLE_WRONGBOOK_AI'))


def valid_key(key: str) -> None:
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', key):
        raise ValueError('invalid_request_key')


def request_fingerprint(wrong_id, attempt_id, input_digest, force_refresh=False, course_id=None, credential_mode='server'):
    return digest({'wrong_id': wrong_id, 'attempt_id': attempt_id, 'input_digest': input_digest,
        'force_refresh': force_refresh, 'course_id': course_id, 'credential_mode': credential_mode})


class ReviewAnalysisRepository:
    def __init__(self, storage, clock=None):
        self.storage = storage
        self.repo = ReviewRepository(storage, clock=clock)

    def _row(self, analysis_id):
        row = self.storage._conn().execute('SELECT * FROM wrong_review_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
        if row is None:
            raise LookupError('analysis_not_found')
        return dict(row)

    def _current(self, snapshot):
        return ReviewLearningContext(self.storage, self.repo.now).build(snapshot['ref']['wrong_id'],
            snapshot['attempt']['attempt_id'], (snapshot.get('_graph_binding') or {}).get('course_id'),
            credential_mode=snapshot.get('credential_mode', 'server'))

    def _is_current(self, snapshot):
        try:
            return self._current(snapshot)['input_digest'] == snapshot['input_digest']
        except (LookupError, ValueError):
            return False

    def _view(self, row, *, body=True):
        snapshot = json.loads(row['input_snapshot'])
        keys = ('analysis_id', 'attempt_id', 'status', 'error_code', 'result_artifact_id', 'created_at', 'finished_at')
        view = {**{k: row[k] for k in keys}, 'ref': snapshot['ref'],
            'stale': not self._is_current(snapshot), 'input_digest': row['input_digest'],
            'context_revision': row['context_revision']}
        request = self.storage._conn().execute('SELECT request_key FROM wrong_review_analysis_requests WHERE analysis_id=? ORDER BY created_at,request_key LIMIT 1', (row['analysis_id'],)).fetchone()
        view['request_key'] = request[0] if request else None
        if body:
            artifact = self.storage.get_artifact(row['result_artifact_id']) if row['result_artifact_id'] else None
            if row['status'] == 'ready' and not artifact:
                raise AnalysisGone('analysis_result_deleted')
            view['result'] = artifact['content'] if artifact else None
            view['provenance'] = artifact['metadata'].get('provenance') if artifact else None
            view['source_evidence'] = snapshot.get('source_evidence', [])
        return view

    def find_request(self, key):
        """Read a tenant receipt without renewing its execution lease."""
        valid_key(key)
        row = self.storage._conn().execute('SELECT analysis_id FROM wrong_review_analysis_requests WHERE request_key=?', (key,)).fetchone()
        if row is None:
            return None
        if row[0] is None:
            raise AnalysisGone('analysis_result_deleted')
        return {**self._view(self._row(row[0])), 'request_key': key}

    def get(self, wrong_id, analysis_id):
        row = self._row(analysis_id)
        if row['wrong_id'] != wrong_id:
            raise LookupError('analysis_not_found')
        return self._view(row)

    def page(self, wrong_id, *, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValueError('invalid_page')
        self.repo.detail(wrong_id)
        conn = self.storage._conn()
        total = conn.execute('SELECT COUNT(*) FROM wrong_review_analyses WHERE wrong_id=?', (wrong_id,)).fetchone()[0]
        rows = conn.execute('SELECT * FROM wrong_review_analyses WHERE wrong_id=? ORDER BY created_at DESC,analysis_id DESC LIMIT ? OFFSET ?', (wrong_id, limit, offset))
        return {'items': [self._view(dict(r), body=False) for r in rows], 'total': total,
            'limit': limit, 'offset': offset, 'has_more': offset+limit < total}

    def claim(self, context, request_key, force_refresh=False):
        """Claim one durable slot; cache and receipt reads never admit model work."""
        valid_key(request_key)
        fingerprint = request_fingerprint(context['ref']['wrong_id'], context['attempt']['attempt_id'],
            context['input_digest'], force_refresh, (context.get('_graph_binding') or {}).get('course_id'),
            context.get('credential_mode', 'server'))
        now = self.repo.now()
        with self.repo.transaction() as conn:
            old = conn.execute('SELECT * FROM wrong_review_analysis_requests WHERE request_key=?', (request_key,)).fetchone()
            if old:
                if old['request_digest'] != fingerprint:
                    raise QuestionRevisionConflict('analysis_request_conflict')
                view = self.find_request(request_key)
                return view, False, None
            if not enabled():
                raise ValueError('analysis_disabled')
            if context.get('read_only_snapshot') or not self._is_current(context):
                raise QuestionRevisionConflict('analysis_input_changed')
            conn.execute("UPDATE wrong_review_analyses SET status='interrupted',epoch=?,error_code='interrupted',finished_at=? WHERE wrong_id=? AND status IN ('running','cancelling') AND lease_until<?",
                (uuid4().hex, now.isoformat(), context['ref']['wrong_id'], now.timestamp()))
            cached = None if force_refresh else conn.execute("SELECT * FROM wrong_review_analyses WHERE wrong_id=? AND input_digest=? AND status='ready' AND result_artifact_id IS NOT NULL ORDER BY created_at DESC LIMIT 1", (context['ref']['wrong_id'], context['input_digest'])).fetchone()
            if cached:
                conn.execute('INSERT INTO wrong_review_analysis_requests VALUES(?,?,?,?)', (request_key, fingerprint, cached['analysis_id'], now.isoformat()))
                return {**self._view(dict(cached)), 'request_key': request_key}, False, None
            if conn.execute("SELECT 1 FROM wrong_review_analyses WHERE wrong_id=? AND status IN ('running','cancelling')", (context['ref']['wrong_id'],)).fetchone():
                raise QuestionRevisionConflict('analysis_already_running')
            if not admit_learning(self.storage.db_path, 'wrongbook-analysis', request_key, fingerprint, now=now.timestamp()):
                raise AnalysisGone('analysis_result_deleted_or_restored')
            aid, epoch = uuid4().hex, uuid4().hex
            conn.execute('''INSERT INTO wrong_review_analyses
                (analysis_id,wrong_id,attempt_id,question_digest,input_digest,context_revision,provider_identity,model,prompt_version,input_snapshot,status,epoch,deadline,lease_until,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'running',?,?,?,?)''',
                (aid, context['ref']['wrong_id'], context['attempt']['attempt_id'], context['ref']['question_digest'],
                 context['input_digest'], context['context_revision'], context['provider_identity'], context['model'],
                 context['prompt_version'], json.dumps(context, ensure_ascii=False), epoch, now.timestamp()+20, now.timestamp()+30, now.isoformat()))
            for source in context['_source_dependencies']:
                conn.execute('INSERT INTO wrong_review_analysis_sources VALUES(?,?)', (aid, source['source_id']))
            conn.execute('INSERT INTO wrong_review_analysis_requests VALUES(?,?,?,?)', (request_key, fingerprint, aid, now.isoformat()))
            return self._view(self._row(aid)), True, epoch

    def active(self, analysis_id, epoch, *, check_deadline=True):
        """Check a worker lease without authorizing additional calls."""
        try:
            row = self._row(analysis_id)
        except LookupError:
            return False
        return row['epoch'] == epoch and row['status'] == 'running' and (not check_deadline or self.repo.now().timestamp() <= row['deadline']) and enabled()

    def finish(self, analysis_id, epoch, result, provenance):
        """Commit one result only while every original input and lease remains valid."""
        with self.repo.transaction() as conn:
            if not self.active(analysis_id, epoch):
                return False
            row = self._row(analysis_id)
            context = json.loads(row['input_snapshot'])
            if not self._is_current(context):
                conn.execute("UPDATE wrong_review_analyses SET status='failed',error_code='input_changed',finished_at=? WHERE analysis_id=?", (self.repo.now().isoformat(), analysis_id))
                return False
            safe_provenance = {k: provenance.get(k) for k in ('provider', 'model', 'prompt_version', 'usage', 'latency_ms')}
            artifact_id = uuid4().hex
            conn.execute('''INSERT INTO artifacts(artifact_id,source_id,artifact_type,title,content,metadata)
                VALUES(?,?,'wrong_review_analysis','单题复盘分析',?,?)''',
                (artifact_id, (context['_source_dependencies'][0]['source_id'] if context['_source_dependencies'] else None),
                 json.dumps(result, ensure_ascii=False), json.dumps({'analysis_id': analysis_id, 'provenance': safe_provenance,
                    'ref': context['ref'], 'input_digest': context['input_digest']}, ensure_ascii=False)))
            for source in context['_source_dependencies']:
                conn.execute('INSERT INTO kg_learning_artifact_sources VALUES(?,?)', (artifact_id, source['source_id']))
            conn.execute("UPDATE wrong_review_analyses SET status='ready',result_artifact_id=?,finished_at=? WHERE analysis_id=?", (artifact_id, self.repo.now().isoformat(), analysis_id))
            return True

    def fail(self, analysis_id, epoch, error_code):
        if error_code not in ERROR_CODES:
            error_code = 'provider_unavailable'
        with self.repo.transaction() as conn:
            conn.execute("UPDATE wrong_review_analyses SET status='failed',error_code=?,finished_at=? WHERE analysis_id=? AND epoch=? AND status='running'",
                (error_code, self.repo.now().isoformat(), analysis_id, epoch))

    def cancel(self, wrong_id, analysis_id, request_key):
        valid_key(request_key)
        with self.repo.transaction() as conn:
            row = self._row(analysis_id)
            if row['wrong_id'] != wrong_id:
                raise LookupError('analysis_not_found')
            used = conn.execute('SELECT analysis_id FROM wrong_review_analyses WHERE cancel_request_key=?', (request_key,)).fetchone()
            if used and used[0] != analysis_id:
                raise QuestionRevisionConflict('cancel_request_conflict')
            if row['status'] in {'running', 'cancelling'}:
                conn.execute("UPDATE wrong_review_analyses SET status='cancelled',epoch=?,error_code='cancelled',finished_at=?,cancel_request_key=? WHERE analysis_id=?", (uuid4().hex, self.repo.now().isoformat(), request_key, analysis_id))
            return self._view(self._row(analysis_id))
