"""批量处理器测试。TODO(徐书和)"""
from __future__ import annotations

import asyncio
import time

import pytest

from filemate.execution.batch_processor import BatchProcessor


async def _fake_worker(path: str) -> dict:
    """模拟一个异步 worker（可注入延迟和失败）。"""
    # path 格式: "ok" / "slow" / "fail"
    if path == "fail":
        raise RuntimeError(f"处理失败: {path}")
    if path == "slow":
        await asyncio.sleep(0.1)
    return {"path": path, "success": True}


@pytest.fixture()
def processor() -> BatchProcessor:
    return BatchProcessor(_fake_worker, concurrency=2)


@pytest.mark.asyncio
class TestBatchProcessor:
    async def test_empty_list(self, processor: BatchProcessor) -> None:
        results = await processor.process_batch([])
        assert results == []

    async def test_single_file(self, processor: BatchProcessor) -> None:
        results = await processor.process_batch(["ok"])
        assert len(results) == 1
        assert results[0]["success"] is True

    async def test_error_isolation(self, processor: BatchProcessor) -> None:
        """单个文件失败不应影响其他文件的结果。"""
        paths = ["ok", "fail", "ok"]
        results = await processor.process_batch(paths)
        assert len(results) == 3
        # 第一个 ok 成功
        assert results[0].get("success") is True
        # 失败的不抛异常，而是返回错误信息
        assert results[1].get("success") is False
        assert "error" in results[1]
        # 第三个 ok 也成功
        assert results[2].get("success") is True

    async def test_progress_callback(self, processor: BatchProcessor) -> None:
        progress: list[tuple] = []

        def on_progress(done: int, total: int, path: str) -> None:
            progress.append((done, total, path))

        await processor.process_batch(["ok", "ok", "ok"], on_progress=on_progress)
        assert len(progress) == 3
        # 最后一次回调 done==total
        assert progress[-1] == (3, 3, "ok")

    async def test_concurrency_limit(self, tmp_path: Path) -> None:
        """验证信号量限制确实控制了并发度。"""
        running = 0
        max_running = 0
        lock = asyncio.Lock()

        async def tracking_worker(path: str) -> dict:
            nonlocal running, max_running
            async with lock:
                running += 1
                max_running = max(max_running, running)
            await asyncio.sleep(0.05)
            async with lock:
                running -= 1
            return {"path": path}

        bp = BatchProcessor(tracking_worker, concurrency=1)
        # 同时提交 5 个，但并发限制为 1
        await bp.process_batch(["a", "b", "c", "d", "e"])
        assert max_running == 1

    async def test_results_order_preserved(self, processor: BatchProcessor) -> None:
        """结果顺序应与输入顺序一致。"""
        paths = ["slow", "ok", "ok"]
        results = await processor.process_batch(paths)
        assert [r["path"] for r in results] == paths
