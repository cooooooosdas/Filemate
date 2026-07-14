"""SQLite 状态存储（薄封装，底层委托给 execution.storage）。"""

from __future__ import annotations

from pathlib import Path

from ..execution.storage import SQLiteStorage


class SQLiteStateStore:
    """为上层（Pipeline / UI）提供 session 级别的读写接口。

    底层全部委托给 SQLiteStorage；此处仅做语义层封装。
    """

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self._impl = SQLiteStorage(db_path)
        self._impl.init_schema()

    # 让外部也可以访问底层存储（供批量操作等高级场景）
    @property
    def storage(self) -> SQLiteStorage:
        return self._impl

    # ------------------------------------------------------------------
    # Session 生命周期
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, source_path: str) -> None:
        self._impl.create_session(session_id, source_path)

    def update_session(self, session_id: str, **kwargs) -> None:
        self._impl.update_session(session_id, **kwargs)

    def get_session(self, session_id: str) -> dict | None:
        return self._impl.get_session(session_id)

    def list_sessions(self, status: str | None = None) -> list[dict]:
        return self._impl.list_sessions(status)

    # ------------------------------------------------------------------
    # 去重
    # ------------------------------------------------------------------

    def is_duplicate(self, file_hash: str) -> bool:
        return self._impl.is_duplicate(file_hash)

    def record_hash(self, file_hash: str, session_id: str) -> None:
        self._impl.record_hash(file_hash, session_id)

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def log_operation(self, session_id: str, op: str, detail: str = "") -> None:
        self._impl.log_operation(session_id, op, detail)

    def get_operations(self, session_id: str) -> list[dict]:
        return self._impl.get_operations(session_id)
