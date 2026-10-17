"""Transactional answer history, isolated from model transport."""

import hashlib
import json
import math
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import (
    AdvanceCommand,
    AnalysisCommand,
    AttemptView,
    CoachMutationResult,
    CoachSnapshot,
    ConsentCommand,
    SubmitAnswer,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def decode(value: str, expected: type = dict) -> Any:
    result = json.loads(value)
    if not isinstance(result, expected):
        raise TypeError("invalid saved JSON")
    return result


def attempt_view(conn: sqlite3.Connection, row: sqlite3.Row) -> AttemptView:
    values = dict(row)
    for key in ("fluency_metrics", "visual_metrics"):
        try:
            values[key] = decode(values[key])
        except (ValueError, TypeError):
            values[key] = {}
            values["data_error"] = True
    run = conn.execute(
        "SELECT * FROM interview_coach_analysis_runs WHERE attempt_id=? "
        "ORDER BY attempt_seq DESC LIMIT 1",
        (row["attempt_id"],),
    ).fetchone()
    if run:
        values["latest_run_id"] = run["run_id"]
        values["analysis_status"] = "cancelled" if run["status"] == "cancelling" else run["status"]
        if run["status"] == "succeeded":
            try:
                from filemate.interview_review.models import validate_saved_analysis

                evaluation = decode(run["evaluation"])
                validate_saved_analysis(evaluation["content_analysis"], row["answer"])
                score = evaluation["score"]
                if (
                    isinstance(score, bool)
                    or not isinstance(score, (int, float))
                    or not math.isfinite(score)
                    or not 0 <= score <= 100
                ):
                    raise ValueError("invalid score")
                values["evaluation"] = evaluation
                values["score"] = score
            except (KeyError, ValueError, TypeError):
                values["data_error"] = True
                values["analysis_status"] = "failed"
    return AttemptView(**values)


def freeze_question(
    conn: sqlite3.Connection, interview_id: str, index: int, question: str, entered_at: str
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO interview_coach_questions "
        "(interview_id,question_index,question,question_digest,entered_at) VALUES (?,?,?,?,?)",
        (interview_id, index, question, digest(question), entered_at),
    )


def initialize_state(conn: sqlite3.Connection, session: dict[str, Any]) -> None:
    questions = session["questions"]
    if isinstance(questions, str):
        questions = decode(questions, list)
    turns = conn.execute(
        "SELECT * FROM interview_turns WHERE interview_id=? ORDER BY question_index",
        (session["interview_id"],),
    ).fetchall()
    entered = {int(t["question_index"]) for t in turns}
    index = min(int(session["current_index"]), max(0, len(questions) - 1))
    if questions:
        entered.add(index)
    for t in turns:
        freeze_question(
            conn, session["interview_id"], t["question_index"], t["question"], t["created_at"]
        )
    if questions:
        freeze_question(
            conn, session["interview_id"], index, questions[index], session["updated_at"]
        )
    conn.execute(
        "INSERT OR IGNORE INTO interview_coach_state "
        "(interview_id,displayed_index,phase,entered_indices,updated_at) VALUES (?,?,?,?,?)",
        (
            session["interview_id"],
            index,
            "summary" if session["status"] == "completed" else "question",
            json.dumps(sorted(entered)),
            session["updated_at"],
        ),
    )


def record_attempt_from_turn(conn: sqlite3.Connection, turn_id: str, *, origin: str) -> AttemptView:
    if not conn.in_transaction:
        raise RuntimeError("answer capture requires an active transaction")
    turn = conn.execute("SELECT * FROM interview_turns WHERE turn_id=?", (turn_id,)).fetchone()
    if turn is None:
        raise ValueError("回答不存在")
    version = conn.execute(
        "SELECT COALESCE(MAX(version),0)+1 FROM interview_answer_attempts WHERE turn_id=?",
        (turn_id,),
    ).fetchone()[0]
    attempt_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO interview_answer_attempts "
        "(attempt_id,interview_id,turn_id,version,question_index,question,question_digest,answer,"
        "input_digest,fluency_metrics,visual_metrics,created_at,origin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            attempt_id,
            turn["interview_id"],
            turn_id,
            version,
            turn["question_index"],
            turn["question"],
            digest(turn["question"]),
            turn["answer"],
            digest(
                {
                    "answer": turn["answer"],
                    "fluency_metrics": turn["fluency_metrics"],
                    "visual_metrics": turn["visual_metrics"],
                }
            ),
            turn["fluency_metrics"],
            turn["visual_metrics"],
            now() if version > 1 else turn["created_at"],
            origin,
        ),
    )
    if turn["scoring_mode"] == "llm":
        evaluation = {"score": turn["score"], "dimensions": {}, "feedback": turn["feedback"]}
        try:
            evaluation["dimensions"] = decode(turn["dimensions"])
            evaluation["content_analysis"] = decode(turn["content_analysis"])
            from filemate.interview_review.models import validate_saved_analysis

            validate_saved_analysis(evaluation["content_analysis"], turn["answer"])
            if not math.isfinite(turn["score"]) or not 0 <= turn["score"] <= 100:
                raise ValueError("invalid score")
        except (ValueError, TypeError):
            pass
        else:
            conn.execute(
                "INSERT INTO interview_coach_analysis_runs "
                "(run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,"
                "review_revision,provider_identity,model,prompt_version,rubric_version,status,evaluation,created_at) "
                "VALUES (?,?,?,1,?,?,0,0,'legacy_unknown','legacy_unknown','legacy_unknown','legacy_unknown','succeeded',?,?)",
                (
                    uuid.uuid4().hex,
                    turn["interview_id"],
                    attempt_id,
                    "legacy_" + attempt_id,
                    digest(turn["answer"]),
                    json.dumps(evaluation, ensure_ascii=False),
                    turn["created_at"],
                ),
            )
    row = conn.execute(
        "SELECT * FROM interview_answer_attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    return attempt_view(conn, row)


def backfill_legacy_attempts(conn: sqlite3.Connection) -> int:
    if not conn.in_transaction:
        raise RuntimeError("backfill requires an active transaction")
    rows = conn.execute(
        "SELECT turn_id FROM interview_turns t WHERE NOT EXISTS "
        "(SELECT 1 FROM interview_answer_attempts a WHERE a.turn_id=t.turn_id)"
    ).fetchall()
    for row in rows:
        record_attempt_from_turn(conn, row["turn_id"], origin="migrated")
    for session in conn.execute(
        "SELECT s.* FROM interview_sessions s WHERE NOT EXISTS "
        "(SELECT 1 FROM interview_coach_state c WHERE c.interview_id=s.interview_id)"
    ).fetchall():
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
                conn.execute("BEGIN IMMEDIATE")
                yield conn

    def _state(self, conn, interview_id):
        if not conn.execute(
            "SELECT 1 FROM interview_sessions WHERE interview_id=?", (interview_id,)
        ).fetchone():
            raise CoachError("interview_not_found", 404)
        row = conn.execute(
            "SELECT * FROM interview_coach_state WHERE interview_id=?", (interview_id,)
        ).fetchone()
        if row is None:
            raise CoachError("coach_data_error")
        return row

    def snapshot(self, interview_id: str) -> CoachSnapshot:
        conn = self.storage._conn()
        session = self.storage.get_interview(interview_id)
        if session is None:
            raise CoachError("interview_not_found", 404)
        row = conn.execute(
            "SELECT * FROM interview_coach_state WHERE interview_id=?", (interview_id,)
        ).fetchone()
        if row is None:
            return CoachSnapshot(
                session=session,
                revision=0,
                displayed_index=0,
                phase="question",
                external_consent=False,
                consent_revision=0,
                provider_identity="",
                data_error=True,
            )
        values = dict(row)
        data_error = False
        try:
            entered = decode(row["entered_indices"], list)
            if row["displayed_index"] not in entered or row["phase"] not in {
                "question",
                "feedback",
                "summary",
            }:
                raise ValueError("invalid coach state")
        except (TypeError, ValueError):
            data_error = True
        index = row["displayed_index"]
        attempt = conn.execute(
            "SELECT * FROM interview_answer_attempts WHERE interview_id=? AND question_index=? "
            "ORDER BY version DESC LIMIT 1",
            (interview_id, index),
        ).fetchone()
        active = conn.execute(
            "SELECT run_id FROM interview_coach_analysis_runs WHERE interview_id=? AND status IN ('running','cancelling')",
            (interview_id,),
        ).fetchone()
        retries = conn.execute(
            "SELECT a.attempt_id FROM interview_answer_attempts a WHERE a.interview_id=? "
            "AND a.version=(SELECT MAX(b.version) FROM interview_answer_attempts b WHERE b.turn_id=a.turn_id) "
            "AND EXISTS (SELECT 1 FROM interview_coach_analysis_runs r WHERE r.attempt_id=a.attempt_id "
            "AND r.attempt_seq=(SELECT MAX(x.attempt_seq) FROM interview_coach_analysis_runs x WHERE x.attempt_id=a.attempt_id) "
            "AND r.status IN ('failed','cancelled','interrupted'))",
            (interview_id,),
        ).fetchall()
        selected = attempt_view(conn, attempt) if attempt else None
        projected = next((t for t in session['turns'] if t['question_index'] == index), None)
        if selected and projected and projected.get('analysis_data_error'):
            selected = selected.model_copy(update={'score':None,'evaluation':{},'data_error':True,'analysis_status':'failed'})
        return CoachSnapshot(
            session=session,
            revision=values["revision"],
            displayed_index=index,
            phase=values["phase"] if not data_error else "question",
            external_consent=bool(values["external_consent"]) and not data_error,
            consent_revision=values["consent_revision"],
            provider_identity=values["provider_identity"],
            current_attempt=selected,
            active_run_id=active["run_id"] if active else None,
            pending_retries=[r[0] for r in retries],
            data_error=data_error,
        )

    def _previous(self, conn, sid, kind, command):
        row = conn.execute(
            "SELECT * FROM interview_coach_actions WHERE interview_id=? AND request_key=?",
            (sid, command.request_key),
        ).fetchone()
        if row:
            if row["kind"] != kind or row["input_digest"] != digest(command.model_dump()):
                raise CoachError("request_key_conflict")
            return decode(row["result_refs"])
        return None

    def _check(self, conn, sid, command):
        state = self._state(conn, sid)
        if state["revision"] != command.expected_revision:
            raise CoachError("revision_conflict")
        view = self.snapshot(sid)
        if view.data_error:
            raise CoachError("coach_data_error")
        return state

    def _receipt(self, conn, sid, kind, command, **refs):
        result = {"kind": kind, "request_key": command.request_key, **refs}
        conn.execute(
            "INSERT INTO interview_coach_actions VALUES (?,?,?,?,?,?)",
            (
                sid,
                command.request_key,
                kind,
                digest(command.model_dump()),
                json.dumps(result, ensure_ascii=False),
                now(),
            ),
        )
        return result

    def _result(self, sid, receipt):
        return CoachMutationResult(snapshot=self.snapshot(sid), receipt=receipt)

    def _invalidate(self, conn, sid):
        conn.execute(
            "UPDATE interview_coach_analysis_runs SET status='cancelling' WHERE interview_id=? AND status='running'",
            (sid,),
        )
        conn.execute(
            "INSERT INTO interview_review_state(interview_id,revision) VALUES (?,1) "
            "ON CONFLICT(interview_id) DO UPDATE SET revision=revision+1,input_digest=''",
            (sid,),
        )

    def submit(self, interview_id: str, command: SubmitAnswer) -> CoachMutationResult:
        from .commands import local_evaluation

        # Local computation happens before taking the cross-connection write lock.
        session = self.storage.get_interview(interview_id)
        if session is None:
            raise CoachError("interview_not_found", 404)
        evaluation = local_evaluation(
            command.answer,
            command.fluency_metrics,
            speech_language="en-US" if session["scenario"] == "英语面" else "zh-CN",
        )
        with self.transaction() as conn:
            old = self._previous(conn, interview_id, "submit", command)
            if old:
                return self._result(interview_id, old)
            state = self._check(conn, interview_id, command)
            frozen = conn.execute(
                "SELECT * FROM interview_coach_questions WHERE interview_id=? AND question_index=?",
                (interview_id, command.question_index),
            ).fetchone()
            if frozen is None:
                raise CoachError("question_not_entered")
            existing = conn.execute(
                "SELECT * FROM interview_turns WHERE interview_id=? AND question_index=?",
                (interview_id, command.question_index),
            ).fetchone()
            latest = conn.execute(
                "SELECT attempt_id FROM interview_answer_attempts WHERE interview_id=? AND question_index=? "
                "ORDER BY version DESC LIMIT 1",
                (interview_id, command.question_index),
            ).fetchone()
            if (latest[0] if latest else None) != command.expected_attempt_id:
                raise CoachError("attempt_conflict")
            if existing is None:
                if command.question_index != state["displayed_index"]:
                    raise CoachError("question_conflict")
                payload = {
                    "interview_id": interview_id,
                    "question_index": command.question_index,
                    "question": frozen["question"],
                    "answer": command.answer,
                    "score": None,
                    "dimensions": evaluation["dimensions"],
                    "feedback": evaluation["feedback"],
                    "fluency_metrics": command.fluency_metrics,
                    "scoring_mode": "local_fallback",
                    "scoring_version": "coach-local-v1",
                    "next_question": None,
                    "expression_review": None,
                    "visual_metrics": command.visual_metrics,
                    "content_analysis": None,
                    "answer_key": command.request_key,
                    "answer_digest": digest(command.model_dump()),
                }
                turn_id = self.storage._save_interview_turn_tx(
                    conn, payload=payload, origin="coach"
                )
            else:
                turn_id = existing["turn_id"]
                self._invalidate(conn, interview_id)
                conn.execute(
                    "UPDATE interview_turns SET answer=?,score=0,dimensions=?,feedback=?,fluency_metrics=?,"
                    "visual_metrics=?,content_analysis='{}',scoring_mode='local_fallback',scoring_version='coach-local-v1' "
                    "WHERE turn_id=?",
                    (
                        command.answer,
                        json.dumps(evaluation["dimensions"], ensure_ascii=False),
                        evaluation["feedback"],
                        json.dumps(command.fluency_metrics or {}, ensure_ascii=False),
                        json.dumps(command.visual_metrics or {}, ensure_ascii=False),
                        turn_id,
                    ),
                )
                record_attempt_from_turn(conn, turn_id, origin="coach")
                conn.execute(
                    "UPDATE interview_coach_state SET revision=revision+1,displayed_index=?,phase='feedback',updated_at=? WHERE interview_id=?",
                    (command.question_index, now(), interview_id),
                )
                self._sync_score(conn, interview_id)
            attempt = conn.execute(
                "SELECT attempt_id FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1",
                (turn_id,),
            ).fetchone()
            receipt = self._receipt(conn, interview_id, "submit", command, attempt_id=attempt[0])
            return self._result(interview_id, receipt)

    def _sync_score(self, conn, sid):
        session = self.storage.get_interview(sid)
        values = [t['score'] for t in session['turns'] if t['score'] is not None]
        conn.execute('UPDATE interview_sessions SET overall_score=?,updated_at=? WHERE interview_id=?',
                     (round(sum(values) / len(values), 2) if values else 0, now(), sid))
        for turn in session['turns']:
            value = turn['score'] if turn['score'] is not None else '待分析'
            summary = f"第{turn['question_index']+1}题第{turn.get('attempt_version',1)}版，模型参考分{value}"
            conn.execute("UPDATE agent_memories SET summary=?,updated_at=? WHERE scope_id=? AND source_type='interview_turn' AND source_id=?",
                         (summary,now(),sid,f"{sid}:{turn['question_index']}"))

    def advance(self, interview_id: str, command: AdvanceCommand) -> CoachMutationResult:
        from filemate.understanding.interview_practice import grounded_followup

        view = self.snapshot(interview_id)
        followup = None
        run = self.storage.get_agent_run(view.session['agent_run_id']) if view.session.get('agent_run_id') else None
        continuous = (run or {}).get('context_refs', {}).get('practice_mode') == 'continuous'
        from filemate.understanding.interview_practice import SPECIALIST_QUESTIONS

        if view.current_attempt and (continuous or view.session['scenario'] in SPECIALIST_QUESTIONS):
            followup = grounded_followup(
                view.current_attempt.answer,
                view.session["scenario"],
                command.from_index + 1,
                view.current_attempt.evaluation.get("content_analysis"),
                difficulty=view.session["difficulty"],
            )
        with self.transaction() as conn:
            old = self._previous(conn, interview_id, "advance", command)
            if old:
                return self._result(interview_id, old)
            state = self._check(conn, interview_id, command)
            current = self.snapshot(interview_id)
            if (
                state["phase"] != "feedback"
                or state["displayed_index"] != command.from_index
                or not current.current_attempt
                or current.current_attempt.attempt_id != command.expected_attempt_id
            ):
                raise CoachError("advance_conflict")
            target = command.from_index + 1
            questions = list(current.session["questions"])
            if target >= len(questions):
                phase, displayed = "summary", command.from_index
            else:
                frozen = conn.execute(
                    "SELECT 1 FROM interview_coach_questions WHERE interview_id=? AND question_index=?",
                    (interview_id, target),
                ).fetchone()
                if not frozen:
                    if followup:
                        questions[target] = followup
                        ids = list(current.session["question_ids"])
                        ids[target] = None
                        conn.execute(
                            "UPDATE interview_sessions SET questions=?,question_ids=? WHERE interview_id=?",
                            (
                                json.dumps(questions, ensure_ascii=False),
                                json.dumps(ids),
                                interview_id,
                            ),
                        )
                    freeze_question(conn, interview_id, target, questions[target], now())
                answered = conn.execute(
                    "SELECT 1 FROM interview_answer_attempts WHERE interview_id=? AND question_index=?",
                    (interview_id, target),
                ).fetchone()
                phase, displayed = ("feedback" if answered else "question"), target
            entered = [
                r[0]
                for r in conn.execute(
                    "SELECT question_index FROM interview_coach_questions WHERE interview_id=? ORDER BY question_index",
                    (interview_id,),
                )
            ]
            conn.execute(
                "UPDATE interview_coach_state SET revision=revision+1,displayed_index=?,phase=?,entered_indices=?,updated_at=? WHERE interview_id=?",
                (displayed, phase, json.dumps(entered), now(), interview_id),
            )
            receipt = self._receipt(conn, interview_id, "advance", command, target_index=target)
            return self._result(interview_id, receipt)

    def list_attempts(
        self, interview_id: str, turn_id: str, *, limit: int = 20, before_version: int | None = None
    ) -> dict[str, Any]:
        conn = self.storage._conn()
        if not conn.execute(
            "SELECT 1 FROM interview_turns WHERE interview_id=? AND turn_id=?",
            (interview_id, turn_id),
        ).fetchone():
            raise CoachError("turn_not_found", 404)
        limit = max(1, min(limit, 100))
        rows = conn.execute(
            "SELECT * FROM interview_answer_attempts WHERE interview_id=? AND turn_id=? AND version<? "
            "ORDER BY version DESC LIMIT ?",
            (interview_id, turn_id, before_version or 2147483647, limit + 1),
        ).fetchall()
        return {
            "items": [attempt_view(conn, r).model_dump() for r in rows[:limit]],
            "next_before_version": rows[limit - 1]["version"] if len(rows) > limit else None,
        }

    def set_consent(
        self, interview_id: str, command: ConsentCommand, *, provider_identity: str
    ) -> CoachMutationResult:
        with self.transaction() as conn:
            old = self._previous(conn, interview_id, "consent", command)
            if old:
                return self._result(interview_id, old)
            state = self._check(conn, interview_id, command)
            if not command.allowed or state["provider_identity"] != provider_identity:
                self._invalidate(conn, interview_id)
            conn.execute(
                "UPDATE interview_coach_state SET revision=revision+1,external_consent=?,consent_revision=consent_revision+1,"
                "provider_identity=?,updated_at=? WHERE interview_id=?",
                (int(command.allowed), provider_identity, now(), interview_id),
            )
            receipt = self._receipt(conn, interview_id, "consent", command)
            self._event(conn, interview_id, "coach_consent", {"allowed": command.allowed})
            return self._result(interview_id, receipt)

    def _event(self, conn, sid, action, detail):
        conn.execute(
            "INSERT INTO interview_review_events(interview_id,action,detail,created_at) VALUES (?,?,?,?)",
            (sid, action, json.dumps(detail), now()),
        )

    def _interrupt_tx(self, conn, sid, instant):
        cursor = conn.execute(
            "UPDATE interview_coach_analysis_runs SET status='interrupted',evaluation='{}',error_code='interrupted',finished_at=? "
            "WHERE interview_id=? AND status IN ('running','cancelling') AND lease_until<=?",
            (instant.isoformat(), sid, instant.isoformat()),
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE interview_coach_state SET revision=revision+1,updated_at=? WHERE interview_id=?",
                (now(), sid),
            )
        return cursor.rowcount

    def interrupt_expired(self, interview_id: str, *, now: datetime) -> int:
        with self.transaction() as conn:
            self._state(conn, interview_id)
            return self._interrupt_tx(conn, interview_id, now)

    def claim_analysis(
        self,
        interview_id: str,
        command: AnalysisCommand,
        *,
        provider_identity: str,
        model: str,
        one_shot_consent: bool = False,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
            self._interrupt_tx(conn, interview_id, datetime.now(timezone.utc))
            old = self._previous(conn, interview_id, "analysis", command)
            if old:
                run = conn.execute(
                    "SELECT * FROM interview_coach_analysis_runs WHERE run_id=?", (old["run_id"],)
                ).fetchone()
                return {"execute": False, "receipt": old, "run": dict(run)}
            state = self._check(conn, interview_id, command)
            if state["consent_revision"] != command.consent_revision or (
                not one_shot_consent
                and (
                    not state["external_consent"] or state["provider_identity"] != provider_identity
                )
            ):
                raise CoachError("consent_required")
            if one_shot_consent and state["provider_identity"] != provider_identity:
                conn.execute("UPDATE interview_coach_state SET external_consent=0,consent_revision=consent_revision+1,provider_identity=? WHERE interview_id=?",
                             (provider_identity, interview_id))
                state = self._state(conn, interview_id)
            attempt = conn.execute(
                "SELECT * FROM interview_answer_attempts WHERE interview_id=? AND attempt_id=?",
                (interview_id, command.attempt_id),
            ).fetchone()
            if attempt is None:
                raise CoachError("attempt_not_found", 404)
            latest = conn.execute(
                "SELECT attempt_id FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1",
                (attempt["turn_id"],),
            ).fetchone()[0]
            if latest != command.attempt_id:
                raise CoachError("attempt_conflict")
            if conn.execute(
                "SELECT 1 FROM interview_coach_analysis_runs WHERE interview_id=? AND status IN ('running','cancelling')",
                (interview_id,),
            ).fetchone():
                raise CoachError("analysis_in_progress")
            view = attempt_view(conn, attempt)
            if view.data_error:
                raise CoachError("attempt_data_error")
            conn.execute(
                "INSERT OR IGNORE INTO interview_review_state(interview_id) VALUES (?)",
                (interview_id,),
            )
            review_revision = conn.execute(
                "SELECT revision FROM interview_review_state WHERE interview_id=?", (interview_id,)
            ).fetchone()[0]
            seq = conn.execute(
                "SELECT COALESCE(MAX(attempt_seq),0)+1 FROM interview_coach_analysis_runs WHERE attempt_id=?",
                (command.attempt_id,),
            ).fetchone()[0]
            run_id = uuid.uuid4().hex
            instant = datetime.now(timezone.utc)
            conn.execute(
                "INSERT INTO interview_coach_analysis_runs "
                "(run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,review_revision,"
                "provider_identity,model,prompt_version,rubric_version,status,deadline_at,lease_until,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?, 'interview-excerpts-v1','four-dim-six-area-v1','running',?,?,?)",
                (
                    run_id,
                    interview_id,
                    command.attempt_id,
                    seq,
                    command.request_key,
                    attempt["input_digest"],
                    state["consent_revision"],
                    review_revision,
                    provider_identity,
                    model,
                    (instant + timedelta(seconds=60)).isoformat(),
                    (instant + timedelta(seconds=65)).isoformat(),
                    instant.isoformat(),
                ),
            )
            conn.execute(
                "UPDATE interview_turns SET score=0,dimensions='{}',content_analysis='{}',scoring_mode='local_fallback',"
                "feedback='回答已保存，正在分析当前版本。' WHERE turn_id=?",
                (attempt["turn_id"],),
            )
            conn.execute(
                "UPDATE interview_review_state SET input_digest='' WHERE interview_id=?",
                (interview_id,),
            )
            conn.execute(
                "UPDATE interview_coach_state SET revision=revision+1,updated_at=? WHERE interview_id=?",
                (now(), interview_id),
            )
            self._sync_score(conn, interview_id)
            receipt = self._receipt(
                conn,
                interview_id,
                "analysis",
                command,
                attempt_id=command.attempt_id,
                run_id=run_id,
            )
            self._event(
                conn,
                interview_id,
                "coach_analysis_started",
                {"run_id": run_id, "attempt_id": command.attempt_id},
            )
            run = dict(
                conn.execute(
                    "SELECT * FROM interview_coach_analysis_runs WHERE run_id=?", (run_id,)
                ).fetchone()
            )
            return {"execute": True, "receipt": receipt, "run": run, "attempt": view.model_dump()}

    def finish_analysis(
        self, run_id: str, *, evaluation: dict[str, Any] | None, error_code: str | None
    ) -> CoachSnapshot:
        from filemate.interview_review.models import validate_saved_analysis

        with self.transaction() as conn:
            run = conn.execute(
                "SELECT * FROM interview_coach_analysis_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise CoachError("analysis_not_found", 404)
            sid = run["interview_id"]
            if run["status"] not in {"running", "cancelling"}:
                return self.snapshot(sid)
            state = self._state(conn, sid)
            attempt = conn.execute(
                "SELECT * FROM interview_answer_attempts WHERE attempt_id=?", (run["attempt_id"],)
            ).fetchone()
            latest = conn.execute(
                "SELECT attempt_id FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1",
                (attempt["turn_id"],),
            ).fetchone()[0]
            review = conn.execute(
                "SELECT revision FROM interview_review_state WHERE interview_id=?", (sid,)
            ).fetchone()
            fresh = (
                run["status"] == "running"
                and latest == run["attempt_id"]
                and state["consent_revision"] == run["consent_revision"]
                and review[0] == run["review_revision"]
                and state["provider_identity"] in {"", run["provider_identity"]}
                and datetime.now(timezone.utc) <= datetime.fromisoformat(run["deadline_at"])
            )
            if not fresh:
                status, evaluation, error_code = "cancelled", None, "superseded"
            else:
                if evaluation:
                    try:
                        validate_saved_analysis(evaluation["content_analysis"], attempt["answer"])
                        score = evaluation["score"]
                        if (
                            isinstance(score, bool)
                            or not isinstance(score, (int, float))
                            or not math.isfinite(score)
                            or not 0 <= score <= 100
                        ):
                            raise ValueError("invalid score")
                    except (KeyError, ValueError, TypeError):
                        evaluation, error_code = None, "invalid_evidence"
                status = "succeeded" if evaluation else "failed"
            conn.execute(
                "UPDATE interview_coach_analysis_runs SET status=?,evaluation=?,error_code=?,finished_at=? WHERE run_id=?",
                (
                    status,
                    json.dumps(evaluation or {}, ensure_ascii=False),
                    error_code,
                    now(),
                    run_id,
                ),
            )
            if fresh:
                if evaluation:
                    conn.execute(
                        "UPDATE interview_turns SET score=?,dimensions=?,feedback=?,scoring_mode='llm',"
                        "scoring_version='coach-v1',content_analysis=? WHERE turn_id=?",
                        (
                            evaluation["score"],
                            json.dumps(evaluation["dimensions"], ensure_ascii=False),
                            evaluation["feedback"],
                            json.dumps(evaluation["content_analysis"], ensure_ascii=False),
                            attempt["turn_id"],
                        ),
                    )
                else:
                    conn.execute(
                        "UPDATE interview_turns SET feedback='当前回答分析未完成，原文已保存，可主动重试。' WHERE turn_id=?",
                        (attempt["turn_id"],),
                    )
                conn.execute(
                    "UPDATE interview_review_state SET revision=revision+1,input_digest='' WHERE interview_id=?",
                    (sid,),
                )
            conn.execute(
                "UPDATE interview_coach_state SET revision=revision+1,updated_at=? WHERE interview_id=?",
                (now(), sid),
            )
            self._sync_score(conn, sid)
            self._event(
                conn,
                sid,
                "coach_analysis_finished",
                {"run_id": run_id, "status": status, "error_code": error_code},
            )
            return self.snapshot(sid)

    def cancel_analysis(self, interview_id: str) -> CoachSnapshot:
        from filemate.interview_review.repository import ReviewRepository

        ReviewRepository(self.storage).cancel(interview_id)
        return self.snapshot(interview_id)


def _provenance(conn: sqlite3.Connection, run_id: str | None) -> dict[str, Any]:
    row = conn.execute('SELECT provider_identity,model,prompt_version,rubric_version,created_at,finished_at '
                       'FROM interview_coach_analysis_runs WHERE run_id=?', (run_id,)).fetchone()
    return dict(row) if row else {}


def current_attempt_projection(conn: sqlite3.Connection, turn_id: str) -> dict[str, Any]:
    from filemate.interview_review.models import VisualMetrics, validate_saved_analysis

    raw = conn.execute('SELECT * FROM interview_turns WHERE turn_id=?', (turn_id,)).fetchone()
    if raw is None:
        raise CoachError('turn_not_found', 404)
    result = dict(raw)
    row = conn.execute('SELECT * FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1', (turn_id,)).fetchone()
    if row is None:
        return {**result, 'dimensions': {}, 'fluency_metrics': {}, 'visual_metrics': {}, 'content_analysis': {},
                'score': None, 'scoring_mode': 'unknown', 'analysis_status': 'unrequested', 'analysis_data_error': True}
    view = attempt_view(conn, row)
    broken = view.data_error
    cached = {}
    for key in ('dimensions', 'fluency_metrics', 'visual_metrics', 'content_analysis'):
        try:
            value = decode(raw[key])
            if key == 'content_analysis' and value:
                value = validate_saved_analysis(value, view.answer)
            if key == 'visual_metrics' and value:
                value = VisualMetrics.model_validate(value).model_dump()
            cached[key] = value
        except (ValueError, TypeError):
            cached[key], broken = {}, True
    if view.score is not None and cached['content_analysis'] != view.evaluation.get('content_analysis'):
        broken = True
    if raw['answer'] != view.answer or raw['question'] != view.question:
        broken = True
    score = view.score if not broken else None
    result.update(question=view.question, answer=view.answer, score=score,
                  dimensions=view.evaluation.get('dimensions', {}) if score is not None else
                  {k: v for k, v in cached['dimensions'].items() if k == '流畅性' and not broken},
                  fluency_metrics=view.fluency_metrics, visual_metrics=cached['visual_metrics'],
                  content_analysis=view.evaluation.get('content_analysis', {}) if score is not None else {},
                  scoring_mode='llm' if score is not None else (raw['scoring_mode'] if raw['scoring_mode'] != 'llm' else 'local_fallback'),
                  feedback=view.evaluation.get('feedback', '') if score is not None else
                  raw['feedback'] if raw['scoring_mode'] != 'llm' and not broken else '当前版本待分析，原回答保留。',
                  attempt_id=view.attempt_id, attempt_version=view.version, attempt_created_at=view.created_at,
                  analysis_status='failed' if broken else view.analysis_status, analysis_run_id=view.latest_run_id,
                  source_revision=digest([view.attempt_id, view.latest_run_id, view.analysis_status]),
                  analysis_provenance=_provenance(conn, view.latest_run_id), analysis_data_error=broken)
    result['attempt_comparison'] = attempt_comparison(conn, turn_id)
    return result


def attempt_comparison(conn: sqlite3.Connection, turn_id: str) -> dict[str, Any]:
    first = conn.execute('SELECT * FROM interview_answer_attempts WHERE turn_id=? ORDER BY version LIMIT 1', (turn_id,)).fetchone()
    last = conn.execute('SELECT * FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1', (turn_id,)).fetchone()
    if first is None:
        return {'first': None, 'last': None, 'scores_comparable': False}
    a, b = attempt_view(conn, first), attempt_view(conn, last)
    pa, pb = _provenance(conn, a.latest_run_id), _provenance(conn, b.latest_run_id)
    keys = ('provider_identity', 'model', 'prompt_version', 'rubric_version')
    comparable = (a.score is not None and b.score is not None and not a.data_error and not b.data_error
                  and all(pa.get(k) and pa.get(k) != 'legacy_unknown' and pa.get(k) == pb.get(k) for k in keys))
    return {'first': {**a.model_dump(), 'provenance': pa}, 'last': {**b.model_dump(), 'provenance': pb},
            'scores_comparable': comparable,
            'notice': '仅比较各版原文与模型参考；来源不同或分析未完成时不比较分数，不推断能力进步。'}


def record_legacy_analysis(conn: sqlite3.Connection, turn_id: str, evaluation: dict[str, Any]) -> None:
    attempt = conn.execute('SELECT * FROM interview_answer_attempts WHERE turn_id=? ORDER BY version DESC LIMIT 1', (turn_id,)).fetchone()
    if conn.execute("SELECT 1 FROM interview_coach_analysis_runs WHERE interview_id=? AND status IN ('running','cancelling')", (attempt['interview_id'],)).fetchone():
        raise ValueError('本场已有分析正在结束')
    sequence = conn.execute('SELECT COALESCE(MAX(attempt_seq),0)+1 FROM interview_coach_analysis_runs WHERE attempt_id=?', (attempt['attempt_id'],)).fetchone()[0]
    conn.execute('INSERT INTO interview_coach_analysis_runs '
                 '(run_id,interview_id,attempt_id,attempt_seq,request_key,input_digest,consent_revision,review_revision,provider_identity,model,prompt_version,rubric_version,status,evaluation,created_at,finished_at) '
                 "VALUES (?,?,?,?,?,?,0,0,'legacy_unknown','legacy_unknown','legacy_unknown','legacy_unknown','succeeded',?,?,?)",
                 (uuid.uuid4().hex, attempt['interview_id'], attempt['attempt_id'], sequence, 'legacy_apply_' + uuid.uuid4().hex,
                  attempt['input_digest'], json.dumps(evaluation, ensure_ascii=False), now(), now()))
