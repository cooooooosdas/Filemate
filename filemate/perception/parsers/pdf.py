"""PDF 解析。"""

from ..parsers import register


class PDFParser:
    def parse(self, path):
        """TODO(汤新阳): 使用 PyPDF2 / pdfplumber 实现。"""
        raise NotImplementedError("TODO(汤新阳): PDF 解析")


register("pdf", PDFParser)
register("PDF", PDFParser)
