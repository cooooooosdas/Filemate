"""Transactional answer history, isolated from model transport."""

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from .models import AdvanceCommand, AttemptView, CoachMutationResult, CoachSnapshot, SubmitAnswer


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def decode(value: str, expected: type = dict) -> Any:
    result = json.loads(value)
    if not isinstance(result, expected):
        raise TypeError('invalid saved JSON')
    return result


def attempt_view(conn: sqlite3.Connection, row: sqlite3.Row) -> AttemptView:
    values = dict(row)
    for key in ('fluency_metrics', 'visual_metrics'):
        try:
            values[key] = decode(values[key])
        except (ValueError, TypeError):
            values[key] = {}
            values['data_error'] = True
    run = conn.execute('SELECT * FROM interview_coach_analysis_runs WHERE attempt_id=? '
                       'ORDER BY attempt_seq DESC LIMIT 1', (row['attempt_id'],)).fetchone()
    if run:
        values['latest_run_id'] = run['run_id']
        values['analysis_status'] = 'cancelled' if run['status'] == 'cancelling' else run['status']
        if run['status'] == 'succeeded':
            try:
                from filemate.interview_review.models import validate_saved_analysis

                evaluation = decode(run['evaluation'])
                validate_saved_analysis(evaluation['content_analysis'], row['answer'])
                score = evaluation['score']
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
                    raise ValueError('invalid score')
                values['evaluation'] = evaluation
                values['score'] = score
            except (KeyError, ValueError, TypeError):
                values['data_error'] = True
                values['analysis_status'] = 'failed'
    return AttemptView(**values)


def freeze_question(conn: sqlite3.Connection, interview_id: str, index: int,
                    question: str, entered_at: str) -> None:
    conn.execute('INSERT OR IGNORE INTO interview_coach_questions '
                 '(interview_id,question_index,question,question_digest,entered_at) VALUES (?,?,?,?,?)',
                 (interview_id, index, question, digest(question), entered_at))


def initialize_state(conn: sqlite3.Connection, session: dict[str, Any]) -> None:
    questions = session['questions']
    if isinstance(questions, str):
        questions = decode(questions, list)
    turns = conn.execute('SELECT * FROM interview_turns WHERE interview_id=? ORDER BY question_index',
                         (session['interview_id'],)).fetchall()
    entered = {int(t['question_index']) for t in turns}
    index = min(int(session['current_index']), max(0, len(questions) - 1))
    if questions:
        entered.add(index)
    for t in turns:
        freeze_question(conn, session['interview_id'], t['question_index'], t['question'], t['created_at'])
    if questions:
        freeze_question(conn, session['interview_id'], index, questions[index], session['updated_at'])
    conn.execute('INSERT OR IGNORE INTO interview_coach_state '
                 '(interview_id,displayed_index,phase,entered_indices,updated_at) VALUES (?,?,?,?,?)',
                 (session['interview_id'], index,
                  'summary' if session['status'] == 'completed' else 'question',
                  json.dumps(sorted(entered)), session['updated_at']))


def record_attempt_from_turn(conn: sqlite3.Connection, turn_id: str, *, origin: str) -> AttemptView:
    if not conn.in_transaction:
        raise RuntimeError('answer capture requires an active transaction')
    turn = conn.execute('SELECT * FROM interview_turns WHERE turn_id=?', (turn_id,)).fetchone()
    if turn is None:
        raise ValueError('回答不存在')
    version = conn.execute('SELECT COALESCE(MAX(version),0)+1 FROM interview_answer_attempts WHERE turn_id=?',
                           (turn_id,)).fetchone()[0]
    attempt_id = uuid.uuid4().hex
    conn.execute('INSERT INTO interview_answer_attempts '
                 '(attempt_id,interview_id,turn_id,version,question_index,question,question_digest,answer,'
                 'input_digest,fluency_metrics,visual_metrics,created_at,origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (attempt_id, turn['interview_id'], turn_id, version, turn['question_index'], turn['question'],
                  digest(turn['question']), turn['answer'], digest({'answer': turn['answer'],
                  'fluency_metrics': turn['fluency_metrics'], 'visual_metrics': turn['visual_metrics']}),
                  turn['fluency_metrics'], turn['visual_metrics'],
                  now() if version > 1 else turn['created_at'], origin))
    if turn['scoring_mode'] == 'llm':
        evaluation = {'score': turn['score'], 'dimensions': {}, 'feedback': turn['feedback']}
        try:
            evaluation['dimensions'] = decode(turn['dimensions'])
            evaluation['content_analysis'] = decode(turn['content_analysis'])
            from filemate.interview_review.models import validate_saved_analysis

            validate_saved_analysis(evaluation['content_analysis'], turn['answer'])
            if not math.isfinite(turn['score']) or not 0 <= turn['score'] <= 100:
                raise ValueError('invalid score')
        except (ValueError, TypeError):
            pass
        else:
            conn.execute('INSERT INTO interview_coach_analysis_runs '
                         '(run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,'
                         'review_revision,provider_identity,model,prompt_version,rubric_version,status,evaluation,created_at) '
                         "VALUES (?,?,?,1,?,?,0,0,'legacy_unknown','legacy_unknown','legacy_unknown','legacy_unknown','succeeded',?,?)",
                         (uuid.uuid4().hex, turn['interview_id'], attempt_id, 'legacy_' + attempt_id,
                          digest(turn['answer']), json.dumps(evaluation, ensure_ascii=False), turn['created_at']))
    row = conn.execute('SELECT * FROM interview_answer_attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
    return attempt_view(conn, row)


def backfill_legacy_attempts(conn: sqlite3.Connection) -> int:
    if not conn.in_transaction:
        raise RuntimeError('backfill requires an active transaction')
    rows = conn.execute('SELECT turn_id FROM interview_turns t WHERE NOT EXISTS '
                        '(SELECT 1 FROM interview_answer_attempts a WHERE a.turn_id=t.turn_id)').fetchall()
    for row in rows:
        record_attempt_from_turn(conn, row['turn_id'], origin='migrated')
    for session in conn.execute('SELECT s.* FROM interview_sessions s WHERE NOT EXISTS '
                                '(SELECT 1 FROM interview_coach_state c WHERE c.interview_id=s.interview_id)').fetchall():
        initialize_state(conn, dict(session))
    return len(rows)


class CoachError(ValueError):
    """Safe domain failure for API transport."""

    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class CoachRepository:
    def __init__(self, storage) -> None:
        self.storage = storage

    @contextmanager
    def transaction(self):
        with self.storage._write_lock:
            conn = self.storage._conn()
            with conn:
                conn.execute('BEGIN IMMEDIATE')
                yield conn

    def _state(self, conn, interview_id):
        if not conn.execute('SELECT 1 FROM interview_sessions WHERE interview_id=?', (interview_id,)).fetchone():
            raise CoachError('interview_not_found', 404)
        row = conn.execute('SELECT * FROM interview_coach_state WHERE interview_id=?', (interview_id,)).fetchone()
        if row is None:
            raise CoachError('coach_data_error')
        return row

    def snapshot(self, interview_id: str) -> CoachSnapshot:
        conn = self.storage._conn()
        session = self.storage.get_interview(interview_id)
        if session is None:
            raise CoachError('interview_not_found', 404)
        row = conn.execute('SELECT * FROM interview_coach_state WHERE interview_id=?', (interview_id,)).fetchone()
        if row is None:
            return CoachSnapshot(session=session, revision=0, displayed_index=0, phase='question',
                                 external_consent=False, consent_revision=0, provider_identity='', data_error=True)
        values = dict(row)
        data_error = False
        try:
            entered = decode(row['entered_indices'], list)
            if row['displayed_index'] not in entered or row['phase'] not in {'question', 'feedback', 'summary'}:
                raise ValueError('invalid coach state')
        except (TypeError, ValueError):
            data_error = True
        index = row['displayed_index']
        attempt = conn.execute('SELECT * FROM interview_answer_attempts WHERE interview_id=? AND question_index=? '
                               'ORDER BY version DESC LIMIT 1', (interview_id, index)).fetchone()
        active = conn.execute("SELECT run_id FROM interview_coach_analysis_runs WHERE interview_id=? AND status IN ('running','cancelling')",
                              (interview_id,)).fetchone()
        retries = conn.execute("SELECT a.attempt_id FROM interview_answer_attempts a WHERE a.interview_id=? "
                               "AND a.version=(SELECT MAX(b.version) FROM interview_answer_attempts b WHERE b.turn_id=a.turn_id) "
                               "AND EXISTS (SELECT 1 FROM interview_coach_analysis_runs r WHERE r.attempt_id=a.attempt_id "
                               "AND r.attempt_seq=(SELECT MAX(x.attempt_seq) FROM interview_coach_analysis_runs x WHERE x.attempt_id=a.attempt_id) "
                               "AND r.status IN ('failed','cancelled','interrupted'))", (interview_id,)).fetchall()
        return CoachSnapshot(session=session, revision=values['revision'], displayed_index=index,
                             phase=values['phase'] if not data_error else 'question',
                             external_consent=bool(values['external_consent']) and not data_error,
                             consent_revision=values['consent_revision'], provider_identity=values['provider_identity'],
                             current_attempt=attempt_view(conn, attempt) if attempt else None,
                             active_run_id=active['run_id'] if active else None,
                             pending_retries=[r[0] for r in retries], data_error=data_error)

    def _previous(self, conn, sid, kind, command):
        row = conn.execute('SELECT * FROM interview_coach_actions WHERE interview_id=? AND request_key=?',
                            (sid, command.request_key)).fetchone()
        if row:
            if row['kind'] != kind or row['input_digest'] != digest(command.model_dump()):
                raise CoachError('request_key_conflict')
            return decode(row['result_refs'])
        return None

    def _check(self, conn, sid, command):
        state = self._state(conn, sid)
        if state['revision'] != command.expected_revision:
            raise CoachError('revision_conflict')
        view = self.snapshot(sid)
        if view.data_error:
            raise CoachError('coach_data_error')
        return state

    def _receipt(self, conn, sid, kind, command, **refs):
        result = {'kind': kind, 'request_key': command.request_key, **refs}
        conn.execute('INSERT INTO interview_coach_actions VALUES (?,?,?,?,?,?)',
                     (sid, command.request_key, kind, digest(command.model_dump()),
                      json.dumps(result, ensure_ascii=False), now()))
        return result

    def _result(self, sid, receipt):
        return CoachMutationResult(snapshot=self.snapshot(sid), receipt=receipt)

    def _invalidate(self, conn, sid):
        conn.execute("UPDATE interview_coach_analysis_runs SET status='cancelling' WHERE interview_id=? AND status='running'", (sid,))
        conn.execute("INSERT INTO interview_review_state(interview_id,revision) VALUES (?,1) "
                     "ON CONFLICT(interview_id) DO UPDATE SET revision=revision+1,input_digest=''", (sid,))

    def submit(self, interview_id: str, command: SubmitAnswer) -> CoachMutationResult:
        from .commands import local_evaluation

        # Local computation happens before taking the cross-connection write lock.
        session = self.storage.get_interview(interview_id)
        if session is None:
            raise CoachError('interview_not_found', 404)
        evaluation = local_evaluation(command.answer, command.fluency_metrics,
                                      speech_language='en-US' if session['scenario'] == '英语面' else 'zh-CN')
        with self.transaction() as conn:
            old = self._previous(conn, interview_id, 'submit', command)
            if old:
                return self._result(interview_id, old)
            state = self._check(conn, interview_id, command)
            frozen = conn.execute('SELECT * FROM interview_coach_questions WHERE interview_id=? AND question_index=?',
                                  (interview_id, command.question_index)).fetchone()
            if frozen is None:
                raise CoachError('question_not_entered')
            existing = conn.execute('SELECT * FROM interview_turns WHERE interview_id=? AND question_index=?',
                                    (interview_id, command.question_index)).fetchone()
            latest = conn.execute('SELECT attempt_id FROM interview_answer_attempts WHERE interview_id=? AND question_index=? '
                                  'ORDER BY version DESC LIMIT 1', (interview_id, command.question_index)).fetchone()
            if (latest[0] if latest else None) != command.expected_attempt_id:
                raise CoachError('attempt_conflict')
            if existing is None:
                if command.question_index != state['displayed_index']:
                    raise CoachError('question_conflict')
                payload = {
                    'interview_id': interview_id, 'question_index': command.question_index,
                    'question': frozen['question'], 'answer': command.answer, 'score': None,
                    'dimensions': evaluation['dimensions'], 'feedback': evaluation['feedback'],
                    'fluency_metrics': command.fluency_metrics, 'scoring_mode': 'local_fallback',
                    'scoring_version': 'coach-local-v1', 'next_question': None, 'expression_review': None,
                    'visual_metrics': command.visual_metrics, 'content_analysis': None,
                    'answer_key': command.request_key, 'answer_digest': digest(command.model_dump()),
                }
                turn_id = self.storage._save_interview_turn_tx(conn, payload=payload, origin='coach')
            else:
                turn_id = existing['turn_id']
                self._invalidate(conn, interview_id)
                conn.execute("UPDATE interview_turns SET answer=?,score=0,dimensions=?,feedback=?,fluency_metrics=?,"
                             "visual_metrics=?,content_analysis='{}',scoring_mode='local_fallback',scoring_version='coach-local-v1' "
                             'WHERE turn_id=?', (command.answer, json.dumps(evaluation['dimensions'], ensure_ascii=False),
                             evaluation['feedback'], json.dumps(command.fluency_metrics or {}, ensure_ascii=False),
                             json.dumps(command.visual_metrics or {}, ensure_ascii=False), turn_id))
                record_attempt_from_turn(conn, turn_id, origin='coach')
                conn.execute("UPDATE interview_coach_state SET revision=revision+1,displayed_index=?,phase='feedback',updated_at=? WHERE interview_id=?",
                             (command.question_index, now(), interview_id))
                self._sync_score(conn, interview_id)
            attempt = conn.execute('SELECT attempt_id FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1', (turn_id,)).fetchone()
            receipt = self._receipt(conn, interview_id, 'submit', command, attempt_id=attempt[0])
            return self._result(interview_id, receipt)

    def _sync_score(self, conn, sid):
        values = [t['score'] for t in self.storage.get_interview(sid)['turns'] if t['score'] is not None]
        conn.execute('UPDATE interview_sessions SET overall_score=?,updated_at=? WHERE interview_id=?',
                     (round(sum(values) / len(values), 2) if values else 0, now(), sid))

    def advance(self, interview_id: str, command: AdvanceCommand) -> CoachMutationResult:
        from filemate.understanding.interview_practice import grounded_followup

        view = self.snapshot(interview_id)
        followup = None
        if view.current_attempt:
            followup = grounded_followup(view.current_attempt.answer, view.session['scenario'], command.from_index + 1,
                         view.current_attempt.evaluation.get('content_analysis'),
                         difficulty=view.session['difficulty'])
        with self.transaction() as conn:
            old = self._previous(conn, interview_id, 'advance', command)
            if old:
                return self._result(interview_id, old)
            state = self._check(conn, interview_id, command)
            current = self.snapshot(interview_id)
            if state['phase'] != 'feedback' or state['displayed_index'] != command.from_index or not current.current_attempt or current.current_attempt.attempt_id != command.expected_attempt_id:
                raise CoachError('advance_conflict')
            target = command.from_index + 1
            questions = list(current.session['questions'])
            if target >= len(questions):
                phase, displayed = 'summary', command.from_index
            else:
                frozen = conn.execute('SELECT 1 FROM interview_coach_questions WHERE interview_id=? AND question_index=?', (interview_id, target)).fetchone()
                if not frozen:
                    if followup:
                        questions[target] = followup
                        ids = list(current.session['question_ids'])
                        ids[target] = None
                        conn.execute('UPDATE interview_sessions SET questions=?,question_ids=? WHERE interview_id=?',
                                     (json.dumps(questions, ensure_ascii=False), json.dumps(ids), interview_id))
                    freeze_question(conn, interview_id, target, questions[target], now())
                answered = conn.execute('SELECT 1 FROM interview_answer_attempts WHERE interview_id=? AND question_index=?', (interview_id, target)).fetchone()
                phase, displayed = ('feedback' if answered else 'question'), target
            entered = [r[0] for r in conn.execute('SELECT question_index FROM interview_coach_questions WHERE interview_id=? ORDER BY question_index', (interview_id,))]
            conn.execute('UPDATE interview_coach_state SET revision=revision+1,displayed_index=?,phase=?,entered_indices=?,updated_at=? WHERE interview_id=?',
                         (displayed, phase, json.dumps(entered), now(), interview_id))
            receipt = self._receipt(conn, interview_id, 'advance', command, target_index=target)
            return self._result(interview_id, receipt)

    def list_attempts(self, interview_id: str, turn_id: str, *, limit: int = 20,
                      before_version: int | None = None) -> dict[str, Any]:
        conn = self.storage._conn()
        if not conn.execute('SELECT 1 FROM interview_turns WHERE interview_id=? AND turn_id=?', (interview_id, turn_id)).fetchone():
            raise CoachError('turn_not_found', 404)
        limit = max(1, min(limit, 100))
        rows = conn.execute('SELECT * FROM interview_answer_attempts WHERE interview_id=? AND turn_id=? AND version<? '
                             'ORDER BY version DESC LIMIT ?', (interview_id, turn_id, before_version or 2147483647, limit + 1)).fetchall()
        return {'items': [attempt_view(conn, r).model_dump() for r in rows[:limit]],
                'next_before_version': rows[limit - 1]['version'] if len(rows) > limit else None}
