"""Word 解析。"""

from ..parsers import register


class WordParser:
    def parse(self, path):
        """TODO(汤新阳): 使用 python-docx 实现。"""
        raise NotImplementedError("TODO(汤新阳): Word 解析")


register("docx", WordParser)
register("doc", WordParser)
