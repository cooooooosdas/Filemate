"""仅供独立代理使用的 gVisor 编译与执行适配器。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .judge import normalized_output
from .windows_sandbox import ProcessResult, SandboxUnavailable

DOCKER = "/usr/bin/docker"
RUNTIME = "filemate-runsc"
OUTPUT_LIMIT = 65536
JOBS = Path("/var/lib/filemate-judge/runs")


def command(arguments: list[str], *, timeout: float = 10) -> str:
    """执行固定运维命令，不经 shell。"""
    return subprocess.check_output(arguments, timeout=timeout, stderr=subprocess.DEVNULL).decode("utf-8")


def container_arguments(image: str, name: str, directory: Path, *, compile_code: bool,
                        time_ms: int = 1000, memory_mb: int = 256) -> list[str]:
    """构造固定隔离策略，禁止客户端自定义任何容器参数。"""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise SandboxUnavailable("判题镜像必须固定为本地内容摘要")
    memory = 384 if compile_code else memory_mb
    mount = (f"type=bind,src={directory},dst=/workspace" if compile_code else
             f"type=bind,src={directory / 'main'},dst=/program,readonly")
    arguments = [DOCKER, "create", "--name", name, "--runtime", RUNTIME, "--pull=never",
                 "--label=filemate.judge=1",
                 "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                 "--user=65534:65534", f"--memory={memory}m", f"--memory-swap={memory}m",
                 "--cpus=1", "--pids-limit=64", "--ulimit=nofile=64:64",
                 "--ulimit=core=0:0", "--ulimit=fsize=8388608:8388608", "--log-driver=none",
                 "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777", "--mount", mount,
                 "--workdir", "/workspace" if compile_code else "/tmp", "--interactive", image]
    return arguments + (["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-fdiagnostics-color=never",
                         "main.cpp", "-o", "main"] if compile_code else
                        ["/usr/local/bin/filemate-runner", str(time_ms), str(memory_mb)])


class DockerCppJudge:
    """必须使用 gVisor，无原生 Docker 或宿主执行回退。"""

    def __init__(self, image: str) -> None:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise SandboxUnavailable("判题镜像摘要无效")
        self.image = image
        self.quarantined = False

    def _run(self, directory: Path, *, compile_code: bool, cancel: threading.Event,
             stdin: str = "", time_ms: int = 1000, memory_mb: int = 256) -> ProcessResult:
        name = "filemate-judge-" + uuid.uuid4().hex
        process = None
        try:
            command(container_arguments(self.image, name, directory, compile_code=compile_code,
                                        time_ms=time_ms, memory_mb=memory_mb))
            info = json.loads(command([DOCKER, "inspect", name]))[0]
            host = info["HostConfig"]
            if (host["Runtime"] != RUNTIME or host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]
                    or host["CapDrop"] != ["ALL"] or info["Image"] != self.image
                    or host["Memory"] != (384 if compile_code else memory_mb) * 1024 * 1024
                    or host["MemorySwap"] != host["Memory"] or host["NanoCpus"] != 1000000000):
                raise SandboxUnavailable("容器隔离配置未生效")
            started = time.monotonic()
            process = subprocess.Popen([DOCKER, "start", "--attach", "--interactive", name],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            def provide_input() -> None:
                try:
                    process.stdin.write(stdin.encode("utf-8"))
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            writer = threading.Thread(target=provide_input, daemon=True)
            writer.start()
            stdout, stderr, reason = bytearray(), bytearray(), ""
            deadline = started + (30 if compile_code else time_ms / 1000 + 8)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, stdout)
                selector.register(process.stderr, selectors.EVENT_READ, stderr)
                while selector.get_map():
                    if cancel.is_set():
                        reason = "cancelled"
                        break
                    if time.monotonic() >= deadline:
                        reason = "timeout" if compile_code else "sandbox_timeout"
                        break
                    for key, _ in selector.select(.02):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        remaining = OUTPUT_LIMIT - len(stdout) - len(stderr)
                        key.data.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            reason = "output_limit"
                            break
                    if reason:
                        break
            if reason:
                # 删除也覆盖尚未完成启动的容器，避免取消与 start 之间的竞争。
                subprocess.run([DOCKER, "rm", "--force", name], timeout=10, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if process.poll() is None:
                    process.kill()
            process.wait(timeout=10)
            writer.join(timeout=1)
            if reason:
                return ProcessResult(-1, stdout.decode("utf-8", errors="replace"),
                                     stderr.decode("utf-8", errors="replace"),
                                     round((time.monotonic() - started) * 1000), 0, reason)
            state = json.loads(command([DOCKER, "inspect", name]))[0]["State"]
            text = stderr.decode("utf-8", errors="replace")
            elapsed = round((time.monotonic() - started) * 1000)
            peak = 0
            exit_code = state["ExitCode"]
            if not compile_code and not reason:
                match = re.search(r'\nFILEMATE_RESULT=(\{[^\n]+\})\n$', text)
                if state["OOMKilled"]:
                    reason = "memory_limit"
                elif match:
                    evidence = json.loads(match[1])
                    exit_code, elapsed, peak, reason = (evidence[key] for key in
                                                        ("exit_code", "elapsed_ms", "peak_memory_bytes", "reason"))
                    text = text[:match.start()]
                else:
                    raise SandboxUnavailable("隔离运行器未返回有效证据")
            if state["Error"] or reason in {"sandbox_timeout", "sandbox_error"}:
                raise SandboxUnavailable("隔离执行器启动或运行失败")
            return ProcessResult(exit_code, stdout.decode("utf-8", errors="replace"), text, elapsed, peak, reason)
        finally:
            cleaned = subprocess.run([DOCKER, "rm", "--force", name], timeout=10, check=False,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            if cleaned.returncode and subprocess.run([DOCKER, "inspect", name], timeout=10, check=False,
                                                      stdout=subprocess.DEVNULL,
                                                      stderr=subprocess.DEVNULL).returncode == 0:
                self.quarantined = True
                raise SandboxUnavailable("评测容器未能清理，服务停止接收新任务")

    def judge(self, code: str, problem: dict[str, Any], cancel: threading.Event,
              progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """临时文件有总容量上限，每个测试点使用独立运行容器。"""
        if self.quarantined:
            raise SandboxUnavailable("隔离服务需要管理员检查后重启")
        JOBS.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="job-", dir=JOBS) as temporary:
            directory = Path(temporary)
            command(["/usr/bin/mount", "-t", "tmpfs", "-o", "size=67108864,nosuid,nodev,mode=0777",
                     "filemate-judge", str(directory)])
            try:
                (directory / "main.cpp").write_text(code, encoding="utf-8")
                (directory / "main.cpp").chmod(0o644)
                compiled = self._run(directory, compile_code=True, cancel=cancel)
                result: dict[str, Any] = {
                    "verdict": "RUNNING", "passed": 0, "total": len(problem["tests"]), "score": 0,
                    "compile_log": compiled.stdout + compiled.stderr, "compile_ms": compiled.elapsed_ms,
                    "tests": [], "provider": "linux-gvisor-gcc", "language": "cpp17",
                    "limits": {"time_ms": problem["time_limit_ms"], "memory_mb": problem["memory_limit_mb"],
                               "processes": 1, "network": False, "output_bytes": OUTPUT_LIMIT,
                               "file_write_bytes": 16 * 1024 * 1024},
                }
                if compiled.reason == "cancelled":
                    result["verdict"] = "CANCELLED"
                    return result
                if compiled.exit_code or compiled.reason:
                    result.update(verdict="CE", compile_reason=compiled.reason or "compiler_error")
                    return result
                binary = directory / "main"
                if binary.is_symlink() or not binary.is_file() or binary.stat().st_size > 8 * 1024 * 1024:
                    raise SandboxUnavailable("编译产物无效")
                with binary.open("rb") as stream:
                    if stream.read(4) != b"\x7fELF":
                        raise SandboxUnavailable("编译产物不是可执行格式")
                progress(result)
                for index, test in enumerate(problem["tests"]):
                    if cancel.is_set():
                        result["verdict"] = "CANCELLED"
                        return result
                    current = directory / str(index)
                    current.mkdir(mode=0o755)
                    shutil.copyfile(binary, current / "main")
                    (current / "main").chmod(0o555)
                    execution = self._run(current, compile_code=False, cancel=cancel, stdin=test["input"],
                                          time_ms=problem["time_limit_ms"], memory_mb=problem["memory_limit_mb"])
                    if execution.reason == "cancelled":
                        result["verdict"] = "CANCELLED"
                        return result
                    verdict = ("TLE" if execution.reason == "timeout" else
                               "RE" if execution.exit_code or execution.reason else
                               "AC" if normalized_output(execution.stdout) == normalized_output(test["expected"])
                               else "WA")
                    result["tests"].append({"index": index, "name": test["name"], "verdict": verdict,
                                            "input": test["input"][:4096], "input_truncated": len(test["input"]) > 4096,
                                            "input_sha256": hashlib.sha256(test["input"].encode()).hexdigest(),
                                            "expected": test["expected"], "actual": execution.stdout,
                                            "stderr": execution.stderr, "elapsed_ms": execution.elapsed_ms,
                                            "peak_memory_bytes": execution.peak_memory_bytes,
                                            "exit_code": execution.exit_code, "reason": execution.reason})
                    result["passed"] = sum(item["verdict"] == "AC" for item in result["tests"])
                    result["score"] = round(100 * result["passed"] / result["total"], 1)
                    progress(result)
                result["verdict"] = next((item["verdict"] for item in result["tests"] if item["verdict"] != "AC"), "AC")
                return result
            finally:
                try:
                    command(["/usr/bin/umount", str(directory)])
                except (OSError, subprocess.SubprocessError):
                    self.quarantined = True
                    raise
