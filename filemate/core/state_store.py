"""SQLite 状态存储（薄封装，底层委托给 execution.storage）。"""

from __future__ import annotations

from pathlib import Path


class SQLiteStateStore:
    """TODO(徐书和 + 胡希): 最终实现迁移至 execution/storage.py。"""

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)

    def create_session(self, session_id: str, source_path: str) -> None:
        raise NotImplementedError("TODO(徐书和)")

    def update_session(self, session_id: str, **kwargs) -> None:
        raise NotImplementedError("TODO(徐书和)")

    def get_session(self, session_id: str) -> dict | None:
        raise NotImplementedError("TODO(徐书和)")

    def list_sessions(self, status: str | None = None) -> list[dict]:
        raise NotImplementedError("TODO(徐书和)")
