"""文件 I/O 工具。"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class OpResult:
    success: bool
    error: str = ""
    dest_path: str = ""


class FileOps:
    """文件操作工具（纯函数式接口，副作用尽量少）。"""

    # ------------------------------------------------------------------
    # 目录
    # ------------------------------------------------------------------

    def ensure_dir(self, path: str | Path) -> Path:
        """确保目录存在，不存在则创建。"""
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ------------------------------------------------------------------
    # 移动 / 复制 / 重命名
    # ------------------------------------------------------------------

    def move(self, src: str | Path, dst: str | Path) -> OpResult:
        """移动文件到目标路径（自动创建目标父目录）。"""
        src_p = Path(src)
        dst_p = Path(dst)
        if not src_p.exists():
            return OpResult(False, f"源文件不存在: {src}", "")
        try:
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_p), str(dst_p))
            logger.debug("move: %s -> %s", src_p, dst_p)
            return OpResult(True, "", str(dst_p))
        except (PermissionError, OSError) as exc:
            logger.error("move 失败: %s", exc)
            return OpResult(False, str(exc), "")

    def rename(self, path: str | Path, new_name: str) -> OpResult:
        """原地重命名文件（保留所在目录）。"""
        p = Path(path)
        if not p.exists():
            return OpResult(False, f"文件不存在: {path}", "")
        new_path = p.with_name(new_name)
        if new_path.exists():
            return OpResult(False, f"目标已存在: {new_path}", "")
        try:
            p.rename(new_path)
            logger.debug("rename: %s -> %s", p.name, new_name)
            return OpResult(True, "", str(new_path))
        except (PermissionError, OSError) as exc:
            return OpResult(False, str(exc), "")

    def copy(self, src: str | Path, dst: str | Path) -> OpResult:
        """复制文件（保留源文件）。"""
        src_p = Path(src)
        dst_p = Path(dst)
        if not src_p.exists():
            return OpResult(False, f"源文件不存在: {src}", "")
        try:
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_p), str(dst_p))
            return OpResult(True, "", str(dst_p))
        except (PermissionError, OSError) as exc:
            return OpResult(False, str(exc), "")

    def delete(self, path: str | Path) -> OpResult:
        """删除文件。"""
        p = Path(path)
        if not p.exists():
            return OpResult(False, f"文件不存在: {path}", "")
        try:
            p.unlink()
            return OpResult(True, "")
        except (PermissionError, OSError) as exc:
            return OpResult(False, str(exc), "")

    # ------------------------------------------------------------------
    # 哈希
    # ------------------------------------------------------------------

    def compute_hash(self, path: str | Path, chunk_size: int = 1 << 20) -> str:
        """计算文件 SHA-256 十六进制摘要。"""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def suffix(path: str | Path) -> str:
        """返回小写扩展名（不含点）。"""
        return Path(path).suffix.lstrip(".").lower()

    @staticmethod
    def is_supported(path: str | Path) -> bool:
        return FileOps.suffix(path) in {
            "pdf", "docx", "doc", "pptx", "ppt",
            "txt", "md", "png", "jpg", "jpeg", "bmp",
        }
