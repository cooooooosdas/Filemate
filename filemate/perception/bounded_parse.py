"""Run untrusted document decoders outside the API process with resource budgets."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import psutil

MEMORY_BYTES = 384 * 1024 * 1024
WALL_SECONDS = 40
OUTPUT_BYTES = 8 * 1024 * 1024
_SLOT = threading.BoundedSemaphore(1)


def _stop(process: subprocess.Popen) -> None:
    """Kill and reap the private decoder group, including optional OCR children."""
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        try:
            children = psutil.Process(process.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            process.kill()
    process.wait(timeout=5)


def parse_bounded(path: Path, *, enriched: bool = False) -> dict:
    """Decode one document, returning the existing error contract on exhaustion."""
    from .file_parser import FileParser

    error = lambda message: FileParser._error(path, message)
    if not _SLOT.acquire(blocking=False):
        return error('资料解析正在进行，请稍后再试')
    try:
        # Model credentials and tenant context are deliberately absent from the decoder.
        env = {key: os.environ[key] for key in
               ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL') if key in os.environ}
        env.update(PYTHONUTF8='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
        worker = Path(__file__).with_name('parse_worker.py')
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                [sys.executable, '-I', str(worker)], stdin=subprocess.PIPE,
                stdout=output, stderr=subprocess.DEVNULL, env=env,
                start_new_session=os.name == 'posix',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            try:
                process.stdin.write(json.dumps({'path': str(path.resolve()),
                                                'enriched': enriched}).encode('utf-8'))
                process.stdin.close()
                deadline = time.monotonic() + WALL_SECONDS
                tracked = psutil.Process(process.pid)
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        return error('资料解析超时，请拆分文件后重试')
                    if os.fstat(output.fileno()).st_size > OUTPUT_BYTES:
                        return error('资料解析结果过大，请拆分文件后重试')
                    try:
                        rss = sum(p.memory_info().rss for p in
                                  [tracked, *tracked.children(recursive=True)] if p.is_running())
                    except psutil.NoSuchProcess:
                        rss = 0
                    if rss > MEMORY_BYTES:
                        return error('资料解析超过内存上限，请拆分文件后重试')
                    time.sleep(0.05)
                if process.returncode != 0:
                    return error('资料解析失败或超过资源上限，请拆分文件后重试')
                output.seek(0)
                raw = output.read(OUTPUT_BYTES + 1)
                if len(raw) > OUTPUT_BYTES:
                    return error('资料解析结果过大，请拆分文件后重试')
                result = json.loads(raw)
                if not isinstance(result, dict) or not isinstance(result.get('raw_text'), str):
                    return error('资料解析结果无效')
                return result
            finally:
                _stop(process)
    except (OSError, ValueError, psutil.Error):
        return error('资料解析服务暂不可用，请稍后重试')
    finally:
        _SLOT.release()
