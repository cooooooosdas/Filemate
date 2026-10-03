"""Windows LPAC 与 Job Object 隔离执行器。"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
import uuid
from ctypes import wintypes as w
from dataclasses import dataclass
from pathlib import Path

_CREATE_PROCESS_LOCK = threading.Lock()


def _create_process_without_error_dialog(kernel, *arguments) -> bool:
    """让子进程继承无崩溃报告模式，并恢复宿主原有错误模式。"""
    # WER 会在提交崩溃后继续占用可执行文件，导致 RE 被目录清理错误覆盖。
    with _CREATE_PROCESS_LOCK:
        previous = kernel.GetErrorMode()
        kernel.SetErrorMode(previous | 0x0001 | 0x0002)
        try:
            return bool(kernel.CreateProcessW(*arguments))
        finally:
            kernel.SetErrorMode(previous)


class SandboxUnavailable(RuntimeError):
    """隔离设施无法完整建立。"""


@dataclass(frozen=True)
class ProcessResult:
    """有界的进程执行证据。"""

    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: int
    peak_memory_bytes: int
    reason: str = ""


def decode_output(data: bytes | bytearray, fallback_encoding: str | None = None) -> str:
    """优先读取 UTF-8，仅为受信任编译器启用系统代码页回退。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(fallback_encoding or "utf-8", errors="replace")


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", w.DWORD), ("descriptor", w.LPVOID), ("inherit", w.BOOL)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
        ("title", w.LPWSTR), ("x", w.DWORD), ("y", w.DWORD),
        ("xsize", w.DWORD), ("ysize", w.DWORD), ("charsx", w.DWORD),
        ("charsy", w.DWORD), ("fill", w.DWORD), ("flags", w.DWORD),
        ("show", w.WORD), ("reserved2size", w.WORD), ("reserved2", w.LPVOID),
        ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", w.LPVOID)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE),
               ("pid", w.DWORD), ("tid", w.DWORD)]


class _Capabilities(ctypes.Structure):
    _fields_ = [("sid", w.LPVOID), ("capabilities", w.LPVOID),
               ("count", w.DWORD), ("reserved", w.DWORD)]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", w.DWORD), ("min_working", ctypes.c_size_t),
        ("max_working", ctypes.c_size_t), ("active_processes", w.DWORD),
        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
               ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", _BasicLimits), ("io", _IoCounters),
               ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
               ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in
               ("user_time", "kernel_time", "period_user_time", "period_kernel_time")] + [
        (name, w.DWORD) for name in ("faults", "total_processes", "active_processes", "terminated_processes")
    ]


class _IoAccounting(ctypes.Structure):
    _fields_ = [("basic", _Accounting), ("io", _IoCounters)]


class _ServiceStatus(ctypes.Structure):
    _fields_ = [(name, w.DWORD) for name in
               ("kind", "state", "controls", "exit_code", "specific_exit", "checkpoint", "wait_hint")]


def _api():
    """声明 Win32 参数宽度以避免 64 位句柄截断。"""
    if os.name != "nt":
        raise SandboxUnavailable("当前平台需要配置受支持的隔离执行器")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    userenv = ctypes.WinDLL("userenv", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([w.LPVOID, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
        "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID], w.BOOL),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "ResumeThread": ([w.HANDLE], w.DWORD),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetExitCodeProcess": ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        "GetErrorMode": ([], w.UINT),
        "SetErrorMode": ([w.UINT], w.UINT),
        "InitializeProcThreadAttributeList": ([w.LPVOID, w.DWORD, w.DWORD,
                                               ctypes.POINTER(ctypes.c_size_t)], w.BOOL),
        "UpdateProcThreadAttribute": ([w.LPVOID, w.DWORD, ctypes.c_size_t,
                                       w.LPVOID, ctypes.c_size_t, w.LPVOID, w.LPVOID], w.BOOL),
        "DeleteProcThreadAttributeList": ([w.LPVOID], None),
        "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, w.LPVOID, w.LPVOID, w.BOOL, w.DWORD,
                            w.LPVOID, w.LPCWSTR, w.LPVOID, w.LPVOID], w.BOOL),
        "LocalFree": ([w.LPVOID], w.LPVOID),
    }
    for name, (args, result) in signatures.items():
        getattr(kernel, name).argtypes = args
        getattr(kernel, name).restype = result
    userenv.CreateAppContainerProfile.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR,
                                                  w.LPVOID, w.DWORD, ctypes.POINTER(w.LPVOID)]
    userenv.CreateAppContainerProfile.restype = ctypes.c_long
    userenv.DeleteAppContainerProfile.argtypes = [w.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = ctypes.c_long
    advapi.ConvertSidToStringSidW.argtypes = [w.LPVOID, ctypes.POINTER(w.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = w.BOOL
    advapi.FreeSid.argtypes = [w.LPVOID]
    advapi.FreeSid.restype = w.LPVOID
    advapi.OpenSCManagerW.argtypes = [w.LPCWSTR, w.LPCWSTR, w.DWORD]
    advapi.OpenSCManagerW.restype = w.HANDLE
    advapi.OpenServiceW.argtypes = [w.HANDLE, w.LPCWSTR, w.DWORD]
    advapi.OpenServiceW.restype = w.HANDLE
    advapi.QueryServiceStatus.argtypes = [w.HANDLE, ctypes.POINTER(_ServiceStatus)]
    advapi.QueryServiceStatus.restype = w.BOOL
    advapi.CloseServiceHandle.argtypes = [w.HANDLE]
    advapi.CloseServiceHandle.restype = w.BOOL
    return kernel, userenv, advapi


def network_isolation_available() -> bool:
    """Windows 防火墙与过滤服务未运行时拒绝评测，不自动改变系统服务。"""
    if os.name != "nt":
        return False
    _, _, advapi = _api()
    manager = advapi.OpenSCManagerW(None, None, 1)
    if not manager:
        return False
    try:
        for name in ("BFE", "MpsSvc"):
            handle = advapi.OpenServiceW(manager, name, 4)
            if not handle:
                return False
            try:
                state = _ServiceStatus()
                if not advapi.QueryServiceStatus(handle, ctypes.byref(state)) or state.state != 4:
                    return False
            finally:
                advapi.CloseServiceHandle(handle)
        return True
    finally:
        advapi.CloseServiceHandle(manager)


def grant_directory(path: Path, sid: str, *, writable: bool) -> None:
    """只向专用目录授予隔离身份权限。"""
    rights = "M" if writable else "RX"
    commands = []
    if writable:
        # 数据盘可能仅继承 Modify；专用目录的所有者需要 WRITE_OWNER 才能降低完整性级别。
        commands.append(["icacls", str(path), "/grant", "*S-1-3-4:(OI)(CI)F", "/Q"])
    commands.append(["icacls", str(path), "/grant", f"*{sid}:(OI)(CI){rights}", "/Q"])
    if writable:
        commands.append(["icacls", str(path), "/setintegritylevel", "(OI)(CI)L", "/Q"])
    for args in commands:
        result = subprocess.run(args, capture_output=True, timeout=20, creationflags=0x08000000,
                                check=False)
        if result.returncode:
            raise SandboxUnavailable("无法设置隔离目录访问权限")


def run_isolated(
    executable: Path,
    arguments: list[str],
    directory: Path,
    *,
    environment: dict[str, str],
    stdin: str = "",
    timeout: float = 2,
    memory_mb: int = 256,
    processes: int = 1,
    output_limit: int = 65536,
    cancel: threading.Event | None = None,
    output_fallback_encoding: str | None = None,
    least_privileged: bool = True,
) -> ProcessResult:
    """先建立全部限制，再恢复挂起的 LPAC 进程。"""
    import msvcrt

    kernel, userenv, advapi = _api()
    if not network_isolation_available():
        raise SandboxUnavailable("Windows 网络隔离服务未就绪，禁止执行提交")
    handles: list[int] = []
    files: list = []
    attributes = None
    sid = w.LPVOID()
    name = "filemate.cpp." + uuid.uuid4().hex
    profile_created = False
    job = None
    info = _ProcessInfo()
    pipe_writes: list[int] = []
    started = time.monotonic()
    try:
        if userenv.CreateAppContainerProfile(name, name, "FileMate temporary judge", None, 0,
                                             ctypes.byref(sid)) < 0:
            raise SandboxUnavailable("无法创建隔离身份")
        profile_created = True
        sid_string = w.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_string)):
            raise SandboxUnavailable("无法解析隔离身份")
        try:
            grant_directory(directory, sid_string.value, writable=True)
        finally:
            kernel.LocalFree(sid_string)

        # 输入文件和管道只继承三个指定句柄，避免泄露宿主打开的数据库或凭据。
        input_path = directory / ".stdin"
        input_path.write_text(stdin, encoding="utf-8", newline="")
        input_file = input_path.open("rb")
        files.append(input_file)
        in_handle = msvcrt.get_osfhandle(input_file.fileno())
        out_read, out_write = os.pipe()
        err_read, err_write = os.pipe()
        pipe_writes.extend([out_write, err_write])
        files.extend([os.fdopen(out_read, "rb", buffering=0), os.fdopen(err_read, "rb", buffering=0)])
        inherited = [in_handle, msvcrt.get_osfhandle(out_write), msvcrt.get_osfhandle(err_write)]
        for handle in inherited:
            os.set_handle_inheritable(handle, True)

        size = ctypes.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 3, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        attributes = ctypes.cast(buffer, w.LPVOID)
        if not kernel.InitializeProcThreadAttributeList(attributes, 3, 0, ctypes.byref(size)):
            raise SandboxUnavailable("无法初始化隔离属性")
        caps = _Capabilities(sid, None, 0, 0)
        opt_out = w.DWORD(1 if least_privileged else 0)
        handle_array = (w.HANDLE * 3)(*inherited)
        for attribute, value in [(0x20009, caps), (0x2000F, opt_out), (0x20002, handle_array)]:
            if not kernel.UpdateProcThreadAttribute(attributes, 0, attribute, ctypes.byref(value),
                                                    ctypes.sizeof(value), None, None):
                raise SandboxUnavailable("无法应用完整隔离属性")
        startup = _StartupInfoEx()
        startup.startup.cb = ctypes.sizeof(startup)
        startup.startup.flags = 0x101
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = inherited
        startup.attributes = attributes

        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise SandboxUnavailable("无法建立资源限制")
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000 | 0x200 | 0x100 | 0x8 | 0x4 | 0x400
        limits.basic.active_processes = processes
        limits.basic.job_time = int(timeout * 10_000_000)
        limits.process_memory = limits.job_memory = memory_mb * 1024 * 1024
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise SandboxUnavailable("无法应用内存、CPU 与进程限制")
        ui = w.DWORD(0xFF)
        if not kernel.SetInformationJobObject(job, 4, ctypes.byref(ui), ctypes.sizeof(ui)):
            raise SandboxUnavailable("无法隔离桌面资源")
        # Windows 用这两个标准路径定位该临时身份的 AC/Temp；不会继承其他宿主变量。
        isolated_env = {"USERPROFILE": str(Path.home()),
                        "LOCALAPPDATA": str(Path.home() / "AppData/Local"),
                        "APPDATA": str(directory), **environment}
        env_block = ctypes.create_unicode_buffer("\0".join(
            f"{key}={value}" for key, value in sorted(isolated_env.items(), key=lambda x: x[0].upper())
        ) + "\0\0")
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(executable), *arguments]))
        if not _create_process_without_error_dialog(kernel, str(executable), command, None, None, True,
                                     0x80000 | 0x400 | 0x4 | 0x08000000,
                                     env_block, str(directory), ctypes.byref(startup), ctypes.byref(info)):
            raise SandboxUnavailable(f"无法启动隔离进程 (Windows {ctypes.get_last_error()})")
        handles.extend([info.process, info.thread])
        if not kernel.AssignProcessToJobObject(job, info.process):
            kernel.TerminateProcess(info.process, 1)
            raise SandboxUnavailable("无法绑定资源限制，进程已终止")
        for handle in inherited:
            os.set_handle_inheritable(handle, False)
        os.close(out_write)
        os.close(err_write)
        pipe_writes.clear()
        chunks = [bytearray(), bytearray()]
        exceeded = threading.Event()

        def read_output(index: int) -> None:
            while data := files[index + 1].read(4096):
                available = max(0, output_limit - len(chunks[index]))
                chunks[index].extend(data[:available])
                if len(data) > available:
                    exceeded.set()
                    kernel.TerminateJobObject(job, 1)
                    break

        readers = [threading.Thread(target=read_output, args=(i,), daemon=True) for i in (0, 1)]
        for reader in readers:
            reader.start()
        started = time.monotonic()
        if kernel.ResumeThread(info.thread) == 0xFFFFFFFF:
            raise SandboxUnavailable("无法恢复隔离进程")
        reason = ""
        while kernel.WaitForSingleObject(info.process, 20) == 0x102:
            if cancel and cancel.is_set():
                reason = "cancelled"
            elif exceeded.is_set():
                reason = "output_limit"
            elif time.monotonic() - started > timeout:
                reason = "timeout"
            else:
                io_limits = _IoAccounting()
                kernel.QueryInformationJobObject(job, 8, ctypes.byref(io_limits),
                                                 ctypes.sizeof(io_limits), None)
                if io_limits.io.write_bytes > 16 * 1024 * 1024:
                    reason = "file_output_limit"
            if reason:
                kernel.TerminateJobObject(job, 1)
                kernel.WaitForSingleObject(info.process, 2000)
                break
        elapsed = int((time.monotonic() - started) * 1000)
        code = w.DWORD()
        if not kernel.GetExitCodeProcess(info.process, ctypes.byref(code)):
            raise SandboxUnavailable("无法取得隔离执行结果")
        # 编译器可能留下子进程，关闭 Job 前强制终止整组以释放管道。
        kernel.TerminateJobObject(job, 1)
        for reader in readers:
            reader.join(timeout=3)
        kernel.QueryInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits), None)
        if exceeded.is_set():
            reason = "output_limit"
        elif cancel and cancel.is_set():
            reason = "cancelled"
        elif code.value == 0xC0000044:
            reason = "timeout"
        return ProcessResult(code.value, decode_output(chunks[0], output_fallback_encoding),
                             decode_output(chunks[1], output_fallback_encoding), elapsed,
                             int(limits.peak_job), reason)
    finally:
        if job:
            kernel.TerminateJobObject(job, 1)
        for handle in handles:
            kernel.CloseHandle(handle)
        if job:
            kernel.CloseHandle(job)
        if attributes:
            kernel.DeleteProcThreadAttributeList(attributes)
        for file in files:
            file.close()
        for descriptor in pipe_writes:
            os.close(descriptor)
        if sid:
            advapi.FreeSid(sid)
        if profile_created:
            userenv.DeleteAppContainerProfile(name)
