"""SQLite 持久化。

Schema 与《项目总纲 v1.0》§3.6 对齐。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
#  Schema（与 项目总纲 §3.6 保持一致）
# ──────────────────────────────────────────────

_SCHEMA = """\
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    source_path      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK(status IN ('pending','processing','done','confirmed','skipped','expired','failed')),
    category         TEXT,
    confidence       REAL,
    suggested_name   TEXT,
    entities         TEXT,   -- JSON
    milestones       TEXT,   -- JSON
    error            TEXT,
    user_modified    INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_hash         TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id),
    first_seen_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    last_processed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    process_count     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS operation_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id),
    action            TEXT NOT NULL,
    detail            TEXT DEFAULT '',
    input_snapshot    TEXT,
    user_override     TEXT,
    latency_ms        INTEGER,
    model_used        TEXT,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS user_rules (
    rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type   TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    replacement TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status    ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created   ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_operation_log_sid  ON operation_log(session_id);
CREATE INDEX IF NOT EXISTS idx_operation_log_ts   ON operation_log(created_at);
"""


# update_session / update_rule 允许更新的列（防止拼写错误；SQL 注入已由参数化查询防御）
_ALLOWED_SESSION_COLS = {
    "status", "category", "confidence", "suggested_name",
    "entities", "milestones", "error", "user_modified",
}
_ALLOWED_RULE_COLS = {"pattern", "replacement", "priority", "enabled"}


class SQLiteStorage:
    """SQLite 存储封装（四张表 + 线程安全）。

    每张表提供最小完备的 CRUD 接口，调用方通过方法字段参数与表列交互。
    """

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()

    # ------------------------------------------------------------------
    # 内部：每个线程持有一条连接
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """建表 + 约束 + 索引。幂等，可重复调用。"""
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    # ------------------------------------------------------------------
    # sessions 表
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, source_path: str) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, source_path) VALUES (?, ?)",
            (session_id, str(source_path)),
        )
        conn.commit()

    def update_session(self, session_id: str, **kwargs: Any) -> None:
        """按字段名更新 session。自动刷新 updated_at。

        支持的字段：status, category, confidence, suggested_name,
        entities, milestones, error, user_modified。
        """
        if not kwargs:
            return
        invalid = set(kwargs) - _ALLOWED_SESSION_COLS
        if invalid:
            raise ValueError(
                f"无效字段: {sorted(invalid)}，允许: {sorted(_ALLOWED_SESSION_COLS)}"
            )
        set_clause = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [datetime.now().isoformat(timespec="seconds"), session_id]
        conn = self._conn()
        conn.execute(
            f"UPDATE sessions SET {set_clause}, updated_at=? WHERE session_id=?",
            values,
        )
        conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """删除 session 及其关联的操作日志与去重记录。返回是否实际删除了行。"""
        conn = self._conn()
        conn.execute("DELETE FROM operation_log WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM processed_files WHERE session_id=?", (session_id,))
        cur = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # processed_files 表
    # ------------------------------------------------------------------

    def is_duplicate(self, file_hash: str) -> bool:
        conn = self._conn()
        row = conn.execute(
            "SELECT 1 FROM processed_files WHERE file_hash=?", (file_hash,)
        ).fetchone()
        return row is not None

    def record_hash(self, file_hash: str, session_id: str) -> None:
        """记录文件哈希（新建或更新处理时间+计数）。

        调用方应在调用本方法前先通过 create_session() 创建 session。
        若 session 尚不存在，自动创建占位记录以保证 FK 不报错
        （source_path 为 __auto_created__ 前缀，方便排查调用顺序问题）。
        """
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, source_path) VALUES (?, ?)",
            (session_id, f"__auto_created__/{session_id}"),
        )
        conn.execute(
            """INSERT INTO processed_files (file_hash, session_id)
               VALUES (?, ?)
               ON CONFLICT(file_hash) DO UPDATE SET
                   last_processed_at = strftime('%Y-%m-%dT%H:%M:%S','now'),
                   process_count = process_count + 1""",
            (file_hash, session_id),
        )
        conn.commit()

    def get_file_info(self, file_hash: str) -> dict[str, Any] | None:
        """查询某个哈希的历史处理信息。"""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM processed_files WHERE file_hash=?", (file_hash,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # operation_log 表
    # ------------------------------------------------------------------

    def log_operation(
        self,
        session_id: str,
        action: str,
        detail: str = "",
        *,
        input_snapshot: str | None = None,
        user_override: str | None = None,
        latency_ms: int | None = None,
        model_used: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> int:
        """写入操作日志。返回自增 id。

        新增的 keyword-only 字段对齐项目总纲 §3.6，用于 Prompt 迭代分析。
        """
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO operation_log
               (session_id, action, detail, input_snapshot, user_override,
                latency_ms, model_used, prompt_tokens, completion_tokens)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, action, detail, input_snapshot, user_override,
                latency_ms, model_used, prompt_tokens, completion_tokens,
            ),
        )
        conn.commit()
        return cur.lastrowid

    def get_operations(self, session_id: str) -> list[dict[str, Any]]:
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM operation_log WHERE session_id=? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # user_rules 表
    # ------------------------------------------------------------------

    def add_rule(
        self,
        rule_type: str,
        pattern: str,
        replacement: str,
        priority: int = 0,
    ) -> int:
        """添加用户自定义规则。返回 rule_id。"""
        conn = self._conn()
        cur = conn.execute(
            """INSERT INTO user_rules (rule_type, pattern, replacement, priority)
               VALUES (?, ?, ?, ?)""",
            (rule_type, pattern, replacement, priority),
        )
        conn.commit()
        return cur.lastrowid

    def update_rule(self, rule_id: int, **kwargs: Any) -> bool:
        """更新规则字段（pattern, replacement, priority, enabled 等）。"""
        if not kwargs:
            return False
        invalid = set(kwargs) - _ALLOWED_RULE_COLS
        if invalid:
            raise ValueError(
                f"无效字段: {sorted(invalid)}，允许: {sorted(_ALLOWED_RULE_COLS)}"
            )
        set_clause = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [rule_id]
        conn = self._conn()
        cur = conn.execute(
            f"UPDATE user_rules SET {set_clause} WHERE rule_id=?",
            values,
        )
        conn.commit()
        return cur.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """删除规则。返回是否实际删除了行。"""
        conn = self._conn()
        cur = conn.execute("DELETE FROM user_rules WHERE rule_id=?", (rule_id,))
        conn.commit()
        return cur.rowcount > 0

    def list_rules(
        self, rule_type: str | None = None, enabled_only: bool = True
    ) -> list[dict[str, Any]]:
        conn = self._conn()
        clauses = []
        params: list[Any] = []
        if enabled_only:
            clauses.append("enabled=1")
        if rule_type:
            clauses.append("rule_type=?")
            params.append(rule_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM user_rules{where} ORDER BY priority DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
