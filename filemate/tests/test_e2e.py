"""端到端集成测试（W4 里程碑）。TODO(余恒 + 胡希)"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from filemate.core.session import ProcessingSession, SessionStatus
from filemate.execution.storage import SQLiteStorage


# ──────────────────────────────────────────────
#  W4 里程碑样本（占位：实际样本由汤新阳提供）
# ──────────────────────────────────────────────

SAMPLE_FILES = [
    # (文件名, 预期分类)
    # TODO(汤新阳 + 张金宝): W4 前填入 20 份真实样本
    ("sample_课件_01.pdf", "课件"),
    ("sample_作业_01.docx", "作业"),
    ("sample_竞赛通知_01.pdf", "竞赛通知"),
    ("sample_考试通知_01.pdf", "考试通知"),
]


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_filemate.db"


@pytest.fixture()
def storage(db_path: Path) -> SQLiteStorage:
    s = SQLiteStorage(db_path)
    s.init_schema()
    yield s
    s.close()


class TestSessionLifecycle:
    """Session 状态机正确性。"""

    def test_happy_path(self, storage: SQLiteStorage) -> None:
        sid = "test-happy"
        storage.create_session(sid, "/fake/path")
        s = ProcessingSession(session_id=sid, source_path="/fake/path")
        s.transition(SessionStatus.PROCESSING)
        s.transition(SessionStatus.DONE)
        s.transition(SessionStatus.CONFIRMED)
        assert s.is_terminal()

    def test_invalid_transition_raises(self) -> None:
        s = ProcessingSession(session_id="x")
        with pytest.raises(ValueError):
            s.transition(SessionStatus.CONFIRMED)  # pending -> confirmed 不合法

    def test_retry_from_failed(self, storage: SQLiteStorage) -> None:
        sid = "test-retry"
        s = ProcessingSession(session_id=sid)
        s.transition(SessionStatus.PROCESSING)
        s.transition(SessionStatus.FAILED)
        s.transition(SessionStatus.PROCESSING)  # 允许重试
        assert not s.is_terminal()


class TestStorageRoundTrip:
    """SQLite 读写往返。"""

    def test_create_and_get(self, storage: SQLiteStorage) -> None:
        sid = "rt-1"
        storage.create_session(sid, "/tmp/a.docx")
        row = storage.get_session(sid)
        assert row is not None
        assert row["session_id"] == sid
        assert row["status"] == "pending"

    def test_update_session(self, storage: SQLiteStorage) -> None:
        sid = "rt-2"
        storage.create_session(sid, "/tmp/b.pdf")
        storage.update_session(sid, category="课件", confidence=0.92)
        row = storage.get_session(sid)
        assert row["category"] == "课件"
        assert abs(row["confidence"] - 0.92) < 1e-6

    def test_list_sessions_filter(self, storage: SQLiteStorage) -> None:
        for i in range(3):
            storage.create_session(f"ls-{i}", f"/tmp/{i}.pdf")
            if i == 0:
                storage.update_session(f"ls-{i}", status="done")
        done = storage.list_sessions("done")
        assert len(done) == 1
        assert done[0]["session_id"] == "ls-0"


class TestDuplicateDetection:
    """去重逻辑。"""

    def test_new_hash_not_duplicate(self, storage: SQLiteStorage) -> None:
        assert not storage.is_duplicate("abc123")

    def test_record_and_detect(self, storage: SQLiteStorage) -> None:
        storage.record_hash("deadbeef", "s-1")
        assert storage.is_duplicate("deadbeef")

    def test_same_hash_same_session_idempotent(self, storage: SQLiteStorage) -> None:
        storage.record_hash("hash1", "s-1")
        storage.record_hash("hash1", "s-1")  # 重复写入不报错
        assert storage.is_duplicate("hash1")


class TestOperationLog:
    """操作日志。"""

    def test_log_and_query(self, storage: SQLiteStorage) -> None:
        storage.create_session("log-1", "/tmp/x.pdf")
        storage.log_operation("log-1", "classify", "课件 0.9")
        ops = storage.get_operations("log-1")
        assert len(ops) == 1
        assert ops[0]["op"] == "classify"
        assert "0.9" in ops[0]["detail"]
