"""评测容量、取消信号与启动自检。"""

from __future__ import annotations

import threading
import time
from typing import Any

from .judge import WindowsCppJudge
from .repository import CodingRepository
from .toolchain import discover_msvc, toolchain_root
from .windows_sandbox import SandboxUnavailable, network_isolation_available

_LOCK = threading.RLock()
_HEALTH_LOCK = threading.Lock()
_SLOTS = threading.BoundedSemaphore(2)
_RUNNING: dict[tuple[str, str], threading.Event] = {}
_HEALTH: dict[str, tuple[float, bool]] = {}


def status(*, force: bool = False) -> dict[str, Any]:
    """报告依赖与真实自检结果，不把工具链文件存在当作隔离成功。"""
    root = toolchain_root()
    installed = False
    try:
        discover_msvc()
        installed = True
    except SandboxUnavailable:
        pass
    provider = WindowsCppJudge(root)
    ready = False
    error = "请先准备本地隔离评测环境" if installed else "需要 Windows 与 MSVC x64/Windows SDK"
    network_ready = network_isolation_available()
    if provider.ready() and network_ready:
        with _HEALTH_LOCK:
            cached = _HEALTH.get(str(root))
            if not force and cached and time.monotonic() - cached[0] < 600:
                ready = cached[1]
            else:
                code = ('#include <windows.h>\n#include <iostream>\n#pragma comment(lib,"advapi32.lib")\n'
                        'int main(){HANDLE t;DWORD b=0,n=0;'
                        'if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&t))return 2;'
                        'if(!GetTokenInformation(t,TokenIsAppContainer,&b,sizeof(b),&n))return 3;'
                        'CloseHandle(t);std::cout<<b;return 0;}')
                probe = {"tests": [{"name": "身份自检", "input": "", "expected": "1"}],
                         "time_limit_ms": 1000, "memory_limit_mb": 256}
                try:
                    ready = provider.judge(code, probe, threading.Event(), lambda _: None)["verdict"] == "AC"
                except (SandboxUnavailable, OSError):
                    ready = False
                _HEALTH[str(root)] = (time.monotonic(), ready)
        if not ready:
            error = "隔离执行自检未通过，提交已关闭。请检查目录权限与 C++ 开发组件后重试。"
    elif provider.ready():
        error = "Windows 防火墙隔离服务未就绪，提交已关闭。"
    return {"ready": ready, "installed": installed, "provider": "Windows AppContainer + LPAC / MSVC C++17",
            "error": "" if ready else error, "languages": ["cpp17"], "max_concurrent": 2,
            "compile_limit_seconds": 30, "runtime_processes": 1, "network": False,
            "network_isolation_ready": network_ready}


def execute(repository: CodingRepository, identifier: str) -> dict[str, Any]:
    """容量不足时保留 queued 提交，取消始终优先于迟到结果。"""
    from .feedback import local_feedback
    from .problems import get_problem

    key = (str(repository.storage.db_path), identifier)
    with _LOCK:
        existing = repository.get(identifier)
        if key in _RUNNING or existing["status"] != "queued":
            return existing
        if not _SLOTS.acquire(blocking=False):
            raise ValueError("评测队列已满，请稍后点击继续评测，已保存的代码不会丢失")
        cancel = threading.Event()
        _RUNNING[key] = cancel
    try:
        submission, claimed = repository.start(identifier)
        if not claimed:
            return submission
        result = WindowsCppJudge().judge(
            submission["code"], get_problem(submission["problem_id"]), cancel,
            lambda evidence: repository.update(identifier, payload={"result": evidence}),
        )
        state = "cancelled" if result["verdict"] == "CANCELLED" else "completed"
        submission["result"] = result
        return repository.update(identifier, status=state,
                                 payload={"result": result, "local_feedback": local_feedback(submission)},
                                 event=state)
    except Exception as exc:
        repository.update(identifier, status="failed", payload={"result": {
            "verdict": "SYSTEM_ERROR", "error": "隔离评测未完成，请检查环境后用原代码新建提交重试",
            "error_code": type(exc).__name__,
        }}, event="failed")
        raise SandboxUnavailable("隔离评测失败，原始代码与历史记录已保留") from exc
    finally:
        with _LOCK:
            _RUNNING.pop(key, None)
        _SLOTS.release()


def cancel(repository: CodingRepository, identifier: str) -> dict[str, Any]:
    """先提交取消状态，再通知仍在运行的 Job。"""
    with _LOCK:
        result = repository.transition(identifier, "cancel")
        signal = _RUNNING.get((str(repository.storage.db_path), identifier))
        if signal:
            signal.set()
        return result


def recover(repository: CodingRepository) -> None:
    """恢复页面时标出前次服务中断的运行记录。"""
    with _LOCK:
        live = {identifier for (database, identifier) in _RUNNING
                if database == str(repository.storage.db_path)}
        repository.interrupt_orphans(live)
