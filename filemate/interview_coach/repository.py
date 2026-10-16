"""Transactional answer history, isolated from model transport."""

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import AttemptView


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
                  turn['fluency_metrics'], turn['visual_metrics'], turn['created_at'], origin))
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
