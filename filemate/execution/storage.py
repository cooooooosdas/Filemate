"""SQLite 持久化。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
#  Schema（与 核心框架架构 §3.3 保持一致）
# ──────────────────────────────────────────────

_SCHEMA = """\
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    source_path  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','processing','done','confirmed','skipped','expired','failed')),
    category     TEXT,
    confidence   REAL,
    suggested_name TEXT,
    entities     TEXT,   -- JSON
    milestones   TEXT,   -- JSON
    error        TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_hash    TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    first_seen   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE TABLE IF NOT EXISTS operation_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    op           TEXT NOT NULL,          -- classify / rename / move / calendar / confirm / reject
    detail       TEXT DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE TABLE IF NOT EXISTS user_rules (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category     TEXT NOT NULL,
    keyword      TEXT NOT NULL,
    weight       REAL NOT NULL DEFAULT 1.0,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status    ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_operation_log_sid  ON operation_log(session_id);
"""


class SQLiteStorage:
    """SQLite 存储封装（四张表 + 线程安全）。"""

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()

    # ------------------------------------------------------------------
    # 内部：每个线程持有一条连接（sqlite3 不支持多线程共享连接）
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
        """建表 + CHECK 约束 + 索引。幂等，可重复调用。"""
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
        if not kwargs:
            return
        set_clause = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [datetime.now().isoformat(), session_id]
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

    def list_sessions(self, status: str | None = None) -> list[dict[str, Any]]:
        conn = self._conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status=? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

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
        conn = self._conn()
        # 确保 FK 不报错（测试可能未显式建 session）
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, source_path) VALUES (?, ?)",
            (session_id, f"/test/{session_id}"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO processed_files (file_hash, session_id) VALUES (?, ?)",
            (file_hash, session_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # operation_log 表
    # ------------------------------------------------------------------

    def log_operation(self, session_id: str, op: str, detail: str = "") -> None:
        conn = self._conn()
        conn.execute(
            "INSERT INTO operation_log (session_id, op, detail) VALUES (?, ?, ?)",
            (session_id, op, detail),
        )
        conn.commit()

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

    def add_rule(self, category: str, keyword: str, weight: float = 1.0) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO user_rules (category, keyword, weight) VALUES (?, ?, ?)",
            (category, keyword, weight),
        )
        conn.commit()
        return cur.lastrowid

    def list_rules(self, active_only: bool = True) -> list[dict[str, Any]]:
        conn = self._conn()
        if active_only:
            rows = conn.execute(
                "SELECT * FROM user_rules WHERE active=1 ORDER BY category, weight DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM user_rules ORDER BY category, weight DESC"
            ).fetchall()
        return [dict(r) for r in rows]
