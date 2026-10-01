"""复制已安装的 MSVC 工具链到专用只读沙箱目录。"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from .windows_sandbox import SandboxUnavailable, grant_directory

_SETUP_LOCK = threading.Lock()


def toolchain_root() -> Path:
    """取得受应用配置控制的工具链目录。"""
    return Path(os.getenv("FILEMATE_CPP_TOOLCHAIN_DIR", str(
        Path(__file__).resolve().parents[2] / "_working" / "cpp-toolchain"
    ))).resolve()


def discover_msvc() -> tuple[Path, Path]:
    """定位本机 x64 编译器与 Windows SDK。"""
    if os.name != "nt":
        raise SandboxUnavailable("此版本需要 Windows 10/11 与 Visual Studio C++ 开发工具")
    visual_studio = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft Visual Studio"
    candidates = sorted(visual_studio.glob("*/*/VC/Tools/MSVC/*"), reverse=True)
    compiler = next((p for p in candidates if (p / "bin/Hostx64/x64/cl.exe").is_file()), None)
    kits = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits/10"
    versions = sorted((kits / "Include").glob("*"), reverse=True)
    sdk = next((p for p in versions if (kits / "Lib" / p.name / "um/x64/kernel32.lib").is_file()), None)
    if compiler is None or sdk is None:
        raise SandboxUnavailable("未找到 MSVC x64 与 Windows SDK，请安装 Visual Studio 的 C++ 桌面开发组件")
    return compiler, sdk


def prepare_toolchain() -> Path:
    """准备独立副本，不修改安装目录的权限或文件。"""
    root = toolchain_root()
    with _SETUP_LOCK:
        if (root / "ready.txt").is_file():
            return root
        compiler, sdk = discover_msvc()
        root.mkdir(parents=True, exist_ok=True)
        # 工具链副本只能读取；不向任何 AppContainer 授予宿主安装目录权限。
        grant_directory(root, "S-1-15-2-2", writable=False)
        components = [
            (compiler / "bin/Hostx64/x64", root / "bin"),
            (compiler / "include", root / "msvc/include"),
            (compiler / "lib/x64", root / "msvc/lib"),
            (sdk / "ucrt", root / "sdk/include/ucrt"),
            (sdk / "shared", root / "sdk/include/shared"),
            (sdk / "um", root / "sdk/include/um"),
            (sdk.parents[1] / "Lib" / sdk.name / "ucrt/x64", root / "sdk/lib/ucrt"),
            (sdk.parents[1] / "Lib" / sdk.name / "um/x64", root / "sdk/lib/um"),
        ]
        if not (root / "ready.txt").is_file():
            for source, destination in components:
                shutil.copytree(source, destination, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("vctip.exe"))
        (root / "ready.txt").write_text(f"MSVC {compiler.name}; SDK {sdk.name}\n", encoding="utf-8")
        return root


def compiler_environment(root: Path, directory: Path) -> dict[str, str]:
    """仅向编译器提供标准库位置和私有临时路径。"""
    return {
        "SystemRoot": os.environ.get("SystemRoot", "C:/Windows"),
        "PATH": str(root / "bin"), "TEMP": str(directory), "TMP": str(directory),
        "INCLUDE": ";".join(str(root / path) for path in
                            ("msvc/include", "sdk/include/ucrt", "sdk/include/shared", "sdk/include/um")),
        "LIB": ";".join(str(root / path) for path in ("msvc/lib", "sdk/lib/ucrt", "sdk/lib/um")),
        "VSLANG": "1033",
    }
