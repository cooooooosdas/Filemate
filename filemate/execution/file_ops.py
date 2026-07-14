"""文件 I/O 工具。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OpResult:
    success: bool
    error: str = ""
    dest_path: str = ""


class FileOps:
    """文件操作工具。"""

    def ensure_dir(self, path: str | Path) -> Path:
        """TODO(徐书和): 创建目录（若不存在）。"""
        raise NotImplementedError("TODO(徐书和)")

    def move(self, src: str | Path, dst: str | Path) -> OpResult:
        """TODO(徐书和): 移动文件到目标路径（自动创建父目录）。"""
        raise NotImplementedError("TODO(徐书和)")

    def rename(self, path: str | Path, new_name: str) -> OpResult:
        """TODO(徐书和): 原地重命名文件。"""
        raise NotImplementedError("TODO(徐书和)")

    def compute_hash(self, path: str | Path) -> str:
        """TODO(徐书和): 计算文件 SHA-256。"""
        raise NotImplementedError("TODO(徐书和)")
