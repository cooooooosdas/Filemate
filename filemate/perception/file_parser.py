"""统一文件解析入口。"""

from __future__ import annotations

import logging
from pathlib import Path

from .parsers import get_parser

logger = logging.getLogger(__name__)

# 输出契约（全感知层统一）
_RESULT_KEYS = ("raw_text", "metadata")


class FileParser:
    """根据文件后缀自动选择解析器，返回统一格式。

    输出格式::

        {
            "raw_text": str,        # 提取的文本内容
            "metadata": {
                "filename": str,    # 原始文件名
                "suffix": str,      # 小写后缀（不含点）
                "size_bytes": int,  # 文件字节大小
            },
        }

    异常处理：解析失败时返回带 ``error`` 字段的结构，不抛异常。
    """

    _MAX_CHARS = 500_000  # 50 万字，控制 LLM token 消耗

    def parse(self, path: str | Path) -> dict:
        """解析文件。"""
        p = Path(path)

        # 前置检查
        if not p.exists():
            return self._error(p, f"文件不存在: {path}")
        if not p.is_file():
            return self._error(p, f"不是文件: {path}")
        if p.stat().st_size == 0:
            return self._ok(p, raw_text="", note="空文件")

        # 选解析器
        suffix = p.suffix.lstrip(".").lower()
        try:
            parser = get_parser(suffix)
        except ValueError:
            return self._error(p, f"不支持的格式: .{suffix}")

        # 调用解析器
        try:
            result = parser.parse(p)
        except Exception as exc:
            logger.exception("解析失败: %s", p)
            return self._error(p, f"解析异常: {exc}")

        # 规范输出
        raw = (result or {}).get("raw_text", "") or ""
        if len(raw) > self._MAX_CHARS:
            raw = raw[: self._MAX_CHARS]
            logger.info("文本已截断到 %d 字: %s", self._MAX_CHARS, p.name)

        return self._ok(p, raw_text=raw)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _ok(p: Path, *, raw_text: str = "", note: str = "") -> dict:
        meta = {
            "filename": p.name,
            "suffix": p.suffix.lstrip(".").lower(),
            "size_bytes": p.stat().st_size,
        }
        out: dict = {"raw_text": raw_text, "metadata": meta}
        if note:
            out["note"] = note
        return out

    @staticmethod
    def _error(p: Path, msg: str) -> dict:
        return {
            "raw_text": "",
            "metadata": {
                "filename": p.name,
                "suffix": p.suffix.lstrip(".").lower(),
                "size_bytes": p.stat().st_size if p.exists() else 0,
            },
            "error": msg,
        }
