"""watchdog 目录监控。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable


class FileWatcher:
    """监控指定目录，新文件到达时触发回调。"""

    def __init__(self, watch_dir: str | Path, *, poll_interval: float = 2.0) -> None:
        self.watch_dir = Path(watch_dir)
        self.poll_interval = poll_interval
        self._callback: Callable[[Path], None] | None = None
        self._seen: set[str] = set()

    def on_new_file(self, callback: Callable[[Path], None]) -> None:
        """注册新文件回调，参数为新文件 Path。"""
        self._callback = callback

    async def run(self) -> None:
        """TODO(汤新阳): 使用 watchdog 或轮询实现监控循环。"""
        raise NotImplementedError("TODO(汤新阳): watcher 实现")
