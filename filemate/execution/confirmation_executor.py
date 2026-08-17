"""用户最终确认后的事务式执行与撤销。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .archiver import Archiver
from .file_ops import FileOps
from .scheduler import CalendarBuilder, CalendarEvent
from .storage import SQLiteStorage


class ExecutionError(RuntimeError):
    """确认执行或撤销无法安全完成。"""


class ConfirmationExecutor:
    """把确认结果应用到文件系统，并保留可验证的撤销记录。"""

    def __init__(
        self,
        *,
        storage: SQLiteStorage,
        archive_dir: str | Path,
        file_ops: FileOps | None = None,
        calendar: CalendarBuilder | None = None,
    ) -> None:
        self.storage = storage
        self.file_ops = file_ops or FileOps()
        self.calendar = calendar or CalendarBuilder()
        self.archiver = Archiver(archive_dir, self.file_ops)

    @staticmethod
    def _json_value(value: Any, fallback: Any) -> Any:
        """兼容数据库原始 JSON 字符串与已解码对象。"""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return value if value is not None else fallback

    def _target_name(self, source: Path, suggested_name: str) -> str:
        """确保归档只改变名称，不伪造文件格式。"""
        desired = suggested_name.strip() or source.name
        suffix = Path(desired).suffix
        if suffix and suffix.lower() != source.suffix.lower():
            raise ExecutionError(
                f"不能把 {source.suffix or '无扩展名'} 文件改成 {suffix} 格式"
            )
        if not suffix:
            desired = f"{desired}{source.suffix}"
        try:
            return self.file_ops.validate_filename(desired)
        except ValueError as exc:
            raise ExecutionError(str(exc)) from exc

    def _calendar_events(
        self,
        session: dict[str, Any],
        entities: dict[str, Any],
        source_name: str,
    ) -> list[CalendarEvent]:
        """从里程碑和截止日期构建去重后的日历事件。"""
        if entities.get("calendar_enabled") is False:
            return []
        events: list[CalendarEvent] = []
        seen: set[tuple[str, str]] = set()
        milestones = self._json_value(session.get("milestones"), [])
        for milestone in milestones:
            if not isinstance(milestone, dict):
                continue
            start = str(milestone.get("date") or "").strip()
            event_name = str(milestone.get("event") or "").strip()
            if not start or not event_name or (start, event_name) in seen:
                continue
            seen.add((start, event_name))
            events.append(
                CalendarEvent(
                    summary=f"[{session.get('category') or '待确认'}] {event_name}",
                    start=start,
                    location=str(entities.get("location") or ""),
                    description=f"来源: {source_name}",
                )
            )

        deadline = str(entities.get("deadline") or "").strip()
        if deadline:
            task = str(
                entities.get("task_description")
                or Path(source_name).stem
            ).strip()
            key = (deadline, task)
            if key not in seen:
                events.append(
                    CalendarEvent(
                        summary=f"[{session.get('category') or '待确认'}] {task}",
                        start=deadline,
                        location=str(entities.get("location") or ""),
                        description=f"来源: {source_name}",
                    )
                )
        return events

    def execute(self, session: dict[str, Any]) -> dict[str, Any]:
        """最终确认并执行归档；重复调用返回同一已应用记录。"""
        session_id = str(session.get("session_id") or "")
        if not session_id:
            raise ExecutionError("Session ID 不能为空")
        source = Path(str(session.get("source_path") or ""))
        entities = dict(self._json_value(session.get("entities"), {}))
        category = str(session.get("category") or "待确认")
        course = str(entities.get("course_name") or "未分类")
        target_name = self._target_name(
            source,
            str(session.get("suggested_name") or ""),
        )
        try:
            planned_dest = self.archiver.preview_dest(
                self.archiver.base_dir,
                category,
                course,
                target_name,
            )
        except ValueError as exc:
            raise ExecutionError(str(exc)) from exc

        input_snapshot = {
            "source_path": str(source),
            "source_exists": source.is_file(),
            "source_hash": (
                self.file_ops.compute_hash(source) if source.is_file() else None
            ),
            "category": category,
            "course_name": course,
            "suggested_name": target_name,
        }
        record, created = self.storage.start_execution(
            session_id=session_id,
            source_path=str(source),
            dest_path=str(planned_dest),
            input_snapshot=input_snapshot,
        )
        if record["status"] == "applied":
            return self._result(record, idempotent=True)

        execution_id = record["execution_id"]
        dest = Path(record["dest_path"])
        events = self._calendar_events(session, entities, source.name)
        planned_ics = dest.with_suffix(".ics") if events else None
        moved = False
        created_ics = False

        try:
            if source.exists() and dest.exists():
                raise ExecutionError(f"归档目标已存在: {dest}")
            if not source.exists() and not dest.exists():
                raise ExecutionError(f"源文件和归档文件均不存在: {source}")
            if created and planned_ics and planned_ics.exists():
                raise ExecutionError(f"日历目标已存在: {planned_ics}")

            if source.exists():
                result = self.archiver.archive(
                    session_id=session_id,
                    category=category,
                    course=course,
                    new_name=target_name,
                    source_path=source,
                )
                if not result.success:
                    raise ExecutionError(result.error)
                dest = Path(result.dest_path)
                moved = True

            ics_path: Path | None = None
            if planned_ics:
                ics_path = dest.with_suffix(".ics")
                if not ics_path.exists():
                    self.calendar.save(events, ics_path)
                    created_ics = True

            output_snapshot = {
                "execution_id": execution_id,
                "dest_path": str(dest),
                "dest_exists": dest.is_file(),
                "dest_hash": self.file_ops.compute_hash(dest),
                "ics_path": str(ics_path) if ics_path else None,
                "calendar_events": len(events),
            }
            entities["archived_path"] = str(dest)
            entities["execution_id"] = execution_id
            if ics_path:
                entities["ics_path"] = str(ics_path)
            else:
                entities.pop("ics_path", None)
            self.storage.finalize_execution(
                execution_id=execution_id,
                session_id=session_id,
                entities=entities,
                dest_path=str(dest),
                ics_path=str(ics_path) if ics_path else None,
                output_snapshot=output_snapshot,
            )
            completed = self.storage.get_execution_record(execution_id)
            if completed is None:
                raise RuntimeError("执行完成后记录不可读")
            return self._result(completed, idempotent=not created)
        except Exception as exc:
            rollback_errors: list[str] = []
            if created_ics and planned_ics and planned_ics.exists():
                try:
                    planned_ics.unlink()
                except OSError as rollback_exc:
                    rollback_errors.append(f"日历回滚失败: {rollback_exc}")
            if moved and dest.exists() and not source.exists():
                rollback = self.file_ops.move(dest, source)
                if not rollback.success:
                    rollback_errors.append(f"文件回滚失败: {rollback.error}")
            message = str(exc)
            if rollback_errors:
                message = f"{message}；{'；'.join(rollback_errors)}"
            self.storage.fail_execution(
                execution_id=execution_id,
                session_id=session_id,
                error=message,
            )
            raise ExecutionError(message) from exc

    def undo(self, session_id: str) -> dict[str, Any]:
        """撤销当前已应用操作，并恢复原文件位置。"""
        record = self.storage.get_active_execution(session_id)
        if record is None:
            latest = self.storage.get_latest_execution(session_id)
            if latest and latest["status"] == "undone":
                return self._result(latest, idempotent=True)
            raise ExecutionError("没有可撤销的已执行操作")

        source = Path(record["source_path"])
        dest = Path(record["dest_path"])
        ics_path = Path(record["ics_path"]) if record.get("ics_path") else None
        if source.exists():
            raise ExecutionError(f"原位置已有同名文件，无法撤销: {source}")
        if not dest.exists():
            raise ExecutionError(f"归档文件不存在，无法撤销: {dest}")

        ics_bytes = ics_path.read_bytes() if ics_path and ics_path.exists() else None
        restore = self.file_ops.move(dest, source)
        if not restore.success:
            raise ExecutionError(restore.error)

        try:
            if ics_path and ics_path.exists():
                ics_path.unlink()
            session = self.storage.get_session(session_id)
            if session is None:
                raise ExecutionError("Session 不存在")
            entities = dict(self._json_value(session.get("entities"), {}))
            for key in ("archived_path", "ics_path", "execution_id"):
                entities.pop(key, None)
            self.storage.finalize_undo(
                execution_id=record["execution_id"],
                session_id=session_id,
                entities=entities,
            )
        except Exception as exc:
            rollback = self.file_ops.move(source, dest)
            if ics_path and ics_bytes is not None and not ics_path.exists():
                ics_path.write_bytes(ics_bytes)
            message = str(exc)
            if not rollback.success:
                message = f"{message}；撤销回滚失败: {rollback.error}"
            raise ExecutionError(message) from exc

        completed = self.storage.get_execution_record(record["execution_id"])
        if completed is None:
            raise RuntimeError("撤销完成后记录不可读")
        return self._result(completed, idempotent=False)

    @staticmethod
    def _result(
        record: dict[str, Any],
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        """转换为稳定的 API 返回结构。"""
        return {
            "execution_id": record["execution_id"],
            "status": record["status"],
            "source_path": record["source_path"],
            "dest_path": record["dest_path"],
            "ics_path": record.get("ics_path"),
            "can_undo": record["status"] == "applied",
            "idempotent": idempotent,
            "error": record.get("error") or "",
        }
