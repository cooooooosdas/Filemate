"""统一文件解析入口。"""

from __future__ import annotations

from pathlib import Path

from .parsers import get_parser


class FileParser:
    """根据文件后缀自动选择解析器，返回统一格式。

    输出格式::

        {
            "raw_text": str,
            "metadata": {
                "filename": str,
                "suffix": str,
                "size_bytes": int,
            },
        }
    """

    def parse(self, path: str | Path) -> dict:
        """TODO(汤新阳): 实现统一入口 + 异常处理 + 大文件截断。"""
        raise NotImplementedError("TODO(汤新阳): FileParser 实现")
