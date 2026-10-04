"""Linux 判题客户端，只通过受限 Unix socket 请求隔离代理。"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .windows_sandbox import SandboxUnavailable

MAX_MESSAGE_BYTES = 2 * 1024 * 1024


def broker_socket() -> Path:
    """返回部署配置中的代理 socket。"""
    return Path(os.environ.get("FILEMATE_JUDGE_SOCKET", "/run/filemate-judge/judge.sock"))


class LinuxCppJudge:
    """Web 进程不持有 Docker 权限，也不能传递命令、镜像或宿主路径。"""

    def _request(self, request: dict[str, Any], cancel: threading.Event,
                 progress: Callable[[dict[str, Any]], None], timeout: float) -> dict[str, Any]:
        if not hasattr(socket, "AF_UNIX"):
            raise SandboxUnavailable("当前系统不支持 Linux 隔离代理")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(str(broker_socket()))
                connection.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
                connection.settimeout(.2)
                pending = bytearray()
                deadline = time.monotonic() + timeout
                cancelled = False
                while time.monotonic() < deadline:
                    if cancel.is_set() and not cancelled:
                        connection.sendall(b'{"cancel":true}\n')
                        cancelled = True
                    try:
                        chunk = connection.recv(65536)
                    except TimeoutError:
                        continue
                    if not chunk:
                        raise SandboxUnavailable("隔离代理连接中断")
                    pending.extend(chunk)
                    if len(pending) > MAX_MESSAGE_BYTES:
                        raise SandboxUnavailable("隔离代理响应超出上限")
                    while b"\n" in pending:
                        line, _, remainder = pending.partition(b"\n")
                        pending = bytearray(remainder)
                        message = json.loads(line)
                        if message.get("error"):
                            raise SandboxUnavailable("隔离代理未能完成评测")
                        if "progress" in message:
                            progress(message["progress"])
                        elif "result" in message:
                            return message["result"]
                raise SandboxUnavailable("隔离代理响应超时")
        except (OSError, ValueError, TypeError) as exc:
            raise SandboxUnavailable("Linux 隔离代理不可用") from exc

    def health(self) -> dict[str, Any]:
        """查询代理最近一次真实自检。"""
        return self._request({"operation": "health"}, threading.Event(), lambda _: None, 45)

    def judge(self, code: str, problem: dict[str, Any], cancel: threading.Event,
              progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """代理仅接受题目ID，测试点与资源限制由代理的受信任题库确定。"""
        return self._request({"operation": "judge", "problem_id": problem["id"], "code": code},
                             cancel, progress, 120)
