"""复用现役面试与Artifact的原子报告和隐私操作。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from filemate.execution.storage import SQLiteStorage, _now_iso
from filemate.interview_review.reports import build_report, evidence_digest


class ReviewRepository:
    def __init__(self, storage: SQLiteStorage):
        self.storage = storage

    def _event(self, interview_id: str | None, action: str, detail: dict | None = None):
        self.storage._conn().execute(
            "INSERT INTO interview_review_events(interview_id,action,detail,created_at) "
            "VALUES (?,?,?,?)", (interview_id, action, json.dumps(detail or {}), _now_iso()),
        )

    def snapshot(self, interview_id: str) -> tuple[dict, int]:
        """捕获原始记录和修订号，使取消、清空、删除优先于迟到分析。"""
        with self.storage._write_lock:
            interview = self.storage.get_interview(interview_id)
            if interview is None:
                raise KeyError(interview_id)
            conn = self.storage._conn()
            conn.execute("INSERT OR IGNORE INTO interview_review_state(interview_id) VALUES (?)",
                         (interview_id,))
            revision = conn.execute(
                "SELECT revision FROM interview_review_state WHERE interview_id=?", (interview_id,),
            ).fetchone()[0]
            conn.commit()
            return interview, revision

    def _check_revision(self, interview_id: str, revision: int):
        state = self.storage._conn().execute(
            "SELECT * FROM interview_review_state WHERE interview_id=?", (interview_id,),
        ).fetchone()
        if not state or state["revision"] != revision:
            raise ValueError("记录已变化或分析已取消，请重新读取")
        return state

    def report(self, interview_id: str) -> dict[str, Any] | None:
        interview, _ = self.snapshot(interview_id)
        state = self.storage._conn().execute(
            "SELECT * FROM interview_review_state WHERE interview_id=?", (interview_id,),
        ).fetchone()
        if not state["artifact_id"] or state["input_digest"] != evidence_digest(interview):
            return None
        artifact = self.storage.get_artifact(state["artifact_id"])
        content = artifact.get("content") if artifact else None
        if (not isinstance(content, dict) or content.get("version") != "2.4"
                or not isinstance(content.get("turns"), list)):
            raise ValueError("报告数据异常，请重新生成；原回答仍保留")
        return content

    def generate(self, interview_id: str) -> dict[str, Any]:
        """生成本地报告，相同记录复用同一Artifact。"""
        interview, revision = self.snapshot(interview_id)
        if not interview["turns"]:
            raise ValueError("请先提交一条回答再生成报告")
        report, digest = build_report(interview), evidence_digest(interview)
        conn = self.storage._conn()
        with self.storage._write_lock:
            state = self._check_revision(interview_id, revision)
            if state["artifact_id"] and state["input_digest"] == digest:
                try:
                    previous = self.report(interview_id)
                    if previous:
                        return previous
                except ValueError:
                    pass
            artifact_id = state["artifact_id"] or uuid.uuid4().hex
            report["artifact_id"] = artifact_id
            report["generated_at"] = _now_iso()
            with conn:
                conn.execute(
                    "INSERT INTO artifacts(artifact_id,artifact_type,title,content,metadata) "
                    "VALUES (?, 'interview_report', ?, ?, ?) ON CONFLICT(artifact_id) DO UPDATE SET "
                    "content=excluded.content,title=excluded.title,updated_at=?",
                    (artifact_id, f"{interview['target_role']}面试复盘",
                     json.dumps(report, ensure_ascii=False), json.dumps({"interview_id": interview_id}),
                     _now_iso()),
                )
                conn.execute(
                    "UPDATE interview_review_state SET artifact_id=?, input_digest=? WHERE interview_id=?",
                    (artifact_id, digest, interview_id),
                )
                self._event(interview_id, "report_generated", {"answered": len(interview["turns"])})
        return report

    def apply_analysis(self, interview_id: str, turn_id: str, revision: int, evaluation: dict):
        """核对修订后写入模型证据，失败或取消不替换原结果。"""
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            self._check_revision(interview_id, revision)
            row = conn.execute(
                "SELECT content_analysis FROM interview_turns WHERE interview_id=? AND turn_id=?",
                (interview_id, turn_id),
            ).fetchone()
            if not row:
                raise KeyError(turn_id)
            conn.execute(
                "UPDATE interview_turns SET score=?, dimensions=?, feedback=?, scoring_mode='llm', "
                "scoring_version='v2.4', content_analysis=? WHERE turn_id=?",
                (evaluation["score"], json.dumps(evaluation["dimensions"], ensure_ascii=False),
                 evaluation["feedback"], json.dumps(evaluation["content_analysis"], ensure_ascii=False),
                 turn_id),
            )
            conn.execute("UPDATE interview_review_state SET revision=revision+1, input_digest='' "
                         "WHERE interview_id=?", (interview_id,))
            conn.execute("UPDATE interview_sessions SET updated_at=?, overall_score="
                         "(SELECT AVG(score) FROM interview_turns WHERE interview_id=? AND scoring_mode='llm') "
                         "WHERE interview_id=?", (_now_iso(), interview_id, interview_id))
            self._event(interview_id, "content_analyzed", {"turn_id": turn_id})
        return self.storage.get_interview(interview_id)

    def cancel(self, interview_id: str):
        """使正在进行的分析失效，不删除既有结果。"""
        self.snapshot(interview_id)
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            conn.execute("UPDATE interview_review_state SET revision=revision+1 WHERE interview_id=?",
                         (interview_id,))
            self._event(interview_id, "analysis_cancelled")
        return {"cancelled": True}

    def clear(self, interview_id: str):
        """经用户确认清空派生分析，保留原回答和语音节奏。"""
        self.snapshot(interview_id)
        conn = self.storage._conn()
        with self.storage._write_lock, conn:
            state = conn.execute("SELECT * FROM interview_review_state WHERE interview_id=?",
                                 (interview_id,)).fetchone()
            changed = conn.execute(
                "SELECT COUNT(*) FROM interview_turns WHERE interview_id=? AND "
                "(visual_metrics!='{}' OR content_analysis!='{}' OR scoring_mode='llm')", (interview_id,),
            ).fetchone()[0]
            if state["artifact_id"]:
                conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (state["artifact_id"],))
            conn.execute(
                "UPDATE interview_turns SET visual_metrics='{}',content_analysis='{}',score=0, "
                "scoring_mode='local_fallback',scoring_version='v2.4-cleared', dimensions='{}', "
                "feedback='分析已清空，原回答与语音节奏保留。' WHERE interview_id=?", (interview_id,),
            )
            conn.execute("UPDATE interview_review_state SET revision=revision+1, input_digest='' "
                         "WHERE interview_id=?", (interview_id,))
            conn.execute("UPDATE interview_sessions SET overall_score=0, expression_review='{}', updated_at=? "
                         "WHERE interview_id=?", (_now_iso(), interview_id))
            if changed or state["artifact_id"]:
                self._event(interview_id, "analysis_cleared")
        return self.storage.get_interview(interview_id)

    def delete_preview(self, interview_id: str):
        """列出删除影响并提供绑定当前修订的确认摘要。"""
        interview, revision = self.snapshot(interview_id)
        state = self.storage._conn().execute(
            "SELECT artifact_id FROM interview_review_state WHERE interview_id=?", (interview_id,),
        ).fetchone()
        token = hashlib.sha256((evidence_digest(interview) + str(revision)).encode()).hexdigest()
        return {"interview_id": interview_id, "answers": len(interview["turns"]),
                "reports": int(bool(state["artifact_id"])), "confirmation_token": token,
                "scope": "本场回答、节奏、观察、报告与关联Agent记录；不删除原资料和其他练习。"}

    def delete(self, interview_id: str, token: str):
        """只删除用户预览确认的本场数据并清除关联私有记忆。"""
        conn = self.storage._conn()
        with self.storage._write_lock:
            if self.storage.get_interview(interview_id) is None:
                return {"deleted": True}
            preview = self.delete_preview(interview_id)
            if preview["confirmation_token"] != token:
                raise ValueError("记录已更新，请重新预览删除影响")
            session = self.storage.get_interview(interview_id)
            state = conn.execute("SELECT artifact_id FROM interview_review_state WHERE interview_id=?",
                                 (interview_id,)).fetchone()
            run_id = session.get("agent_run_id")
            with conn:
                if state["artifact_id"]:
                    conn.execute("DELETE FROM artifacts WHERE artifact_id=?", (state["artifact_id"],))
                conn.execute("DELETE FROM agent_memories WHERE scope_id=?", (interview_id,))
                conn.execute("DELETE FROM interview_review_events WHERE interview_id=?", (interview_id,))
                conn.execute("DELETE FROM interview_sessions WHERE interview_id=?", (interview_id,))
                if run_id:
                    conn.execute("DELETE FROM agent_runs WHERE run_id=? AND NOT EXISTS "
                                 "(SELECT 1 FROM interview_sessions WHERE agent_run_id=?)", (run_id, run_id))
                self._event(None, "interview_deleted", {"answers": preview["answers"]})
            return {"deleted": True}

    def events(self, interview_id: str):
        self.snapshot(interview_id)
        return [dict(row) for row in self.storage._conn().execute(
            "SELECT event_id,action,detail,created_at FROM interview_review_events "
            "WHERE interview_id=? ORDER BY event_id DESC LIMIT 100", (interview_id,),
        ).fetchall()]

    def log_export(self, interview_id: str, format: str):
        with self.storage._write_lock, self.storage._conn():
            self._event(interview_id, "report_exported", {"format": format})
