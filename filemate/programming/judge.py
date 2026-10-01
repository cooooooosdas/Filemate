"""真实编译与逐点执行，模型不能参与正确性裁决。"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .toolchain import compiler_environment, toolchain_root
from .windows_sandbox import SandboxUnavailable, run_isolated


class JudgeProvider(Protocol):
    """可替换的语言与沙箱适配接口。"""

    def judge(self, code: str, problem: dict[str, Any], cancel: threading.Event,
              progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]: ...


def normalized_output(value: str) -> str:
    """允许末尾空行与行末空白，不忽略答案中间的字符或空格。"""
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").split("\n")).rstrip()


class WindowsCppJudge:
    """编译使用无网络 AppContainer，提交程序使用更严格的 LPAC。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or toolchain_root()

    def _compile(self, code: str, directory: Path, cancel: threading.Event):
        (directory / "main.cpp").write_text(code, encoding="utf-8", newline="")
        return run_isolated(
            self.root / "bin/cl.exe",
            ["/nologo", "/std:c++17", "/EHsc", "/MT", "/O2", "/utf-8",
             "/diagnostics:column", "main.cpp", "/Fe:main.exe", "/Fo:main.obj"],
            directory, environment=compiler_environment(self.root, directory),
            timeout=30, memory_mb=768, processes=8, output_limit=65536, cancel=cancel,
            least_privileged=False,
            output_fallback_encoding="mbcs",
        )

    def ready(self) -> bool:
        """缺少任何组件时禁止执行，不退回宿主进程。"""
        return os.name == "nt" and all((self.root / name).is_file() for name in
                                      ("ready.txt", "bin/cl.exe", "bin/c1xx.dll", "bin/link.exe"))

    def judge(self, code: str, problem: dict[str, Any], cancel: threading.Event,
              progress: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        """输出编译证据、各测试点证据与实际通过比例。"""
        if not self.ready():
            raise SandboxUnavailable("隔离工具链尚未就绪，请先准备本地评测环境")
        base = self.root.parent / "cpp-runs"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="compile-", dir=base) as temporary:
            directory = Path(temporary)
            compiled = self._compile(code, directory, cancel)
            compile_log = (compiled.stdout + compiled.stderr).replace(str(directory), "[沙箱]")
            result: dict[str, Any] = {
                "verdict": "RUNNING", "passed": 0, "total": len(problem["tests"]), "score": 0,
                "compile_log": compile_log, "compile_ms": compiled.elapsed_ms, "tests": [],
                "provider": "windows-appcontainer-msvc", "language": "cpp17",
                "limits": {"time_ms": problem["time_limit_ms"], "memory_mb": problem["memory_limit_mb"],
                           "processes": 1, "network": False, "output_bytes": 65536,
                           "file_write_bytes": 16 * 1024 * 1024},
            }
            if compiled.reason == "cancelled":
                result["verdict"] = "CANCELLED"
                return result
            if compiled.exit_code or compiled.reason or not (directory / "main.exe").is_file():
                # 基础设施启动失败不能误报学生语法错误。
                if compiled.exit_code in {0xC0000135, 0xC0000142, 126}:
                    raise SandboxUnavailable("编译器未能在隔离环境中启动")
                result.update(verdict="CE", compile_reason=compiled.reason or "compiler_error")
                return result
            progress(result)
            for index, test in enumerate(problem["tests"]):
                if cancel.is_set():
                    result["verdict"] = "CANCELLED"
                    return result
                # 每个测试点使用独立目录与身份，阻止跨测试点遗留文件影响结果。
                with tempfile.TemporaryDirectory(prefix="run-", dir=base) as run_dir:
                    current = Path(run_dir)
                    shutil.copyfile(directory / "main.exe", current / "main.exe")
                    execution = run_isolated(
                        current / "main.exe", [], current,
                        environment={"SystemRoot": os.environ.get("SystemRoot", "C:/Windows"),
                                     "TEMP": str(current), "TMP": str(current)},
                        stdin=test["input"], timeout=problem["time_limit_ms"] / 1000,
                        memory_mb=problem["memory_limit_mb"], cancel=cancel,
                    )
                if execution.reason == "cancelled":
                    result["verdict"] = "CANCELLED"
                    return result
                verdict = ("TLE" if execution.reason == "timeout" else
                           "RE" if execution.exit_code or execution.reason else
                           "AC" if normalized_output(execution.stdout) == normalized_output(test["expected"])
                           else "WA")
                result["tests"].append({
                    "index": index, "name": test["name"], "verdict": verdict,
                    "input": test["input"][:4096], "input_truncated": len(test["input"]) > 4096,
                    "input_sha256": hashlib.sha256(test["input"].encode()).hexdigest(),
                    "expected": test["expected"], "actual": execution.stdout,
                    "stderr": execution.stderr, "elapsed_ms": execution.elapsed_ms,
                    "peak_memory_bytes": execution.peak_memory_bytes,
                    "exit_code": execution.exit_code, "reason": execution.reason,
                })
                result["passed"] = sum(t["verdict"] == "AC" for t in result["tests"])
                result["score"] = round(100 * result["passed"] / result["total"], 1)
                progress(result)
            result["verdict"] = next((t["verdict"] for t in result["tests"] if t["verdict"] != "AC"), "AC")
            return result
