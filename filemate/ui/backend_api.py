"""Gradio 后端 API 封装，供 UI 层调用。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class BackendAPI:
    """FileMate 后端 API。Gradio 界面通过本类与后端交互。

    实际使用::

        api = BackendAPI(pipeline_worker, state_store)
        api.submit("/path/to/file.docx")
        api.get_queue()
        api.confirm(session_id, accepted=True)
    """

    def __init__(self, pipeline_worker, state_store) -> None:
        """
        Parameters
        ----------
        pipeline_worker : PipelineWorker
            已初始化（含阶段链）的流水线。
        state_store : SQLiteStateStore
            已初始化 schema 的 SQLite 状态存储。
        """
        self.pipeline = pipeline_worker
        self.store = state_store

    # ------------------------------------------------------------------
    # 提交
    # ------------------------------------------------------------------

    def submit(self, file_path: str) -> dict:
        """将文件路径入队，返回创建时的 session 信息。

        Returns
        -------
        dict with keys: session_id, source_path, status
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}

        session_id = uuid.uuid4().hex[:12]
        self.store.create_session(session_id, str(path))

        # 构造 session 并入队
        from filemate.core.session import ProcessingSession
        session = ProcessingSession(session_id=session_id, source_path=str(path))
        try:
            asyncio.get_event_loop().run_until_complete(
                self.pipeline.queue.put(session)
            )
        except RuntimeError:
            # 没有 event loop（在同步上下文中）
            asyncio.run(self.pipeline.queue.put(session))

        logger.info("submit: %s -> session %s", path.name, session_id)
        return session.to_dict()

    def submit_batch(self, paths: list[str]) -> list[dict]:
        """批量提交。"""
        return [self.submit(p) for p in paths]

    # ------------------------------------------------------------------
    # 确认 / 拒绝
    # ------------------------------------------------------------------

    def confirm(
        self,
        session_id: str,
        accepted: bool,
        edits: dict | None = None,
    ) -> dict:
        """用户确认/拒绝 AI 建议。

        Parameters
        ----------
        accepted : bool
            True = 用户接受了建议；False = 用户拒绝。
        edits : dict, optional
            用户修改后的字段（如 suggested_name）。
        """
        session = self.store.get_session(session_id)
        if not session:
            return {"error": f"session 不存在: {session_id}"}

        # 持久化用户修改
        updates: dict = {}
        if edits:
            updates.update(edits)
        if accepted:
            updates["status"] = "confirmed"
        else:
            updates["status"] = "skipped"

        self.store.update_session(session_id, **updates)
        self.store.log_operation(
            session_id,
            "confirm" if accepted else "reject",
            detail=str(edits or {}),
        )
        logger.info("confirm: session %s accepted=%s", session_id, accepted)
        return {"ok": True, "session_id": session_id, "accepted": accepted}

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> dict | None:
        """按 ID 获取 session 详情。"""
        return self.store.get_session(session_id)

    def get_queue(self, status: str | None = None) -> list[dict]:
        """获取 session 列表（按 created_at 降序）。"""
        return self.store.list_sessions(status=status)

    def get_operations(self, session_id: str) -> list[dict]:
        """获取指定 session 的操作日志。"""
        return self.store.get_operations(session_id)

    def is_duplicate(self, file_hash: str) -> bool:
        """检查文件哈希是否已处理过。"""
        return self.store.is_duplicate(file_hash)
