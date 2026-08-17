"""文件 I/O 工具。"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class OpResult:
    success: bool
    error: str = ""
    dest_path: str = ""


class FileOps:
    """文件操作工具（纯函数式接口，副作用尽量少）。"""

    INVALID_WINDOWS_CHARS: ClassVar[frozenset[str]] = frozenset('<>:"/\\|?*')
    RESERVED_WINDOWS_NAMES: ClassVar[set[str]] = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }

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
        if src_p.resolve() == dst_p.resolve():
            return OpResult(True, "", str(dst_p))
        if dst_p.exists():
            return OpResult(False, f"目标已存在: {dst_p}", "")
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
        if not new_name:
            return OpResult(False, "新文件名不能为空", "")
        try:
            new_path = p.with_name(new_name)
        except ValueError as exc:
            return OpResult(False, f"无效的文件名: {new_name!r} — {exc}", "")
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
        """计算文件 SHA-256 十六进制摘要。

        Raises:
            FileNotFoundError: 文件不存在。
        """
        src = Path(path)
        if not src.is_file():
            raise FileNotFoundError(f"文件不存在: {src}")
        h = hashlib.sha256()
        with open(src, "rb") as f:
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

    @classmethod
    def validate_filename(cls, name: str) -> str:
        """校验单个文件名并阻止路径穿越与 Windows 非法名称。"""
        candidate = name.strip()
        if not candidate or candidate in {".", ".."}:
            raise ValueError("文件名不能为空")
        if any(char in cls.INVALID_WINDOWS_CHARS for char in candidate):
            raise ValueError("文件名不能包含路径分隔符或系统非法字符")
        if any(ord(char) < 32 for char in candidate):
            raise ValueError("文件名不能包含控制字符")
        if candidate.endswith((" ", ".")):
            raise ValueError("文件名不能以空格或句点结尾")
        if Path(candidate).stem.upper() in cls.RESERVED_WINDOWS_NAMES:
            raise ValueError("文件名是系统保留名称")
        return candidate

    @classmethod
    def sanitize_path_segment(cls, value: str, fallback: str) -> str:
        """把用户可编辑文本收敛为安全目录名。"""
        cleaned = "".join(
            "-" if char in cls.INVALID_WINDOWS_CHARS or ord(char) < 32 else char
            for char in value.strip()
        ).strip(" .")
        if not cleaned or cleaned in {".", ".."}:
            return fallback
        if cleaned.upper() in cls.RESERVED_WINDOWS_NAMES:
            return fallback
        return cleaned[:80]

    @staticmethod
    def is_supported(path: str | Path) -> bool:
        """判断文件扩展名是否为系统支持的格式。"""
        return FileOps.suffix(path) in {
            "pdf", "docx", "doc", "pptx", "ppt",
            "txt", "md", "png", "jpg", "jpeg", "bmp",
        }
