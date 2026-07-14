"""PPT 解析。"""

from ..parsers import register


class PPTParser:
    def parse(self, path):
        """TODO(汤新阳): 使用 python-pptx 实现。"""
        raise NotImplementedError("TODO(汤新阳): PPT 解析")


register("pptx", PPTParser)
register("ppt", PPTParser)
