"""SQLite 持久化。

Schema 与《项目总纲 v1.0》§3.6 对齐。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────
#  Schema（与 项目总纲 §3.6 保持一致）
# ──────────────────────────────────────────────

_SCHEMA = """\
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

_KNOWLEDGE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

INSERT OR IGNORE INTO workspaces (workspace_id, name) VALUES ('local', '本地工作区');

CREATE TABLE IF NOT EXISTS sources (
    source_id     TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    media_type    TEXT NOT NULL DEFAULT '',
    file_hash     TEXT,
    raw_text      TEXT NOT NULL DEFAULT '',
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id   TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    source_id     TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    title         TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL,
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS document_contexts (
    ctx_id        TEXT PRIMARY KEY,
    workspace_id  TEXT NOT NULL DEFAULT 'local'
                  REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    source_id     TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    artifact_id   TEXT REFERENCES artifacts(artifact_id) ON DELETE SET NULL,
    context_text  TEXT NOT NULL,
    chat_history  TEXT NOT NULL DEFAULT '[]',
    metadata      TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    expires_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_workspace ON sources(workspace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(workspace_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(workspace_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_contexts_source ON document_contexts(source_id, created_at);
"""

_EXECUTION_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_records (
    execution_id   TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK(status IN ('pending','applied','undone','failed')),
    source_path    TEXT NOT NULL,
    dest_path      TEXT NOT NULL,
    ics_path       TEXT,
    input_snapshot TEXT NOT NULL DEFAULT '{}',
    output_snapshot TEXT NOT NULL DEFAULT '{}',
    error          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    applied_at     TEXT,
    undone_at      TEXT,
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_execution_session
    ON execution_records(session_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_open
    ON execution_records(session_id)
    WHERE status IN ('pending','applied');
"""

_LEARNING_SCHEMA = """\
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    page_number  INTEGER,
    content      TEXT NOT NULL,
    metadata     TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(source_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    attempt_id      TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    question_index  INTEGER NOT NULL,
    user_answer     TEXT NOT NULL,
    is_correct      INTEGER NOT NULL,
    score           REAL NOT NULL,
    feedback        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS wrong_questions (
    wrong_id         TEXT PRIMARY KEY,
    artifact_id      TEXT NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id        TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    question_index   INTEGER NOT NULL,
    question         TEXT NOT NULL,
    latest_answer    TEXT NOT NULL DEFAULT '',
    error_count      INTEGER NOT NULL DEFAULT 1,
    correct_streak   INTEGER NOT NULL DEFAULT 0,
    mastered         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(artifact_id, question_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON document_chunks(source_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_attempts_artifact ON quiz_attempts(artifact_id, created_at);
CREATE INDEX IF NOT EXISTS idx_wrong_mastered ON wrong_questions(mastered, updated_at);
"""

_INTERVIEW_SCHEMA = """\
CREATE TABLE IF NOT EXISTS interview_sessions (
    interview_id  TEXT PRIMARY KEY,
    target_role   TEXT NOT NULL,
    scenario      TEXT NOT NULL,
    difficulty    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    questions     TEXT NOT NULL,
    current_index INTEGER NOT NULL DEFAULT 0,
    overall_score REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS interview_turns (
    turn_id        TEXT PRIMARY KEY,
    interview_id   TEXT NOT NULL REFERENCES interview_sessions(interview_id) ON DELETE CASCADE,
    question_index INTEGER NOT NULL,
    question       TEXT NOT NULL,
    answer         TEXT NOT NULL,
    score          REAL NOT NULL,
    dimensions     TEXT NOT NULL DEFAULT '{}',
    feedback       TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(interview_id, question_index)
);

CREATE INDEX IF NOT EXISTS idx_interview_turns ON interview_turns(interview_id, question_index);
"""

_STUDY_PLAN_SCHEMA = """\
CREATE TABLE IF NOT EXISTS study_plans (
    plan_id         TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL UNIQUE REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    source_id       TEXT REFERENCES sources(source_id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    exam_date       TEXT NOT NULL,
    daily_minutes   INTEGER NOT NULL,
    goal            TEXT NOT NULL DEFAULT '',
    plan_data       TEXT NOT NULL,
    completed_days  TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active','completed','archived')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS idx_study_plans_status
    ON study_plans(status, updated_at);
"""

_PRODUCT_FEEDBACK_SCHEMA = """\
CREATE TABLE IF NOT EXISTS product_feedback (
    feedback_id  TEXT PRIMARY KEY,
    area         TEXT NOT NULL
                 CHECK(area IN ('retrieval','tutor','interview','study_plan')),
    target_hash  TEXT NOT NULL,
    rating       INTEGER NOT NULL CHECK(rating IN (-1, 1)),
    context      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    UNIQUE(area, target_hash)
);

CREATE INDEX IF NOT EXISTS idx_product_feedback_area
    ON product_feedback(area, updated_at);
"""

_SPACED_REPETITION_SCHEMA = """\
ALTER TABLE wrong_questions
    ADD COLUMN next_review_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00';
ALTER TABLE wrong_questions
    ADD COLUMN interval_days INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wrong_questions
    ADD COLUMN ease_factor REAL NOT NULL DEFAULT 2.5;
ALTER TABLE wrong_questions
    ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_wrong_next_review
    ON wrong_questions(mastered, next_review_at);
"""

_MIGRATIONS = (
    (1, "initial_execution_schema", _SCHEMA),
    (2, "knowledge_persistence", _KNOWLEDGE_SCHEMA),
    (3, "reversible_execution", _EXECUTION_SCHEMA),
    (4, "retrieval_and_wrongbook", _LEARNING_SCHEMA),
    (5, "mock_interview", _INTERVIEW_SCHEMA),
    (6, "persistent_study_plans", _STUDY_PLAN_SCHEMA),
    (7, "anonymous_product_feedback", _PRODUCT_FEEDBACK_SCHEMA),
    (8, "spaced_repetition", _SPACED_REPETITION_SCHEMA),
)


# update_session / update_rule 允许更新的列（防止拼写错误；SQL 注入已由参数化查询防御）
_ALLOWED_SESSION_COLS = {
    "status", "category", "confidence", "suggested_name",
    "entities", "milestones", "error", "user_modified",
}
_ALLOWED_RULE_COLS = {"pattern", "replacement", "priority", "enabled"}
_ALLOWED_EXECUTION_COLS = {
    "status",
    "dest_path",
    "ics_path",
    "output_snapshot",
    "error",
    "applied_at",
    "undone_at",
}


def _now_iso() -> str:
    """生成带时区的 UTC 时间。"""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


class SQLiteStorage:
    """SQLite 存储封装（版本迁移 + 线程安全）。

    每张表提供最小完备的 CRUD 接口，调用方通过方法字段参数与表列交互。
    """

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._connections: set[sqlite3.Connection] = set()

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
                timeout=10.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
            with self._write_lock:
                self._connections.add(conn)
        return conn

    def close(self) -> None:
        """关闭该存储实例创建的全部线程连接。"""
        with self._write_lock:
            for conn in tuple(self._connections):
                conn.close()
            self._connections.clear()
            self._local.conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """按版本执行数据库迁移。幂等，可重复调用。"""
        conn = self._conn()
        with self._write_lock:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       version    INTEGER PRIMARY KEY,
                       name       TEXT NOT NULL,
                       applied_at TEXT NOT NULL DEFAULT
                                  (strftime('%Y-%m-%dT%H:%M:%S','now'))
                   )"""
            )
            conn.commit()
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations")
            }
            for version, name, script in _MIGRATIONS:
                if version in applied:
                    continue
                safe_name = name.replace("'", "''")
                try:
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        f"{script}\n"
                        "INSERT INTO schema_migrations (version, name) "
                        f"VALUES ({version}, '{safe_name}');\n"
                        "COMMIT;"
                    )
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise

    def get_schema_version(self) -> int:
        """返回已应用的最高数据库版本。"""
        row = self._conn().execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        return int(row["version"] if row else 0)

    def list_migrations(self) -> list[dict[str, Any]]:
        """按版本列出迁移记录。"""
        rows = self._conn().execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # sessions 表
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, source_path: str) -> None:
        with self._write_lock:
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
        values = list(kwargs.values()) + [_now_iso(), session_id]
        with self._write_lock:
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
        with self._write_lock:
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
        with self._write_lock:
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
        with self._write_lock:
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
        with self._write_lock:
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
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                f"UPDATE user_rules SET {set_clause} WHERE rule_id=?",
                values,
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_rule(self, rule_id: int) -> bool:
        """删除规则。返回是否实际删除了行。"""
        with self._write_lock:
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

    # ------------------------------------------------------------------
    # workspaces / sources / artifacts / document_contexts
    # ------------------------------------------------------------------

    @staticmethod
    def _dump_json(value: Any) -> str:
        """稳定序列化 JSON 数据。"""
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode_row(
        row: sqlite3.Row | None,
        json_fields: tuple[str, ...],
    ) -> dict[str, Any] | None:
        """把 SQLite 行转换为字典并还原 JSON 字段。"""
        if row is None:
            return None
        result = dict(row)
        for field in json_fields:
            raw = result.get(field)
            if raw is None:
                continue
            try:
                result[field] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                result[field] = {} if field == "metadata" else []
        return result

    def create_workspace(self, workspace_id: str, name: str) -> None:
        """创建或更新工作区。"""
        if not workspace_id.strip() or not name.strip():
            raise ValueError("workspace_id 和 name 不能为空")
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO workspaces (workspace_id, name)
                   VALUES (?, ?)
                   ON CONFLICT(workspace_id) DO UPDATE SET
                       name=excluded.name, updated_at=?""",
                (workspace_id, name, now),
            )
            self._conn().commit()

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """读取单个工作区。"""
        row = self._conn().execute(
            "SELECT * FROM workspaces WHERE workspace_id=?",
            (workspace_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        """列出工作区。"""
        rows = self._conn().execute(
            "SELECT * FROM workspaces ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def save_source(
        self,
        *,
        original_name: str,
        source_path: str,
        raw_text: str = "",
        workspace_id: str = "local",
        media_type: str = "",
        file_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> str:
        """新增或更新统一资料源，并返回 source_id。"""
        if not original_name.strip() or not source_path.strip():
            raise ValueError("original_name 和 source_path 不能为空")
        if self.get_workspace(workspace_id) is None:
            raise ValueError(f"工作区不存在: {workspace_id}")

        if source_id is None:
            if file_hash:
                source_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"filemate:{workspace_id}:{file_hash}",
                ).hex
            else:
                source_id = uuid.uuid4().hex

        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO sources
                   (source_id, workspace_id, original_name, source_path,
                    media_type, file_hash, raw_text, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                       original_name=excluded.original_name,
                       source_path=excluded.source_path,
                       media_type=excluded.media_type,
                       file_hash=excluded.file_hash,
                       raw_text=excluded.raw_text,
                       metadata=excluded.metadata,
                       updated_at=?""",
                (
                    source_id,
                    workspace_id,
                    original_name,
                    source_path,
                    media_type,
                    file_hash,
                    raw_text,
                    self._dump_json(metadata or {}),
                    now,
                ),
            )
            self._conn().commit()
        return source_id

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        """按 ID 读取资料源。"""
        row = self._conn().execute(
            "SELECT * FROM sources WHERE source_id=?",
            (source_id,),
        ).fetchone()
        return self._decode_row(row, ("metadata",))

    def list_sources(
        self,
        workspace_id: str = "local",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按工作区列出最近资料源。"""
        rows = self._conn().execute(
            """SELECT * FROM sources WHERE workspace_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (workspace_id, limit),
        ).fetchall()
        return [self._decode_row(row, ("metadata",)) for row in rows]

    def save_artifact(
        self,
        *,
        artifact_type: str,
        content: Any,
        source_id: str | None = None,
        workspace_id: str = "local",
        title: str = "",
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> str:
        """保存由资料派生的 AI 产物。"""
        if not artifact_type.strip():
            raise ValueError("artifact_type 不能为空")
        artifact_id = artifact_id or uuid.uuid4().hex
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO artifacts
                   (artifact_id, workspace_id, source_id, artifact_type,
                    title, content, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET
                       artifact_type=excluded.artifact_type,
                       title=excluded.title,
                       content=excluded.content,
                       metadata=excluded.metadata,
                       updated_at=?""",
                (
                    artifact_id,
                    workspace_id,
                    source_id,
                    artifact_type,
                    title,
                    self._dump_json(content),
                    self._dump_json(metadata or {}),
                    now,
                ),
            )
            self._conn().commit()
        return artifact_id

    def get_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        """读取单个 AI 产物。"""
        row = self._conn().execute(
            "SELECT * FROM artifacts WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        return self._decode_row(row, ("content", "metadata"))

    def update_artifact(
        self,
        artifact_id: str,
        *,
        title: str,
        content: Any,
    ) -> dict[str, Any] | None:
        """更新用户可编辑的学习产物标题与内容。"""
        with self._write_lock:
            cursor = self._conn().execute(
                """UPDATE artifacts SET title=?, content=?, updated_at=?
                   WHERE artifact_id=?""",
                (title.strip(), self._dump_json(content), _now_iso(), artifact_id),
            )
            self._conn().commit()
        return self.get_artifact(artifact_id) if cursor.rowcount else None

    def list_artifacts(
        self,
        *,
        workspace_id: str = "local",
        source_id: str | None = None,
        artifact_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """按资料源或类型筛选 AI 产物。"""
        clauses = ["workspace_id=?"]
        params: list[Any] = [workspace_id]
        if source_id:
            clauses.append("source_id=?")
            params.append(source_id)
        if artifact_type:
            clauses.append("artifact_type=?")
            params.append(artifact_type)
        params.append(limit)
        rows = self._conn().execute(
            f"""SELECT * FROM artifacts WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC LIMIT ?""",
            params,
        ).fetchall()
        return [
            self._decode_row(row, ("content", "metadata"))
            for row in rows
        ]

    def save_document_context(
        self,
        *,
        ctx_id: str,
        context_text: str,
        source_id: str | None = None,
        artifact_id: str | None = None,
        workspace_id: str = "local",
        chat_history: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> None:
        """新增或更新可恢复的文档问答上下文。"""
        if not ctx_id.strip() or not context_text.strip():
            raise ValueError("ctx_id 和 context_text 不能为空")
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO document_contexts
                   (ctx_id, workspace_id, source_id, artifact_id, context_text,
                    chat_history, metadata, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ctx_id) DO UPDATE SET
                       artifact_id=excluded.artifact_id,
                       context_text=excluded.context_text,
                       chat_history=excluded.chat_history,
                       metadata=excluded.metadata,
                       expires_at=excluded.expires_at,
                       updated_at=?""",
                (
                    ctx_id,
                    workspace_id,
                    source_id,
                    artifact_id,
                    context_text,
                    self._dump_json(chat_history or []),
                    self._dump_json(metadata or {}),
                    expires_at,
                    now,
                ),
            )
            self._conn().commit()

    def get_document_context(self, ctx_id: str) -> dict[str, Any] | None:
        """读取文档问答上下文。"""
        row = self._conn().execute(
            "SELECT * FROM document_contexts WHERE ctx_id=?",
            (ctx_id,),
        ).fetchone()
        return self._decode_row(row, ("chat_history", "metadata"))

    def append_context_messages(
        self,
        ctx_id: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """原子追加上下文对话消息并返回完整历史。"""
        if not messages:
            context = self.get_document_context(ctx_id)
            return context["chat_history"] if context else []
        with self._write_lock:
            context = self.get_document_context(ctx_id)
            if context is None:
                raise ValueError(f"文档上下文不存在: {ctx_id}")
            history = list(context.get("chat_history") or [])
            history.extend(messages)
            self._conn().execute(
                """UPDATE document_contexts
                   SET chat_history=?, updated_at=? WHERE ctx_id=?""",
                (
                    self._dump_json(history),
                    _now_iso(),
                    ctx_id,
                ),
            )
            self._conn().commit()
            return history

    def delete_document_context(self, ctx_id: str) -> bool:
        """删除文档上下文。"""
        with self._write_lock:
            cur = self._conn().execute(
                "DELETE FROM document_contexts WHERE ctx_id=?",
                (ctx_id,),
            )
            self._conn().commit()
            return cur.rowcount > 0

    def replace_source_chunks(
        self,
        source_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        """原子替换资料源的检索分块。"""
        if self.get_source(source_id) is None:
            raise ValueError(f"资料源不存在: {source_id}")
        with self._write_lock:
            connection = self._conn()
            connection.execute("DELETE FROM document_chunks WHERE source_id=?", (source_id,))
            connection.executemany(
                """INSERT INTO document_chunks
                   (chunk_id, source_id, chunk_index, page_number, content, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"filemate:{source_id}:chunk:{chunk['chunk_index']}",
                        ).hex,
                        source_id,
                        int(chunk["chunk_index"]),
                        chunk.get("page_number"),
                        str(chunk["content"]),
                        self._dump_json(chunk.get("metadata") or {}),
                    )
                    for chunk in chunks
                ],
            )
            connection.commit()

    def list_source_chunks(self, source_id: str) -> list[dict[str, Any]]:
        """按原始顺序读取资料分块。"""
        rows = self._conn().execute(
            "SELECT * FROM document_chunks WHERE source_id=? ORDER BY chunk_index",
            (source_id,),
        ).fetchall()
        return [self._decode_row(row, ("metadata",)) for row in rows]

    def record_quiz_attempt(
        self,
        *,
        artifact_id: str,
        question_index: int,
        user_answer: str,
        is_correct: bool,
        score: float,
        feedback: str,
    ) -> dict[str, Any]:
        """记录一次作答，并同步更新错题掌握状态。"""
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"AI 产物不存在: {artifact_id}")
        questions = artifact.get("content")
        if not isinstance(questions, list) or not 0 <= question_index < len(questions):
            raise ValueError("题目序号无效")
        question = questions[question_index]
        attempt_id = uuid.uuid4().hex
        now = _now_iso()
        existing_wrong = self._conn().execute(
            """SELECT correct_streak, interval_days, ease_factor, review_count
               FROM wrong_questions WHERE artifact_id=? AND question_index=?""",
            (artifact_id, question_index),
        ).fetchone()
        with self._write_lock:
            connection = self._conn()
            connection.execute(
                """INSERT INTO quiz_attempts
                   (attempt_id, artifact_id, source_id, question_index,
                    user_answer, is_correct, score, feedback)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt_id,
                    artifact_id,
                    artifact.get("source_id"),
                    question_index,
                    user_answer,
                    int(is_correct),
                    score,
                    feedback,
                ),
            )
            if is_correct:
                current_interval = int(existing_wrong["interval_days"]) if existing_wrong else 0
                current_ease = float(existing_wrong["ease_factor"]) if existing_wrong else 2.5
                quality = 5 if score >= 0.95 else 4 if score >= 0.85 else 3
                ease = max(
                    1.3,
                    current_ease
                    + 0.1
                    - (5 - quality) * (0.08 + (5 - quality) * 0.02),
                )
                interval_days = (
                    1
                    if current_interval <= 0
                    else max(3, round(current_interval * ease))
                )
                next_review_at = (
                    datetime.now(tz=timezone.utc) + timedelta(days=interval_days)
                ).isoformat(timespec="seconds")
                connection.execute(
                    """UPDATE wrong_questions SET
                       latest_answer=?, correct_streak=correct_streak + 1,
                       mastered=CASE WHEN correct_streak + 1 >= 2 THEN 1 ELSE 0 END,
                       interval_days=?, ease_factor=?,
                       review_count=review_count + 1, next_review_at=?,
                       updated_at=?
                       WHERE artifact_id=? AND question_index=?""",
                    (
                        user_answer,
                        interval_days,
                        round(ease, 3),
                        next_review_at,
                        now,
                        artifact_id,
                        question_index,
                    ),
                )
            else:
                wrong_id = uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"filemate:{artifact_id}:wrong:{question_index}",
                ).hex
                connection.execute(
                    """INSERT INTO wrong_questions
                       (wrong_id, artifact_id, source_id, question_index,
                        question, latest_answer, next_review_at,
                        interval_days, ease_factor, review_count)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0, 2.3, 1)
                       ON CONFLICT(artifact_id, question_index) DO UPDATE SET
                           latest_answer=excluded.latest_answer,
                           error_count=wrong_questions.error_count + 1,
                           correct_streak=0, mastered=0, interval_days=0,
                           ease_factor=MAX(1.3, wrong_questions.ease_factor - 0.2),
                           review_count=wrong_questions.review_count + 1,
                           next_review_at=excluded.next_review_at, updated_at=?""",
                    (
                        wrong_id,
                        artifact_id,
                        artifact.get("source_id"),
                        question_index,
                        self._dump_json(question),
                        user_answer,
                        now,
                        now,
                    ),
                )
            connection.commit()
        return {
            "attempt_id": attempt_id,
            "is_correct": is_correct,
            "score": score,
            "feedback": feedback,
            "reference_answer": question.get("answer", "") if isinstance(question, dict) else "",
        }

    def list_wrong_questions(
        self,
        *,
        mastered: bool | None = None,
        due_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """列出待复习或已掌握错题。"""
        query = "SELECT * FROM wrong_questions"
        params: list[Any] = []
        if mastered is not None:
            query += " WHERE mastered=?"
            params.append(int(mastered))
        query += " ORDER BY next_review_at, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        rows = self._conn().execute(query, params).fetchall()
        decoded = [self._decode_row(row, ("question",)) for row in rows]
        if not due_only:
            return decoded
        now = datetime.now(tz=timezone.utc)
        due: list[dict[str, Any]] = []
        for item in decoded:
            try:
                next_review = datetime.fromisoformat(str(item["next_review_at"]))
                if next_review.tzinfo is None:
                    next_review = next_review.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                next_review = datetime.min.replace(tzinfo=timezone.utc)
            if next_review <= now:
                due.append(item)
        return due

    def create_interview(
        self,
        *,
        target_role: str,
        scenario: str,
        difficulty: str,
        questions: list[str],
    ) -> dict[str, Any]:
        """创建模拟面试。"""
        interview_id = uuid.uuid4().hex[:16]
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO interview_sessions
                   (interview_id, target_role, scenario, difficulty, questions)
                   VALUES (?, ?, ?, ?, ?)""",
                (interview_id, target_role, scenario, difficulty, self._dump_json(questions)),
            )
            self._conn().commit()
        return self.get_interview(interview_id)

    def get_interview(self, interview_id: str) -> dict[str, Any] | None:
        """读取模拟面试及作答记录。"""
        row = self._conn().execute(
            "SELECT * FROM interview_sessions WHERE interview_id=?",
            (interview_id,),
        ).fetchone()
        interview = self._decode_row(row, ("questions",))
        if interview is None:
            return None
        turns = self._conn().execute(
            "SELECT * FROM interview_turns WHERE interview_id=? ORDER BY question_index",
            (interview_id,),
        ).fetchall()
        interview["turns"] = [self._decode_row(turn, ("dimensions",)) for turn in turns]
        return interview

    def save_interview_turn(
        self,
        *,
        interview_id: str,
        question_index: int,
        question: str,
        answer: str,
        score: float,
        dimensions: dict[str, float],
        feedback: str,
    ) -> dict[str, Any]:
        """保存单轮面试评分并推进进度。"""
        interview = self.get_interview(interview_id)
        if interview is None:
            raise ValueError("模拟面试不存在")
        next_index = question_index + 1
        completed = next_index >= len(interview["questions"])
        scores = [float(turn["score"]) for turn in interview["turns"]] + [score]
        with self._write_lock:
            connection = self._conn()
            turn_id = uuid.uuid4().hex
            connection.execute(
                """INSERT INTO interview_turns
                   (turn_id, interview_id, question_index, question, answer,
                    score, dimensions, feedback)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn_id, interview_id, question_index, question, answer,
                    score, self._dump_json(dimensions), feedback,
                ),
            )
            connection.execute(
                """UPDATE interview_sessions SET current_index=?, status=?,
                   overall_score=?, updated_at=? WHERE interview_id=?""",
                (
                    next_index,
                    "completed" if completed else "active",
                    round(sum(scores) / len(scores), 2),
                    _now_iso(),
                    interview_id,
                ),
            )
            connection.commit()
        return self.get_interview(interview_id)

    def create_study_plan(
        self,
        *,
        artifact_id: str,
        source_id: str | None,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """保存学习计划，并为每日完成状态建立持久化记录。"""
        existing = self._conn().execute(
            "SELECT plan_id FROM study_plans WHERE artifact_id=?",
            (artifact_id,),
        ).fetchone()
        if existing is not None:
            saved = self.get_study_plan(existing["plan_id"])
            if saved is not None:
                return saved

        plan_id = uuid.uuid4().hex
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO study_plans
                   (plan_id, artifact_id, source_id, title, exam_date,
                    daily_minutes, goal, plan_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan_id,
                    artifact_id,
                    source_id,
                    str(plan.get("title", "学习计划")),
                    str(plan.get("exam_date", "")),
                    int(plan.get("daily_minutes", 60)),
                    str(plan.get("goal", "")),
                    self._dump_json(plan),
                ),
            )
            self._conn().commit()
        saved = self.get_study_plan(plan_id)
        if saved is None:
            raise RuntimeError("学习计划保存失败")
        return saved

    def get_study_plan(self, plan_id: str) -> dict[str, Any] | None:
        """读取一份学习计划及已完成日期序号。"""
        row = self._conn().execute(
            "SELECT * FROM study_plans WHERE plan_id=?",
            (plan_id,),
        ).fetchone()
        if row is None:
            return None
        return self._decode_row(row, ("plan_data", "completed_days"))

    def list_study_plans(
        self,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """按最近更新顺序列出学习计划。"""
        if status is not None and status not in {"active", "completed", "archived"}:
            raise ValueError("无效的学习计划状态")
        query = "SELECT * FROM study_plans"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        rows = self._conn().execute(query, params).fetchall()
        return [
            self._decode_row(row, ("plan_data", "completed_days"))
            for row in rows
        ]

    def set_study_plan_day(
        self,
        plan_id: str,
        day_index: int,
        completed: bool,
    ) -> dict[str, Any]:
        """更新单个学习日状态，并自动维护计划状态。"""
        plan = self.get_study_plan(plan_id)
        if plan is None:
            raise ValueError("学习计划不存在")
        days = plan["plan_data"].get("daily_plan", [])
        if not 0 <= day_index < len(days):
            raise ValueError("学习日序号无效")

        completed_days = {int(item) for item in plan["completed_days"]}
        if completed:
            completed_days.add(day_index)
        else:
            completed_days.discard(day_index)
        normalized = sorted(completed_days)
        status = "completed" if days and len(normalized) == len(days) else "active"
        with self._write_lock:
            self._conn().execute(
                """UPDATE study_plans SET completed_days=?, status=?, updated_at=?
                   WHERE plan_id=?""",
                (self._dump_json(normalized), status, _now_iso(), plan_id),
            )
            self._conn().commit()
        updated = self.get_study_plan(plan_id)
        if updated is None:
            raise RuntimeError("学习计划更新失败")
        return updated

    def record_product_feedback(
        self,
        *,
        area: str,
        target_id: str,
        rating: int,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """保存不含原文和身份信息的匿名产品反馈。"""
        if area not in {"retrieval", "tutor", "interview", "study_plan"}:
            raise ValueError("无效的反馈区域")
        if rating not in {-1, 1}:
            raise ValueError("反馈评分只能为 -1 或 1")
        if not target_id.strip():
            raise ValueError("反馈目标不能为空")
        target_hash = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"filemate:feedback-target:{target_id}",
        ).hex
        feedback_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"filemate:feedback:{area}:{target_hash}",
        ).hex
        now = _now_iso()
        with self._write_lock:
            self._conn().execute(
                """INSERT INTO product_feedback
                   (feedback_id, area, target_hash, rating, context, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(area, target_hash) DO UPDATE SET
                       rating=excluded.rating,
                       context=excluded.context,
                       updated_at=excluded.updated_at""",
                (
                    feedback_id,
                    area,
                    target_hash,
                    rating,
                    self._dump_json(context or {}),
                    now,
                ),
            )
            self._conn().commit()
        row = self._conn().execute(
            "SELECT * FROM product_feedback WHERE feedback_id=?",
            (feedback_id,),
        ).fetchone()
        result = self._decode_row(row, ("context",))
        if result is None:
            raise RuntimeError("产品反馈保存失败")
        return result

    def list_product_feedback(
        self,
        *,
        area: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """读取匿名产品反馈，用于本地统计与导出。"""
        query = "SELECT * FROM product_feedback"
        params: list[Any] = []
        if area is not None:
            if area not in {"retrieval", "tutor", "interview", "study_plan"}:
                raise ValueError("无效的反馈区域")
            query += " WHERE area=?"
            params.append(area)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        rows = self._conn().execute(query, params).fetchall()
        return [self._decode_row(row, ("context",)) for row in rows]

    def get_product_feedback_summary(self) -> dict[str, Any]:
        """汇总匿名反馈数量和正向率。"""
        rows = self._conn().execute(
            """SELECT area, COUNT(*) AS total,
                      SUM(CASE WHEN rating=1 THEN 1 ELSE 0 END) AS positive
               FROM product_feedback GROUP BY area"""
        ).fetchall()
        by_area = {
            row["area"]: {
                "total": int(row["total"]),
                "positive": int(row["positive"] or 0),
                "positive_rate": round(
                    int(row["positive"] or 0) / int(row["total"]) * 100,
                    2,
                ),
            }
            for row in rows
        }
        total = sum(item["total"] for item in by_area.values())
        positive = sum(item["positive"] for item in by_area.values())
        return {
            "total": total,
            "positive": positive,
            "positive_rate": round(positive / total * 100, 2) if total else 0.0,
            "by_area": by_area,
        }

    def get_learning_analytics(self) -> dict[str, Any]:
        """汇总学习资产、错题与模拟面试指标。"""
        connection = self._conn()
        scalar_queries = {
            "source_count": "SELECT COUNT(*) FROM sources",
            "artifact_count": "SELECT COUNT(*) FROM artifacts",
            "pending_wrong_count": "SELECT COUNT(*) FROM wrong_questions WHERE mastered=0",
            "mastered_wrong_count": "SELECT COUNT(*) FROM wrong_questions WHERE mastered=1",
            "quiz_attempt_count": "SELECT COUNT(*) FROM quiz_attempts",
            "interview_count": "SELECT COUNT(*) FROM interview_sessions",
            "study_plan_count": "SELECT COUNT(*) FROM study_plans",
            "completed_study_plan_count": (
                "SELECT COUNT(*) FROM study_plans WHERE status='completed'"
            ),
        }
        result = {
            key: int(connection.execute(query).fetchone()[0])
            for key, query in scalar_queries.items()
        }
        average = connection.execute(
            "SELECT AVG(overall_score) FROM interview_sessions WHERE current_index > 0"
        ).fetchone()[0]
        result["average_interview_score"] = round(float(average or 0), 2)

        study_rows = connection.execute(
            "SELECT plan_data, completed_days FROM study_plans"
        ).fetchall()
        total_study_days = 0
        completed_study_days = 0
        for row in study_rows:
            try:
                plan_data = json.loads(row["plan_data"])
                completed_days = json.loads(row["completed_days"])
            except (TypeError, json.JSONDecodeError):
                continue
            total_study_days += len(plan_data.get("daily_plan", []))
            completed_study_days += len(completed_days)
        result["total_study_days"] = total_study_days
        result["completed_study_days"] = completed_study_days
        result["study_completion_rate"] = round(
            completed_study_days / total_study_days * 100,
            2,
        ) if total_study_days else 0.0
        result["product_feedback"] = self.get_product_feedback_summary()

        dimension_totals: dict[str, float] = {}
        dimension_counts: dict[str, int] = {}
        rows = connection.execute("SELECT dimensions FROM interview_turns").fetchall()
        for row in rows:
            try:
                dimensions = json.loads(row["dimensions"])
            except (TypeError, json.JSONDecodeError):
                continue
            for name, score in dimensions.items():
                dimension_totals[name] = dimension_totals.get(name, 0.0) + float(score)
                dimension_counts[name] = dimension_counts.get(name, 0) + 1
        result["interview_dimensions"] = {
            name: round(total / dimension_counts[name], 2)
            for name, total in dimension_totals.items()
        }

        recent_rows = connection.execute(
            """SELECT interview_id, target_role, scenario, status, current_index,
                      overall_score, created_at
               FROM interview_sessions ORDER BY updated_at DESC LIMIT 5"""
        ).fetchall()
        result["recent_interviews"] = [dict(row) for row in recent_rows]
        return result

    # ------------------------------------------------------------------
    # reversible execution
    # ------------------------------------------------------------------

    def start_execution(
        self,
        *,
        session_id: str,
        source_path: str,
        dest_path: str,
        input_snapshot: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        """创建待执行记录；已有未结束记录时原样返回。"""
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    """SELECT * FROM execution_records
                       WHERE session_id=? AND status IN ('pending','applied')
                       ORDER BY rowid DESC LIMIT 1""",
                    (session_id,),
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    decoded = self._decode_row(
                        existing,
                        ("input_snapshot", "output_snapshot"),
                    )
                    return decoded, False

                execution_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO execution_records
                       (execution_id, session_id, source_path, dest_path,
                        input_snapshot)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        execution_id,
                        session_id,
                        source_path,
                        dest_path,
                        self._dump_json(input_snapshot),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
            record = self.get_execution_record(execution_id)
            if record is None:
                raise RuntimeError("执行记录创建失败")
            return record, True

    def update_execution_record(
        self,
        execution_id: str,
        **kwargs: Any,
    ) -> None:
        """更新可撤销执行记录。"""
        if not kwargs:
            return
        invalid = set(kwargs) - _ALLOWED_EXECUTION_COLS
        if invalid:
            raise ValueError(f"无效执行字段: {sorted(invalid)}")
        values_map = dict(kwargs)
        if "output_snapshot" in values_map:
            values_map["output_snapshot"] = self._dump_json(
                values_map["output_snapshot"]
            )
        set_clause = ", ".join(f"{key}=?" for key in values_map)
        values = [*values_map.values(), _now_iso(), execution_id]
        with self._write_lock:
            self._conn().execute(
                f"""UPDATE execution_records SET {set_clause}, updated_at=?
                    WHERE execution_id=?""",
                values,
            )
            self._conn().commit()

    def get_execution_record(
        self,
        execution_id: str,
    ) -> dict[str, Any] | None:
        """读取单条执行记录。"""
        row = self._conn().execute(
            "SELECT * FROM execution_records WHERE execution_id=?",
            (execution_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def get_active_execution(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """读取 Session 当前已应用、尚未撤销的执行。"""
        row = self._conn().execute(
            """SELECT * FROM execution_records
               WHERE session_id=? AND status='applied'
               ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def get_latest_execution(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """读取 Session 最近一次执行记录。"""
        row = self._conn().execute(
            """SELECT * FROM execution_records WHERE session_id=?
               ORDER BY rowid DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return self._decode_row(
            row,
            ("input_snapshot", "output_snapshot"),
        )

    def list_execution_records(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """按时间倒序列出 Session 的执行与撤销历史。"""
        rows = self._conn().execute(
            """SELECT * FROM execution_records WHERE session_id=?
               ORDER BY rowid DESC""",
            (session_id,),
        ).fetchall()
        return [
            self._decode_row(
                row,
                ("input_snapshot", "output_snapshot"),
            )
            for row in rows
        ]

    def finalize_execution(
        self,
        *,
        execution_id: str,
        session_id: str,
        entities: dict[str, Any],
        dest_path: str,
        ics_path: str | None,
        output_snapshot: dict[str, Any],
    ) -> None:
        """原子完成执行记录、Session 状态和审计日志。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                updated = conn.execute(
                    """UPDATE execution_records
                       SET status='applied', dest_path=?, ics_path=?,
                           output_snapshot=?, error='', applied_at=?,
                           updated_at=?
                       WHERE execution_id=? AND status='pending'""",
                    (
                        dest_path,
                        ics_path,
                        self._dump_json(output_snapshot),
                        now,
                        now,
                        execution_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("执行记录状态已变化，无法完成")
                conn.execute(
                    """UPDATE sessions
                       SET status='confirmed', entities=?, error='', updated_at=?
                       WHERE session_id=?""",
                    (self._dump_json(entities), now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail, input_snapshot)
                       VALUES (?, 'execute', ?, ?)""",
                    (
                        session_id,
                        dest_path,
                        self._dump_json(output_snapshot),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def fail_execution(
        self,
        *,
        execution_id: str,
        session_id: str,
        error: str,
    ) -> None:
        """原子标记执行失败并记录审计信息。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """UPDATE execution_records
                       SET status='failed', error=?, updated_at=?
                       WHERE execution_id=? AND status='pending'""",
                    (error, now, execution_id),
                )
                conn.execute(
                    """UPDATE sessions
                       SET status='failed', error=?, updated_at=?
                       WHERE session_id=?""",
                    (error, now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail)
                       VALUES (?, 'execute_failed', ?)""",
                    (session_id, error),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise

    def finalize_undo(
        self,
        *,
        execution_id: str,
        session_id: str,
        entities: dict[str, Any],
    ) -> None:
        """原子完成撤销并将 Session 恢复为待确认状态。"""
        now = _now_iso()
        with self._write_lock:
            conn = self._conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                updated = conn.execute(
                    """UPDATE execution_records
                       SET status='undone', undone_at=?, updated_at=?
                       WHERE execution_id=? AND status='applied'""",
                    (now, now, execution_id),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("执行记录已撤销或状态已变化")
                conn.execute(
                    """UPDATE sessions
                       SET status='done', entities=?, error='', updated_at=?
                       WHERE session_id=?""",
                    (self._dump_json(entities), now, session_id),
                )
                conn.execute(
                    """INSERT INTO operation_log
                       (session_id, action, detail, input_snapshot)
                       VALUES (?, 'undo', ?, ?)""",
                    (
                        session_id,
                        execution_id,
                        self._dump_json(
                            {
                                "execution_id": execution_id,
                                "restored": True,
                            }
                        ),
                    ),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
