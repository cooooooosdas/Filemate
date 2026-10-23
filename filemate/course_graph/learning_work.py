"""Persist bounded learning work before calling external providers outside transactions."""

import json
import secrets
from datetime import timedelta
from uuid import uuid4

from filemate.course_graph.learning_evidence import parse_time, read_learning_projection
from filemate.course_graph.models import CourseGraphError, digest, request_key_valid
from filemate.course_graph.repository import get_request, record_change, require_course, transaction

SAFE_ERRORS = frozenset({'provider_failed', 'model_timeout', 'invalid_output', 'budget_exceeded',
                         'governance_unavailable', 'input_changed', 'lease_expired'})


class LearningWorkService:
    """Share one persisted claim protocol for practice and grounded answers."""

    def __init__(self, storage, clock):
        self.storage, self.clock = storage, clock

    def _row(self, conn, cid, wid):
        require_course(conn, cid)
        row = conn.execute('SELECT * FROM kg_learning_work WHERE course_id=? AND work_id=?', (cid, wid)).fetchone()
        if row is None:
            raise CourseGraphError('learning_work_not_found', 404)
        return dict(row)

    def _current(self, read, row):
        projection = read_learning_projection(read, row['course_id'], now=self.clock())
        binding = json.loads(row['payload']).get('goal_binding')
        if binding:
            artifact = read.get_artifact(binding['artifact_id'])
            if artifact is None or digest(artifact) != binding['digest']:
                return False
        return (row['graph_digest'] == projection['graph_digest']
                and row['evidence_digest'] == projection['evidence_digest'])

    def _view(self, read, row):
        result = {k: v for k, v in row.items() if k not in {'epoch', 'lease_until'}}
        result['payload'] = json.loads(row['payload'])
        result['stale'] = not self._current(read, row)
        if row['status'] == 'running' and (parse_time(row['lease_until']) or self.clock()) <= self.clock():
            result['status'], result['error_code'] = 'interrupted', 'lease_expired'
        return result

    def get(self, cid, wid):
        """Read saved work without a model call, lease renewal or database mutation."""
        with self.storage.read_snapshot() as read:
            return self._view(read, self._row(read._conn(), cid, wid))

    def find(self, cid, kind, inputs, request_key):
        """Recover an uncertain response by key instead of sending a second model request."""
        request_key_valid(request_key)
        with self.storage.read_snapshot() as read:
            require_course(read._conn(), cid)
            row = read._conn().execute('SELECT * FROM kg_learning_work WHERE course_id=? AND request_key=?',
                                       (cid, request_key)).fetchone()
            if row is None:
                old = get_request(read._conn(), cid, request_key, 'learning_work_claim', digest(inputs))
                if old:
                    if old['metadata']['kind'] != kind:
                        raise CourseGraphError('request_key_conflict')
                    raise CourseGraphError('learning_work_unavailable', 410)
                return None
            if row['kind'] != kind or row['input_digest'] != digest(inputs):
                raise CourseGraphError('request_key_conflict')
            return self._view(read, dict(row))

    def claim(self, cid, kind, inputs, request_key, sources, graph_digest, evidence_digest, *, goal_binding=None):
        """Claim one course slot and a nonrefundable daily request before external work."""
        request_key_valid(request_key)
        if kind not in {'practice', 'answer'} or not isinstance(sources, list) or not 1 <= len(set(sources)) <= 12:
            raise CourseGraphError('invalid_learning_work', 422)
        hashed, now = digest(inputs), self.clock()
        with transaction(self.storage) as conn:
            require_course(conn, cid)
            row = conn.execute('SELECT * FROM kg_learning_work WHERE course_id=? AND request_key=?',
                               (cid, request_key)).fetchone()
            if row:
                if row['kind'] != kind or row['input_digest'] != hashed:
                    raise CourseGraphError('request_key_conflict')
                return {**self._view(self.storage, dict(row)), '_claimed': False}
            old = get_request(conn, cid, request_key, 'learning_work_claim', hashed)
            if old:
                if old['metadata']['kind'] != kind:
                    raise CourseGraphError('request_key_conflict')
                raise CourseGraphError('learning_work_unavailable', 410)
            projection = read_learning_projection(self.storage, cid, now=now)
            if graph_digest != projection['graph_digest'] or evidence_digest != projection['evidence_digest']:
                raise CourseGraphError('input_changed')
            if any(not projection['_snapshot'].fingerprints.get(sid) for sid in sources):
                raise CourseGraphError('source_not_in_course', 404)
            if goal_binding:
                artifact = self.storage.get_artifact(goal_binding['artifact_id'])
                if artifact is None or digest(artifact) != goal_binding['digest']:
                    raise CourseGraphError('input_changed')
            conn.execute('''UPDATE kg_learning_work SET status='interrupted',epoch=epoch+1,lease_until=NULL,
                error_code='lease_expired',updated_at=? WHERE course_id=? AND status='running'
                AND (lease_until IS NULL OR lease_until<=?)''', (now.isoformat(), cid, now.isoformat()))
            if conn.execute("SELECT 1 FROM kg_learning_work WHERE course_id=? AND status='running'", (cid,)).fetchone():
                raise CourseGraphError('learning_busy', 409)
            spent = conn.execute("""SELECT COUNT(*) FROM kg_changes WHERE course_id=? AND kind='learning_work_claim'
                AND created_at>=?""", (cid, (now - timedelta(hours=24)).isoformat())).fetchone()[0]
            if spent >= 30:
                raise CourseGraphError('learning_budget_exceeded', 429)
            wid, epoch = str(uuid4()), secrets.randbits(60)
            conn.execute('''INSERT INTO kg_learning_work(work_id,course_id,kind,request_key,input_digest,
                graph_digest,evidence_digest,status,epoch,lease_until,payload,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,'running',?,?,?,?,?)''',
                (wid, cid, kind, request_key, hashed, graph_digest, evidence_digest, epoch,
                 (now + timedelta(seconds=30)).isoformat(), json.dumps({'goal_binding': goal_binding}) if goal_binding else '{}',
                 now.isoformat(), now.isoformat()))
            conn.executemany('INSERT INTO kg_learning_work_sources VALUES(?,?)', [(wid, sid) for sid in sorted(set(sources))])
            record_change(conn, cid, request_key, 'learning_work_claim', hashed, {'work_id': wid, 'kind': kind})
            conn.execute('UPDATE kg_changes SET created_at=? WHERE course_id=? AND request_key=?',
                         (now.isoformat(), cid, request_key))
            return {**self._view(self.storage, self._row(conn, cid, wid)), '_claimed': True, '_epoch': epoch}

    def _complete(self, wid, epoch, payload, error):
        with transaction(self.storage) as conn:
            row = conn.execute('SELECT * FROM kg_learning_work WHERE work_id=?', (wid,)).fetchone()
            if row is None:
                raise CourseGraphError('learning_work_not_found', 404)
            cid = row['course_id']
            if row['status'] == 'running' and row['epoch'] == epoch:
                current = (self._current(self.storage, row)
                           and (parse_time(row['lease_until']) or self.clock()) > self.clock())
                status = ('failed' if error else 'ready') if current else 'interrupted'
                conn.execute('''UPDATE kg_learning_work SET status=?,payload=?,error_code=?,lease_until=NULL,
                    updated_at=? WHERE work_id=?''',
                    (status, json.dumps(payload, ensure_ascii=False) if current and not error else '{}',
                     error if current else 'input_changed', self.clock().isoformat(), wid))
        return self.get(cid, wid)

    def finish(self, work_id, epoch, result):
        """Persist a validated result only while its original claim and inputs remain current."""
        if len(json.dumps(result, ensure_ascii=False, allow_nan=False)) > 140_000:
            return self.fail(work_id, epoch, 'invalid_output')
        return self._complete(work_id, epoch, result, None)

    def fail(self, work_id, epoch, error_code):
        """Save a fixed safe error code without provider text or secrets."""
        return self._complete(work_id, epoch, {}, error_code if error_code in SAFE_ERRORS else 'provider_failed')

    def cancel(self, cid, wid, request_key):
        """Cancel without erasing an accepted question set or permitting a late result."""
        request_key_valid(request_key)
        hashed = digest({'work_id': wid})
        with transaction(self.storage) as conn:
            row = self._row(conn, cid, wid)
            previous = get_request(conn, cid, request_key, 'learning_cancel', hashed)
            if not previous:
                if row['status'] == 'confirmed':
                    raise CourseGraphError('work_already_confirmed')
                conn.execute('''UPDATE kg_learning_work SET status='cancelled',epoch=epoch+1,payload='{}',
                    lease_until=NULL,error_code=NULL,updated_at=? WHERE work_id=?''', (self.clock().isoformat(), wid))
                record_change(conn, cid, request_key, 'learning_cancel', hashed, {'work_id': wid})
        return self.get(cid, wid)
