"""批量处理队列。"""

from __future__ import annotations

import asyncio
from typing import Callable


class BatchProcessor:
    """批量处理（支持一次拖入多个文件）。"""

    def __init__(self, worker, *, concurrency: int = 2) -> None:
        self.worker = worker
        self.concurrency = concurrency

    async def process_batch(self, paths: list[str]) -> list[dict]:
        """TODO(徐书和 + 胡希): 实现并发处理 + 进度回调。"""
        raise NotImplementedError("TODO: 批量处理实现")
