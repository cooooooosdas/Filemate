"""提交产物、撤销状态和编程证据的原子持久化。"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from filemate.execution.storage import SQLiteStorage, _now_iso

from .problems import get_problem


def _problem_available(record: dict[str, Any]) -> bool:
    """无法对应固定题目版本的记录不得执行或进入统计。"""
    try:
        return record["problem_version"] == get_problem(record["problem_id"])["version"]
    except KeyError:
        return False


class CodingRepository:
    """复用现役 SQLite 与 Artifact，错题由有效提交投影生成。"""

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def _event(self, identifier: str | None, action: str, details: dict | None = None) -> None:
        self.storage._conn().execute(
            "INSERT INTO coding_events(submission_id,action,details,created_at) VALUES(?,?,?,?)",
            (identifier, action, self.storage._dump_json(details or {}), _now_iso()),
        )

    def get(self, identifier: str) -> dict[str, Any]:
        """读取提交并检查存储结构，损坏数据保留原样。"""
        row = self.storage._conn().execute(
            """SELECT c.*,a.content FROM coding_submissions c JOIN artifacts a
               ON a.artifact_id=c.artifact_id WHERE c.submission_id=?""", (identifier,),
        ).fetchone()
        if row is None:
            raise KeyError(identifier)
        result = dict(row)
        try:
            payload = json.loads(result.pop("content"))
            if not _problem_available(result):
                raise ValueError("unavailable problem revision")
            if not isinstance(payload, dict) or not isinstance(payload.get("code"), str):
                raise TypeError("invalid payload")
            if not isinstance(payload.get("result"), dict):
                raise TypeError("invalid result")
            result.update({key: payload.get(key) for key in
                           ("code", "language", "result", "review", "notes", "code_sha256", "local_feedback")})
            result["data_error"] = False
        except (ValueError, TypeError):
            result.update(code="", result={}, review=None, notes="", data_error=True)
        return result

    def _finish_damaged(self, identifier: str, status: str, event: str) -> dict[str, Any]:
        """仅更新损坏提交的索引状态，原产物字节保持不变。"""
        conn = self.storage._conn()
        try:
            conn.execute("UPDATE coding_submissions SET status=?,updated_at=? WHERE submission_id=?",
                         (status, _now_iso(), identifier))
            self._event(identifier, event)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return self.get(identifier)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        """按时间倒序读取有界提交列表。"""
        rows = self.storage._conn().execute(
            "SELECT submission_id FROM coding_submissions ORDER BY created_at DESC,rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self.get(row[0]) for row in rows]

    def create(self, problem: dict[str, Any], code: str, request_key: str) -> dict[str, Any]:
        """相同请求键只创建一次，键复用不同内容时报冲突。"""
        with self.storage._write_lock:
            conn = self.storage._conn()
            old = conn.execute("SELECT submission_id FROM coding_submissions WHERE request_key=?",
                               (request_key,)).fetchone()
            if old:
                result = self.get(old[0])
                if result["problem_id"] != problem["id"] or result["code"] != code:
                    raise ValueError("提交键已用于其他代码，请创建新的提交")
                return result
            identifier, artifact = uuid.uuid4().hex, uuid.uuid4().hex
            now = _now_iso()
            payload = {"code": code, "language": "cpp17", "result": {}, "review": None,
                       "notes": "", "code_sha256": hashlib.sha256(code.encode()).hexdigest()}
            try:
                conn.execute(
                    """INSERT INTO artifacts(artifact_id,workspace_id,artifact_type,title,content,metadata)
                       VALUES(?,'local','coding_submission',?,?,?)""",
                    (artifact, problem["title"], self.storage._dump_json(payload),
                     self.storage._dump_json({"problem_id": problem["id"], "version": problem["version"]})),
                )
                conn.execute(
                    """INSERT INTO coding_submissions
                       (submission_id,request_key,problem_id,problem_version,artifact_id,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,'queued',?,?)""",
                    (identifier, request_key, problem["id"], problem["version"], artifact, now, now),
                )
                self._event(identifier, "created")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return self.get(identifier)

    def update(self, identifier: str, *, status: str | None = None,
               payload: dict[str, Any] | None = None, event: str | None = None) -> dict[str, Any]:
        """在事务中写入执行证据，取消状态不可被迟到结果覆盖。"""
        with self.storage._write_lock:
            old = self.get(identifier)
            if old["data_error"]:
                raise ValueError("提交数据损坏，请新建提交，原记录已保留")
            if old["status"] == "cancelled" and status != "cancelled" and (
                status is not None or (payload and "result" in payload)
            ):
                return old
            data = {key: old[key] for key in
                    ("code", "language", "result", "review", "notes", "code_sha256", "local_feedback")}
            data.update(payload or {})
            conn = self.storage._conn()
            try:
                conn.execute("UPDATE artifacts SET content=?,updated_at=? WHERE artifact_id=?",
                             (self.storage._dump_json(data), _now_iso(), old["artifact_id"]))
                conn.execute("UPDATE coding_submissions SET status=?,updated_at=? WHERE submission_id=?",
                             (status or old["status"], _now_iso(), identifier))
                if event:
                    self._event(identifier, event)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return self.get(identifier)

    def start(self, identifier: str) -> tuple[dict[str, Any], bool]:
        """只允许一个执行者认领 queued 提交。"""
        with self.storage._write_lock:
            row = self.get(identifier)
            if row["data_error"] or not row["active"]:
                raise ValueError("提交已撤销或数据损坏，无法执行")
            if row["status"] != "queued":
                return row, False
            return self.update(identifier, status="running", event="started"), True

    def transition(self, identifier: str, action: str) -> dict[str, Any]:
        """幂等取消、撤销和恢复；运行中的证据不能被撤销。"""
        with self.storage._write_lock:
            row = self.get(identifier)
            if action == "cancel":
                if row["status"] in {"queued", "running"}:
                    if row["data_error"]:
                        return self._finish_damaged(identifier, "cancelled", "cancelled")
                    return self.update(identifier, status="cancelled", event="cancelled")
                return row
            if row["status"] in {"queued", "running"}:
                raise ValueError("请先取消评测，再撤销这次提交")
            if action not in {"undo", "restore"}:
                raise ValueError("不支持的操作")
            if action == "restore" and row["data_error"]:
                raise ValueError("提交数据损坏，暂不能恢复，原记录已保留")
            active = int(action == "restore")
            if row["active"] == active:
                return row
            conn = self.storage._conn()
            try:
                conn.execute("UPDATE coding_submissions SET active=?,updated_at=? WHERE submission_id=?",
                             (active, _now_iso(), identifier))
                self._event(identifier, action)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            return self.get(identifier)

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        """读取不包含源代码、模型凭据和环境变量的操作日志。"""
        return [dict(row) for row in self.storage._conn().execute(
            "SELECT * FROM coding_events ORDER BY event_id DESC LIMIT ?", (limit,),
        ).fetchall()]

    def evidence(self) -> list[dict[str, Any]]:
        """流式读取全部有效提交的最小统计字段，不把所有源代码堆入内存。"""
        records = []
        rows = self.storage._conn().execute(
            """SELECT c.*,a.content FROM coding_submissions c JOIN artifacts a ON a.artifact_id=c.artifact_id
               WHERE c.status='completed' AND c.active=1 ORDER BY c.created_at DESC,c.rowid DESC""",
        )
        for row in rows:
            item = dict(row)
            if not _problem_available(item):
                continue
            try:
                payload = json.loads(item.pop("content"))
                if (not isinstance(payload, dict) or not isinstance(payload.get("code"), str)
                        or not isinstance(payload.get("result"), dict)):
                    continue
                result = payload["result"]
                item["result"] = {"verdict": result.get("verdict"), "score": result.get("score", 0)}
                review = payload.get("review")
                item["review"] = {"created_at": review.get("created_at")} if isinstance(review, dict) else None
                item["data_error"] = False
                records.append(item)
            except (ValueError, TypeError):
                continue
        return records

    def interrupt_orphans(self, live: set[str]) -> None:
        """将本服务未持有的运行记录标记为中断，保留代码与已有证据。"""
        with self.storage._write_lock:
            rows = self.storage._conn().execute(
                "SELECT submission_id FROM coding_submissions WHERE status='running'",
            ).fetchall()
            for row in rows:
                if row[0] not in live:
                    if self.get(row[0])["data_error"]:
                        self._finish_damaged(row[0], "failed", "interrupted")
                        continue
                    self.update(row[0], status="failed", payload={"result": {
                        "verdict": "SYSTEM_ERROR", "error": "服务已中断，请保留代码新建提交重试",
                    }}, event="interrupted")
