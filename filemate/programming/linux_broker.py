"""独立 root 服务的受限判题协议，不暴露 Docker socket 或通用执行接口。"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .linux_docker import DOCKER, JOBS, DockerCppJudge
from .problems import get_problem
from .windows_sandbox import SandboxUnavailable

REQUEST_LIMIT = 700000
_SLOT = threading.BoundedSemaphore(1)
_CLIENTS = threading.BoundedSemaphore(8)
_HEALTH_LOCK = threading.Lock()
_HEALTH: tuple[float, bool] = (0, False)
PROBE_CODE = '''#include <sys/socket.h>
#include <unistd.h>
#include <fstream>
#include <iostream>
int main(){std::ifstream secret("/opt/filemate/current/.env.production");
std::ofstream root("/etc/filemate-probe");
if(getuid()!=65534 || secret.good() || root.good() || socket(AF_INET,SOCK_STREAM,0)!=-1 || fork()!=-1)return 1;
std::cout<<"isolated";}'''


def validate_request(value: Any) -> dict[str, Any]:
    """只接受健康查询或已知题目代码，不接受路径、命令与自定义限制。"""
    if not isinstance(value, dict):
        raise TypeError("请求无效")
    if value == {"operation": "health"}:
        return value
    if set(value) != {"operation", "problem_id", "code"} or value["operation"] != "judge":
        raise ValueError("请求字段无效")
    code = value["code"]
    if not isinstance(code, str) or not code.strip() or "\x00" in code or len(code.encode("utf-8")) > 100000:
        raise ValueError("代码无效")
    if not isinstance(value["problem_id"], str):
        raise TypeError("题目无效")
    try:
        get_problem(value["problem_id"])
    except KeyError as exc:
        raise ValueError("题目不支持") from exc
    return value


def health(provider: DockerCppJudge, cancel: threading.Event) -> dict[str, Any]:
    """真实编译并验证身份、文件、网络与派生进程边界，缓存十分钟。"""
    global _HEALTH
    with _HEALTH_LOCK:
        if getattr(provider, "quarantined", False):
            _HEALTH = (time.monotonic(), False)
        if time.monotonic() - _HEALTH[0] >= 600:
            if not _SLOT.acquire(blocking=False):
                raise SandboxUnavailable("判题器正在使用")
            try:
                probe = {"tests": [{"name": "隔离自检", "input": "", "expected": "isolated"}],
                         "time_limit_ms": 1000, "memory_limit_mb": 256}
                try:
                    ready = provider.judge(PROBE_CODE, probe, cancel, lambda _: None)["verdict"] == "AC"
                except (SandboxUnavailable, OSError, subprocess.SubprocessError):
                    ready = False
                if cancel.is_set():
                    raise SandboxUnavailable("自检已取消")
            finally:
                _SLOT.release()
            _HEALTH = (time.monotonic(), ready)
        return {"ready": _HEALTH[1], "installed": True, "provider": "Linux gVisor / GCC C++17",
                "error": "" if _HEALTH[1] else "隔离自检未通过，评测已关闭", "languages": ["cpp17"],
                "max_concurrent": 1, "compile_limit_seconds": 30, "runtime_processes": 1,
                "network": False, "network_isolation_ready": _HEALTH[1], "setup_supported": False}


def serve_client(connection: socket.socket, provider: DockerCppJudge) -> None:
    """断开连接即取消容器，协议失败只返回通用错误。"""
    cancel = threading.Event()
    try:
        connection.settimeout(2)
        pending = bytearray()
        while b"\n" not in pending:
            chunk = connection.recv(65536)
            if not chunk:
                return
            pending.extend(chunk)
            if len(pending) > REQUEST_LIMIT:
                raise ValueError("请求过大")
        line, _, remaining = pending.partition(b"\n")
        request = validate_request(json.loads(line))
        connection.settimeout(None)
        def watch_cancel() -> None:
            buffer = bytearray(remaining)
            try:
                while True:
                    if b"\n" in buffer:
                        # 唯一后续指令是取消；其他输入也按取消处理。
                        cancel.set()
                        return
                    chunk = connection.recv(1024)
                    if not chunk:
                        cancel.set()
                        return
                    buffer.extend(chunk)
                    if len(buffer) > 1024:
                        cancel.set()
                        return
            except OSError:
                cancel.set()
        reader = threading.Thread(target=watch_cancel, daemon=True)
        reader.start()
        def send(value: dict[str, Any]) -> None:
            connection.sendall((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
        if request["operation"] == "health":
            send({"result": health(provider, cancel)})
        else:
            if not health(provider, cancel)["ready"]:
                raise SandboxUnavailable("隔离未就绪")
            if not _SLOT.acquire(blocking=False):
                raise SandboxUnavailable("代理容量已满")
            try:
                result = provider.judge(request["code"], get_problem(request["problem_id"]), cancel,
                                        lambda result: send({"progress": result}))
                send({"result": result})
            finally:
                _SLOT.release()
    except Exception as exc:  # noqa: BLE001 - 独立权限代理不得向客户端泄露运维异常。
        logging.getLogger(__name__).warning("判题代理请求未完成 (%s)", type(exc).__name__)
        try:
            connection.sendall(b'{"error":"sandbox_unavailable"}\n')
        except OSError:
            pass
    finally:
        cancel.set()
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        connection.close()
        _CLIENTS.release()


def main() -> None:
    """监听仅 root 与 FileMate 服务组可访问的 Unix socket。"""
    import grp

    if os.geteuid() != 0:
        raise SystemExit("判题代理必须由专用系统服务启动")
    cleanup_orphans()
    if sys.argv[1:] == ["--cleanup"]:
        return
    provider = DockerCppJudge(os.environ["FILEMATE_JUDGE_IMAGE"])
    address = Path(os.environ.get("FILEMATE_JUDGE_SOCKET", "/run/filemate-judge/judge.sock"))
    if address.parent != Path("/run/filemate-judge"):
        raise SystemExit("代理 socket 必须位于专用运行目录")
    address.parent.mkdir(mode=0o750, exist_ok=True)
    if address.exists():
        if not address.is_socket():
            raise SystemExit("代理地址已被非 socket 文件占用")
        address.unlink()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(address))
        os.chown(address, 0, grp.getgrnam("filemate").gr_gid)
        address.chmod(0o660)
        server.listen(8)
        while True:
            connection, _ = server.accept()
            if not _CLIENTS.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(target=serve_client, args=(connection, provider), daemon=True).start()


def cleanup_orphans() -> None:
    """只清理专用标签容器与已验证的专用临时目录。"""
    containers = subprocess.check_output([DOCKER, "ps", "--all", "--quiet", "--filter", "label=filemate.judge=1"],
                                         timeout=10).decode().split()
    if any(not re.fullmatch(r"[0-9a-f]{12,64}", identifier) for identifier in containers):
        raise SandboxUnavailable("容器清理清单无效")
    if containers:
        subprocess.run([DOCKER, "rm", "--force", *containers], check=True, timeout=30,
                       stdout=subprocess.DEVNULL)
    if JOBS.exists():
        if JOBS.is_symlink() or JOBS.resolve() != JOBS or JOBS.stat().st_uid != 0:
            raise SandboxUnavailable("临时目录边界无效")
        for directory in JOBS.iterdir():
            if (directory.is_symlink() or not directory.is_dir() or directory.parent != JOBS
                    or not re.fullmatch(r"job-[a-z0-9_]+", directory.name) or directory.stat().st_uid != 0):
                raise SandboxUnavailable("临时工作目录无效")
            if subprocess.run(["/usr/bin/mountpoint", "--quiet", str(directory)], check=False).returncode == 0:
                subprocess.run(["/usr/bin/umount", str(directory)], check=True, timeout=10)
            if not directory.resolve().is_relative_to(JOBS):
                raise SandboxUnavailable("临时工作目录超出边界")
            shutil.rmtree(directory)


if __name__ == "__main__":
    main()
