"""最终确认、归档与撤销闭环测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from filemate.execution.confirmation_executor import (
    ConfirmationExecutor,
    ExecutionError,
)
from filemate.execution.storage import SQLiteStorage


class FakeCalendar:
    """避免单元测试依赖真实日历序列化。"""

    def save(self, events: list, out_path: str | Path) -> Path:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"events={len(events)}", encoding="utf-8")
        return path


class FailingCalendar:
    def save(self, events: list, out_path: str | Path) -> Path:
        raise RuntimeError("日历写入失败")


@pytest.fixture()
def storage(tmp_path: Path) -> SQLiteStorage:
    instance = SQLiteStorage(tmp_path / "execution.db")
    instance.init_schema()
    yield instance
    instance.close()


def create_ready_session(
    storage: SQLiteStorage,
    source: Path,
    *,
    session_id: str = "session-exec",
    suggested_name: str = "第一章进程管理",
) -> dict:
    """创建与处理流水线输出一致的待确认 Session。"""
    storage.create_session(session_id, str(source))
    storage.update_session(
        session_id,
        status="done",
        category="课件",
        confidence=0.95,
        suggested_name=suggested_name,
        entities=json.dumps(
            {
                "course_name": "操作系统",
                "deadline": "2026-08-20",
                "task_description": "复习进程管理",
                "calendar_enabled": True,
            },
            ensure_ascii=False,
        ),
        milestones=json.dumps(
            [{"event": "章节测验", "date": "2026-08-18", "order": 1}],
            ensure_ascii=False,
        ),
    )
    session = storage.get_session(session_id)
    assert session is not None
    return session


def test_execute_and_undo_restore_file_and_session(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"course-content")
    session = create_ready_session(storage, source)
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
        calendar=FakeCalendar(),
    )

    applied = executor.execute(session)
    destination = Path(applied["dest_path"])
    ics_path = Path(applied["ics_path"])

    assert applied["status"] == "applied"
    assert applied["can_undo"] is True
    assert destination == (
        tmp_path
        / "archive"
        / "操作系统"
        / "课件"
        / "第一章进程管理.pdf"
    )
    assert destination.read_bytes() == b"course-content"
    assert not source.exists()
    assert ics_path.read_text(encoding="utf-8") == "events=2"
    confirmed = storage.get_session("session-exec")
    assert confirmed["status"] == "confirmed"
    entities = json.loads(confirmed["entities"])
    assert entities["archived_path"] == str(destination)

    undone = executor.undo("session-exec")

    assert undone["status"] == "undone"
    assert undone["can_undo"] is False
    assert source.read_bytes() == b"course-content"
    assert not destination.exists()
    assert not ics_path.exists()
    restored = storage.get_session("session-exec")
    assert restored["status"] == "done"
    restored_entities = json.loads(restored["entities"])
    assert "archived_path" not in restored_entities
    assert "ics_path" not in restored_entities


def test_execute_and_undo_are_idempotent(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("content", encoding="utf-8")
    session = create_ready_session(storage, source)
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
        calendar=FakeCalendar(),
    )

    first = executor.execute(session)
    repeated = executor.execute(session)
    first_undo = executor.undo("session-exec")
    repeated_undo = executor.undo("session-exec")

    assert repeated["execution_id"] == first["execution_id"]
    assert repeated["idempotent"] is True
    assert repeated_undo["execution_id"] == first_undo["execution_id"]
    assert repeated_undo["idempotent"] is True
    assert len(storage.list_execution_records("session-exec")) == 1


def test_destination_collision_never_overwrites(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"new")
    session = create_ready_session(storage, source)
    collision = (
        tmp_path
        / "archive"
        / "操作系统"
        / "课件"
        / "第一章进程管理.pdf"
    )
    collision.parent.mkdir(parents=True)
    collision.write_bytes(b"existing")
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
        calendar=FakeCalendar(),
    )

    with pytest.raises(ExecutionError, match="目标已存在"):
        executor.execute(session)

    assert source.read_bytes() == b"new"
    assert collision.read_bytes() == b"existing"
    assert storage.get_session("session-exec")["status"] == "failed"
    assert storage.get_latest_execution("session-exec")["status"] == "failed"


def test_calendar_failure_rolls_back_file_move(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"safe")
    session = create_ready_session(storage, source)
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
        calendar=FailingCalendar(),
    )

    with pytest.raises(ExecutionError, match="日历写入失败"):
        executor.execute(session)

    assert source.read_bytes() == b"safe"
    assert not (tmp_path / "archive" / "操作系统" / "课件" / "第一章进程管理.pdf").exists()
    assert storage.get_session("session-exec")["status"] == "failed"


def test_rejects_extension_change_before_creating_record(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"pdf")
    session = create_ready_session(
        storage,
        source,
        suggested_name="伪装文档.docx",
    )
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
    )

    with pytest.raises(ExecutionError, match="不能把 .pdf 文件改成 .docx"):
        executor.execute(session)

    assert source.exists()
    assert storage.list_execution_records("session-exec") == []


def test_undo_refuses_to_overwrite_original_location(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    source = tmp_path / "lesson.txt"
    source.write_text("original", encoding="utf-8")
    session = create_ready_session(storage, source)
    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=tmp_path / "archive",
        calendar=FakeCalendar(),
    )
    applied = executor.execute(session)
    source.write_text("new occupant", encoding="utf-8")

    with pytest.raises(ExecutionError, match="原位置已有同名文件"):
        executor.undo("session-exec")

    assert source.read_text(encoding="utf-8") == "new occupant"
    assert Path(applied["dest_path"]).read_text(encoding="utf-8") == "original"
    assert storage.get_active_execution("session-exec") is not None


def test_recover_after_interrupted_archive(
    storage: SQLiteStorage,
    tmp_path: Path,
) -> None:
    """归档完成后进程崩溃（record 停在 pending）→ 再次 execute 恢复并 finalize。"""
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"content")
    session = create_ready_session(storage, source)
    archive_dir = tmp_path / "archive"
    dest = archive_dir / "操作系统" / "课件" / "第一章进程管理.pdf"

    # 模拟崩溃现场：文件已归档，但 execution record 停在 pending
    dest.parent.mkdir(parents=True, exist_ok=True)
    source.rename(dest)
    storage.start_execution(
        session_id="session-exec",
        source_path=str(source),
        dest_path=str(dest),
        input_snapshot={"source_path": str(source), "source_exists": False},
    )

    executor = ConfirmationExecutor(
        storage=storage,
        archive_dir=archive_dir,
        calendar=FakeCalendar(),
    )
    applied = executor.execute(session)

    assert applied["status"] == "applied"
    assert dest.exists()
    assert not source.exists()
    assert storage.get_session("session-exec")["status"] == "confirmed"
