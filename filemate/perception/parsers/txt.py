"""纯文本解析器。"""

from pathlib import Path

from . import PLAIN_TEXT_SUFFIXES, register


def parse(path: Path) -> dict:
    """解析纯文本文件。"""
    text = path.read_text(encoding="utf-8")
    return {"raw_text": text}


# 注册解析器
_parser = type("TXTParser", (), {"parse": staticmethod(parse)})()
for _suffix in PLAIN_TEXT_SUFFIXES:
    register(_suffix, _parser)
