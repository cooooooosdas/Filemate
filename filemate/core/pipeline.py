"""PipelineWorker：单 Worker 异步消费队列。"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import Any, Callable

from .session import ProcessingSession, SessionStatus

logger = logging.getLogger(__name__)

# 每个处理阶段的函数签名：
#   (ProcessingSession) -> ProcessingSession
# 抛出异常视为阶段失败，session 进入 failed 状态。

StageFn = Callable[[ProcessingSession], ProcessingSession]


class PipelineWorker:
    """异步处理流水线：watchdog / 命令行 → 入队 → 单 Worker 顺序消费。

    调用方通过 *stage_fn 参数注入各阶段实现，pipeline 本身不依赖具体模块。
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        *,
        on_complete: Callable[[ProcessingSession], None] | None = None,
        stages: list[StageFn] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        queue : asyncio.Queue
            入队（ProcessingSession）。
        on_complete : callable, optional
            每个 session 完成后回调（无论成功/失败）。
        stages : list[StageFn]
            处理阶段链，按顺序执行。
            典型顺序：parse → classify → extract → detect_milestones → generate_name
        """
        self.queue = queue
        self.on_complete = on_complete
        self.stages: list[StageFn] = stages or []
        self._running = False
        self._processed = 0
        self._failed = 0

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """消费循环，直到收到 None 哨兵。"""
        self._running = True
        logger.info("PipelineWorker 启动，阶段数=%d", len(self.stages))
        while self._running:
            session = await self.queue.get()
            try:
                if session is None:
                    # 哨兵：优雅关闭
                    self._running = False
                    self.queue.task_done()
                    break
                await self._process(session)
            except asyncio.CancelledError:
                logger.info("PipelineWorker 被取消")
                raise
            except Exception as exc:
                logger.exception("Pipeline 未捕获异常: %s", exc)
            finally:
                self.queue.task_done()

        logger.info(
            "PipelineWorker 停止，共处理 %d 个文件（失败 %d）",
            self._processed,
            self._failed,
        )

    # ------------------------------------------------------------------
    # 单文件处理
    # ------------------------------------------------------------------

    async def _process(self, session: ProcessingSession) -> None:
        """对单个 session 顺序执行所有阶段。"""
        t0 = time.perf_counter()
        session.transition(SessionStatus.PROCESSING)
        logger.info("[%s] 开始处理: %s", session.session_id, session.source_path)

        for idx, stage in enumerate(self.stages, 1):
            stage_name = getattr(stage, "__name__", f"stage_{idx}")
            try:
                logger.debug("[%s] 阶段 %d/%d: %s", session.session_id, idx, len(self.stages), stage_name)
                session = stage(session)
            except Exception as exc:
                session.error = f"{stage_name} 失败: {exc}"
                session.transition(SessionStatus.FAILED)
                logger.error("[%s] %s\n%s", session.session_id, session.error, traceback.format_exc())
                self._failed += 1
                break

        else:
            # 所有阶段通过
            session.transition(SessionStatus.DONE)
            self._processed += 1
            elapsed = time.perf_counter() - t0
            logger.info("[%s] 完成 (%.2fs): %s -> %s", session.session_id, elapsed, session.source_path, session.suggested_name)

        if self.on_complete:
            try:
                self.on_complete(session)
            except Exception:
                logger.exception("on_complete 回调失败: %s", session.session_id)

    # ------------------------------------------------------------------
    # 便捷：从 stages 列表构造阶段
    # ------------------------------------------------------------------

    @staticmethod
    def make_stage(name: str) -> Callable[[StageFn], StageFn]:
        """装饰器：给阶段_fn 加上 __name__（用于日志）。"""
        def decorator(fn: StageFn) -> StageFn:
            fn.__name__ = name
            return fn
        return decorator
