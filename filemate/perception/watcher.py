"""watchdog 目录监控（轮询实现，跨平台兼容）。"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# 默认监控的文件后缀
_DEFAULT_EXTENSIONS = {
    "pdf", "docx", "doc", "pptx", "ppt",
    "txt", "md", "png", "jpg", "jpeg", "bmp",
}


class FileWatcher:
    """监控指定目录，新文件到达时触发回调。

    实现：轮询（poll）+ 已见集合去重。跨平台，无 watchdog 依赖。

    用法::

        watcher = FileWatcher("C:\\Downloads\\CourseFiles")

        def on_new(path: Path):
            print(f"新文件: {path.name}")

        watcher.on_new_file(on_new)
        asyncio.run(watcher.run())   # 阻塞直到 stop()
    """

    def __init__(
        self,
        watch_dir: str | Path,
        *,
        poll_interval: float = 2.0,
        extensions: set[str] | None = None,
        recursive: bool = False,
    ) -> None:
        self.watch_dir = Path(watch_dir).expanduser().resolve()
        self.poll_interval = poll_interval
        self.extensions = extensions or _DEFAULT_EXTENSIONS
        self.recursive = recursive
        self._callback: Callable[[Path], None] | None = None
        self._seen: set[str] = set()
        self._running = False
        self._init_seen()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def on_new_file(self, callback: Callable[[Path], None]) -> None:
        """注册新文件回调（同步函数即可）。"""
        self._callback = callback

    async def run(self) -> None:
        """启动监控循环（阻塞）。"""
        self._running = True
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "FileWatcher 启动: %s (extensions=%s, interval=%.1fs)",
            self.watch_dir,
            sorted(self.extensions),
            self.poll_interval,
        )
        while self._running:
            try:
                self._scan()
            except Exception:
                logger.exception("扫描目录失败: %s", self.watch_dir)
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        """请求停止（下一轮循环退出）。"""
        self._running = False

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _init_seen(self) -> None:
        """把已有文件都标记为已见，避免启动时触发大量回调。"""
        try:
            it = self.watch_dir.rglob("*") if self.recursive else self.watch_dir.iterdir()
            for p in it:
                if p.is_file():
                    self._seen.add(str(p.resolve())
                                   )
        except OSError:
            pass

    def _scan(self) -> None:
        """扫描一次，对新文件触发回调。"""
        it = self.watch_dir.rglob("*") if self.recursive else self.watch_dir.iterdir()
        for p in it:
            if not p.is_file():
                continue
            suffix = p.suffix.lstrip(".").lower()
            if suffix not in self.extensions:
                continue
            resolved = str(p.resolve())
            if resolved in self._seen:
                continue
            self._seen.add(resolved)
            logger.debug("新文件: %s", p.name)
            if self._callback:
                try:
                    result = self._callback(p)
                    if asyncio.iscoroutine(result):
                        asyncio.get_event_loop().run_until_complete(result)
                except Exception:
                    logger.exception("回调执行失败: %s", p)
