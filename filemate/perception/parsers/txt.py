"""纯文本解析器。"""

from pathlib import Path

from . import register


def parse(path: Path) -> dict:
    """解析纯文本文件。"""
    text = path.read_text(encoding="utf-8")
    return {"raw_text": text}


# 注册解析器
register("txt", type("TXTParser", (), {"parse": staticmethod(parse)})())