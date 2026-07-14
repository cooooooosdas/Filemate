"""PDF 解析。"""

from __future__ import annotations

import logging
from pathlib import Path

from ..parsers import register

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 解析器。

    优先使用 pdfplumber（提取质量更高），不可用时回退到 PyPDF2。
    """

    def parse(self, path: str | Path) -> dict:
        p = Path(path)

        # 优先 pdfplumber
        try:
            return self._parse_pdfplumber(p)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("pdfplumber 解析失败，回退 PyPDF2: %s", exc)

        # 回退 PyPDF2
        try:
            return self._parse_pypdf2(p)
        except ImportError as exc:
            raise RuntimeError(
                "PDF 解析需要 pdfplumber 或 PyPDF2。运行: pip install pdfplumber PyPDF2"
            ) from exc

    # ------------------------------------------------------------------
    # pdfplumber 实现
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pdfplumber(p: Path) -> dict:
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError from exc

        pages: list[str] = []
        with pdfplumber.open(str(p)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = text.strip()
                if text:
                    pages.append(f"--- 第 {i + 1} 页 ---\n{text}")

        raw = "\n\n".join(pages)
        logger.debug("PDF 解析(pdfplumber): %s → %d 页 / %d 字", p.name, len(pages), len(raw))
        return {
            "raw_text": raw,
            "metadata": {"suffix": "pdf", "pages": len(pages), "engine": "pdfplumber"},
        }

    # ------------------------------------------------------------------
    # PyPDF2 回退
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pypdf2(p: Path) -> dict:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            try:
                from pypdf import PdfReader  # type: ignore[no-redef]
            except ImportError as exc:
                raise ImportError from exc

        reader = PdfReader(str(p))
        pages: list[str] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"--- 第 {i + 1} 页 ---\n{text}")

        raw = "\n\n".join(pages)
        logger.debug("PDF 解析(PyPDF2): %s → %d 页 / %d 字", p.name, len(pages), len(raw))
        return {
            "raw_text": raw,
            "metadata": {"suffix": "pdf", "pages": len(pages), "engine": "pypdf2"},
        }


register("pdf", PDFParser)
register("PDF", PDFParser)
