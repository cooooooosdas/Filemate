"""批量处理队列。"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class BatchProcessor:
    """批量处理（限制并发度 + 进度回调）。"""

    def __init__(self, worker, *, concurrency: int = 2) -> None:
        """
        Parameters
        ----------
        worker:
            一个 *异步可调用对象*，接收单个 path 返回 dict。
            实际使用中传入 PipelineWorker.process_one。
        concurrency:
            最大并发数。默认 2（避免并发文件 I/O 冲突）。
        """
        self.worker = worker
        self.concurrency = max(1, concurrency)
        self._semaphore: asyncio.Semaphore | None = None

    async def process_batch(
        self,
        paths: list[str],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[dict]:
        """并发处理多个文件，通过 on_progress(done, total, path) 上报进度。

        Returns 与 paths 等长的结果列表（顺序保持一致）。
        """
        if not paths:
            return []

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrency)

        results: list[dict] = [{} for _ in paths]

        async def _run(index: int, path: str) -> None:
            async with self._semaphore:
                logger.debug("批量处理 [%d/%d]: %s", index + 1, len(paths), path)
                try:
                    result = await self.worker(path)  # type: ignore[call-arg]
                except Exception as exc:
                    logger.exception("处理失败: %s", path)
                    result = {"path": path, "success": False, "error": str(exc)}
                results[index] = result
                if on_progress:
                    on_progress(index + 1, len(paths), path)

        tasks = [asyncio.create_task(_run(i, p)) for i, p in enumerate(paths)]
        await asyncio.gather(*tasks)
        return results
