"""SQLite 持久化。"""

from __future__ import annotations

from pathlib import Path


class SQLiteStorage:
    """SQLite 存储封装（四张表：sessions / processed_files / operation_log / user_rules）。"""

    def __init__(self, db_path: str | Path = "filemate.db") -> None:
        self.db_path = Path(db_path)

    def init_schema(self) -> None:
        """TODO(徐书和): 建表 + CHECK 约束 + 索引。"""
        raise NotImplementedError("TODO(徐书和): init_schema")

    def is_duplicate(self, file_hash: str) -> bool:
        """TODO(徐书和): 按哈希查重。"""
        raise NotImplementedError("TODO(徐书和)")

    def record_hash(self, file_hash: str, session_id: str) -> None:
        """TODO(徐书和): 记录已处理文件哈希。"""
        raise NotImplementedError("TODO(徐书和)")

    def log_operation(self, session_id: str, op: str, detail: str = "") -> None:
        """TODO(徐书和): 写入操作日志。"""
        raise NotImplementedError("TODO(徐书和)")
