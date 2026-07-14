"""PipelineWorker：单 Worker 异步消费队列。"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .session import ProcessingSession, SessionStatus

logger = logging.getLogger(__name__)


class PipelineWorker:
    """异步处理流水线：watchdog 入队 → 单 Worker 顺序消费。"""

    def __init__(
        self,
        queue: asyncio.Queue,
        *,
        on_complete: Callable[[ProcessingSession], None] | None = None,
    ) -> None:
        self.queue = queue
        self.on_complete = on_complete
        self._running = False

    async def run(self) -> None:
        """TODO(胡希): 实现异步消费循环 + 错误恢复。"""
        raise NotImplementedError("TODO(胡希): PipelineWorker.run()")

    async def _process(self, session: ProcessingSession) -> None:
        """对单个 session 依次调用 感知 → 理解 → 执行。"""
        raise NotImplementedError("TODO(胡希)")
