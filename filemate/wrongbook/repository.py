"""Transactional, tenant-bound review evidence and read projections."""

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from filemate.execution.data_actions import digest
from filemate.execution.storage import QuestionRevisionConflict, SQLiteStorage, _knowledge_identity
from filemate.study.generator import check_answer
from filemate.study.question_validation import validate_question
from filemate.wrongbook.engine import LOCAL_ZONE, RULE_VERSION, parse_time, transition
from filemate.wrongbook.models import Answer, Diagnosis

STATE_FIELDS = (
    "learning_status", "schedule_status", "scheduler_version", "review_stage", "eligible_count",
    "first_verified_at", "last_verified_at", "correct_streak", "mastered", "interval_days",
    "next_review_at", "paused_at", "revision", "error_cause", "error_cause_source",
    "error_cause_confidence", "error_cause_note", "error_causes", "custom_tags", "diagnosed_at",
    "legacy_mastered",
)
ENGINE_FIELDS = STATE_FIELDS[:12]


class ReviewRepository:
    def __init__(self, storage: SQLiteStorage, *, clock: Callable[[], datetime] | None = None):
        self.storage = storage
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def now(self) -> datetime:
        """Return a server-owned timezone-aware clock."""
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("复习时钟缺少时区")
        return value.astimezone(timezone.utc)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Serialize the evidence, state and receipt in one write transaction."""
        with self.storage._write_lock:
            conn = self.storage._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def detail(self, wrong_id: str) -> dict:
        """Read one scoped wrong record without inferring unavailable evidence."""
        try:
            row = self.storage.get_wrong_question(wrong_id)
        except (ValueError, TypeError):
            raw = self.storage._conn().execute('SELECT * FROM wrong_questions WHERE wrong_id=?', (wrong_id,)).fetchone()
            row = {**dict(raw), 'question': {}, 'data_error': True} if raw else None
        if row is None:
            raise LookupError("错题不存在")
        if not isinstance(row.get('question'), dict):
            row.update(question={}, data_error=True)
        for field in ("error_causes", "custom_tags"):
            try:
                row[field] = json.loads(row[field]) if isinstance(row[field], str) else row[field]
                if not isinstance(row[field], list):
                    raise TypeError("invalid list")
            except (ValueError, TypeError, KeyError):
                row[field] = []
                row["data_error"] = True
        if not row["error_causes"] and row["error_cause"] != "unconfirmed":
            row["error_causes"] = [row["error_cause"]]
        row["legacy_mastered"] = bool(row.get("legacy_mastered")) or row["scheduler_version"] != RULE_VERSION and bool(row["mastered"])
        row["data_error"] = row.get("data_error", False) or parse_time(row.get("next_review_at")) is None
        artifact = self.storage.get_artifact(row["artifact_id"])
        row["read_only_snapshot"] = bool(artifact and artifact.get("metadata", {}).get("read_only_snapshot"))
        row['question_digest'] = digest(row['question'])
        return row

    @staticmethod
    def state(row: dict | None) -> dict:
        """Keep event state bounded to review decisions rather than source content."""
        return {key: row.get(key) for key in STATE_FIELDS} if row else {}

    def replay(self, conn: Any, key: str, fingerprint: str) -> dict | None:
        """Replay the same operation; a reused key cannot describe a different write."""
        old = conn.execute("SELECT input_digest,result FROM review_events WHERE request_key=?", (key,)).fetchone()
        if old is None:
            return None
        if old["input_digest"] != fingerprint:
            raise QuestionRevisionConflict("操作标识已用于其他内容，请保留原稿并重新预览")
        return json.loads(old["result"])

    def event(self, conn: Any, *, row: dict, action: str, key: str, fingerprint: str,
              before: dict, after: dict, result: dict, attempt_id: str | None = None,
              undo_of: str | None = None) -> dict:
        """Persist the response beside its state transition for safe uncertain retries."""
        event_id = uuid.uuid4().hex
        result = {**result, "review_event_id": event_id}
        conn.execute("""INSERT INTO review_events
            (event_id,artifact_id,wrong_id,attempt_id,action,request_key,input_digest,
             before_state,after_state,result,undo_of,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, row["artifact_id"], row.get("wrong_id"), attempt_id, action, key, fingerprint,
             json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False), undo_of, self.now().isoformat(timespec="seconds")))
        return result

    def submit(self, payload: dict) -> dict:
        """Validate the actual question and save an independent versioned answer."""
        command = Answer.model_validate(payload)
        body = command.model_dump()
        fingerprint = digest({"operation": "answer", **body})
        with self.transaction() as conn:
            replay = self.replay(conn, command.request_key, fingerprint)
            if replay is not None:
                return replay
            artifact = self.storage.get_artifact(command.artifact_id)
            if artifact is None:
                raise LookupError("题目集不存在")
            questions = artifact.get("content")
            if artifact["artifact_type"] != "questions" or not isinstance(questions, list):
                raise ValueError("该产物不是有效题集")
            if artifact.get("metadata", {}).get("read_only_snapshot"):
                raise QuestionRevisionConflict("历史题集只读，请在当前版本作答")
            if command.question_index >= len(questions) or questions[command.question_index] != command.expected_question:
                raise QuestionRevisionConflict("题目已变化，请刷新后作答，原稿保留")
            raw = questions[command.question_index]
            question = validate_question(raw, legacy=True)
            previous = conn.execute("SELECT wrong_id FROM wrong_questions WHERE artifact_id=? AND question_index=?",
                                    (command.artifact_id, command.question_index)).fetchone()
            old = self.detail(previous["wrong_id"]) if previous else None
            if old and old["scheduler_version"] != RULE_VERSION and old["mastered"]:
                raise QuestionRevisionConflict("历史两次复练结果保留；请先预览并确认启用新复习规则")
            self_reported = command.action == "dont_know" or command.self_reported_result is not None
            correct = None if self_reported or question["question_type"] == "short_answer" else check_answer(question, command.user_answer)
            status = "self_reported" if self_reported else "pending" if correct is None else "assisted" if command.answer_revealed else "verified"
            verified_wrong = correct is False and status == "verified"
            method = "self_report" if self_reported else "ungraded" if correct is None else "objective_rule"
            state = transition(old, correct=correct, independent=not command.answer_revealed, now=self.now())
            if old is None and conn.execute(
                "SELECT 1 FROM quiz_attempts WHERE artifact_id=? AND question_index=? LIMIT 1",
                (command.artifact_id, command.question_index),
            ).fetchone():
                state["purpose"] = "practice"
            stamp = self.now().isoformat(timespec="seconds")
            attempt_id = uuid.uuid4().hex
            feedback = "待核对：不计入确定对错" if correct is None else "客观规则核对正确" if correct else "客观规则核对未通过"
            conn.execute("""INSERT INTO quiz_attempts
                (attempt_id,artifact_id,source_id,question_index,user_answer,is_correct,score,feedback,created_at,
                 purpose,judgement_method,judgement_status,rule_version,question_digest,answer_revealed,
                 duration_ms,duration_source,self_reported_result) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (attempt_id, command.artifact_id, artifact.get("source_id"), command.question_index,
                 command.user_answer, int(correct) if correct is not None else None,
                 float(correct) if correct is not None else None, feedback, stamp, state["purpose"], method, status,
                 RULE_VERSION, digest(raw), int(command.answer_revealed), command.duration_ms,
                 "client_reported" if command.duration_ms is not None else None,
                 command.self_reported_result or ("unsure" if self_reported else None)))
            if old is None and correct is not True:
                wid = uuid.uuid4().hex
                knowledge_key, knowledge_label = _knowledge_identity(raw, source_id=artifact.get("source_id"), artifact_id=command.artifact_id)
                conn.execute("""INSERT INTO wrong_questions
                    (wrong_id,artifact_id,source_id,question_index,question,latest_answer,error_count,review_count,
                     knowledge_key,knowledge_label,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,0,?,?,?,?)""",
                    (wid, command.artifact_id, artifact.get("source_id"), command.question_index,
                     json.dumps(raw, ensure_ascii=False), command.user_answer, int(verified_wrong),
                     knowledge_key, knowledge_label, stamp, stamp))
            else:
                wid = old["wrong_id"] if old else None
            if wid:
                changes = {key: state[key] for key in ENGINE_FIELDS}
                changes.update(latest_answer=command.user_answer, updated_at=stamp,
                               revision=old["revision"] + 1 if old else 1,
                               review_attempt_count=(old["review_attempt_count"] + 1) if old else 0)
                if old:
                    changes.update(error_count=old["error_count"] + int(verified_wrong),
                                   review_count=old["review_count"] + 1)
                conn.execute("UPDATE wrong_questions SET " + ",".join(f"{key}=?" for key in changes) + " WHERE wrong_id=?",
                             [*changes.values(), wid])
            after = self.state(self.detail(wid)) if wid else {}
            result = {"attempt_id": attempt_id, "wrong_id": wid, "is_correct": correct,
                      "score": float(correct) if correct is not None else None, "feedback": feedback,
                      "judgement_method": method, "judgement_status": status, "rule_version": RULE_VERSION,
                      "reference_answer": question["answer"], "eligible": state["eligible"],
                      "reason": state["reason"], "before": self.state(old), "after": after}
            return self.event(conn, row={"artifact_id": command.artifact_id, "wrong_id": wid},
                              action="answer", key=command.request_key, fingerprint=fingerprint,
                              before=self.state(old), after=after, result=result, attempt_id=attempt_id)

    def diagnose(self, wrong_id: str, payload: dict) -> dict:
        """Persist only user-chosen causes, including an explicit clearing action."""
        command = Diagnosis.model_validate(payload)
        fingerprint = digest({"operation": "diagnosis", "wrong_id": wrong_id, **command.model_dump()})
        with self.transaction() as conn:
            replay = self.replay(conn, command.request_key, fingerprint)
            if replay is not None:
                return replay
            old = self.detail(wrong_id)
            if command.expected_revision != old["revision"]:
                raise QuestionRevisionConflict("错题已变化，请重新读取后确认错因")
            primary = command.primary_cause or next(iter(command.error_causes), "unconfirmed")
            confirmed = primary != "unconfirmed"
            stamp = self.now().isoformat(timespec="seconds")
            conn.execute("""UPDATE wrong_questions SET error_causes=?,custom_tags=?,error_cause=?,error_cause_source=?,
                error_cause_confidence=?,error_cause_note=?,diagnosed_at=?,updated_at=?,revision=revision+1 WHERE wrong_id=?""",
                (json.dumps(command.error_causes), json.dumps(command.custom_tags, ensure_ascii=False), primary,
                 "user" if confirmed else "unconfirmed", int(confirmed), command.note, stamp if confirmed else None, stamp, wrong_id))
            after = self.state(self.detail(wrong_id))
            return self.event(conn, row=old, action="diagnosis", key=command.request_key, fingerprint=fingerprint,
                              before=self.state(old), after=after, result={"wrong_id": wrong_id, **after})

    def history(self, wrong_id: str, *, kind: str, limit: int = 30, offset: int = 0) -> dict:
        """Read a bounded, stable page using the original question identity."""
        if kind not in {"attempts", "events"} or type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValueError("历史分页参数无效")
        wrong = self.detail(wrong_id)
        table = "quiz_attempts" if kind == "attempts" else "review_events"
        where, params = ("artifact_id=? AND question_index=?", [wrong["artifact_id"], wrong["question_index"]]) if kind == "attempts" else ("wrong_id=?", [wrong_id])
        conn = self.storage._conn()
        total = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0]
        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?", [*params, limit, offset])]
        if kind == "events":
            for row in rows:
                for field in ("before_state", "after_state", "result"):
                    row[field] = json.loads(row[field])
        return {"items": rows, "total": total, "limit": limit, "offset": offset, "has_more": offset + len(rows) < total}

    def time_connection(self):
        """Share the engine's strict parsing with SQL counts and bounded selection."""
        conn = self.storage._conn()

        def strict_time(value):
            parsed = parse_time(value)
            return (parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() if parsed else None

        conn.create_function("filemate_review_time", 1, strict_time, deterministic=True)
        return conn

    def due_page(self, *, limit: int = 50) -> list[dict]:
        """Filter the full collection before taking bounded queue candidates."""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("候选数量无效")
        ids = self.time_connection().execute("""SELECT wrong_id FROM wrong_questions
            WHERE schedule_status='active' AND (scheduler_version=? OR mastered=0)
              AND filemate_review_time(next_review_at)<=?
            ORDER BY filemate_review_time(next_review_at),updated_at,wrong_id LIMIT ?""",
            (RULE_VERSION, self.now().timestamp(), limit)).fetchall()
        return [self.detail(row["wrong_id"]) for row in ids]

    def summary(self) -> dict:
        """Count the full collection independently of bounded queue candidates."""
        now = self.now()
        stamp = now.isoformat(timespec="seconds")
        day_start = now.astimezone(LOCAL_ZONE).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).timestamp()
        row = self.time_connection().execute("""SELECT COUNT(*) AS total,
            COALESCE(SUM(schedule_status='paused'),0) AS paused_count,
            COALESCE(SUM(scheduler_version!=? AND mastered=1),0) AS legacy_mastered_count,
            COALESCE(SUM(scheduler_version=? AND learning_status='criterion_met'),0) AS criterion_met_count,
            COALESCE(SUM(learning_status='pending_check'),0) AS pending_check_count,
            COALESCE(SUM(filemate_review_time(next_review_at) IS NULL),0) AS invalid_time_count,
            COALESCE(SUM(schedule_status='active' AND (scheduler_version=? OR mastered=0)
                AND filemate_review_time(next_review_at)<=?),0) AS due_count,
            COALESCE(SUM(schedule_status='active' AND (scheduler_version=? OR mastered=0)
                AND filemate_review_time(next_review_at)<?),0) AS overdue_count
            FROM wrong_questions""", (RULE_VERSION, RULE_VERSION, RULE_VERSION, now.timestamp(), RULE_VERSION, day_start)).fetchone()
        conn = self.time_connection()
        active = conn.execute("""SELECT COUNT(*) FROM wrong_questions WHERE scheduler_version=?
            AND schedule_status='active' AND learning_status IN ('new','needs_review','provisional')""", (RULE_VERSION,)).fetchone()[0]
        attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE rule_version=? AND purpose IN ('review','early_practice')", (RULE_VERSION,)).fetchone()[0]
        return {**dict(row), 'active_review_count': active, 'saved_review_attempt_count': attempts,
                "rule_version": RULE_VERSION, "as_of": stamp, "day_zone": "Asia/Shanghai"}
