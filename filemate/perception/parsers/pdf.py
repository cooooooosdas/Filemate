"""PDF 解析。"""

from __future__ import annotations

import logging
from pathlib import Path

from ..parsers import register

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 解析器。

    优先使用 PyPDF2 提取文字流，失败时回退到 pdfplumber。
    """

    def parse(self, path: str | Path) -> dict:
        p = Path(path)
        if self._is_encrypted(p):
            return {
                "raw_text": "",
                "metadata": {"suffix": "pdf", "encrypted": True},
                "error": "PDF 已加密，请先解密后重新上传",
            }
        empty_result = None
        # 先提取文字流，避免对教材逐字构建昂贵的版面几何缓存。
        for engine in (self._parse_pypdf2, self._parse_pdfplumber):
            try:
                result = engine(p)
            except ImportError:
                continue
            except MemoryError:
                raise
            except Exception:  # noqa: BLE001 - decoder fallback boundary
                logger.warning("PDF decoder failed: %s", engine.__name__)
                continue
            if result.get('error') or result['raw_text'].strip():
                return result
            empty_result = result
        if empty_result is not None:
            empty_result['metadata']['text_pages'] = 0
            empty_result['note'] = "图片型PDF，无文字层，需OCR"
            return empty_result
        raise RuntimeError("PDF 无法解析，请确认文件有效或另存后重试")

    # ------------------------------------------------------------------
    # 加密检测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_encrypted(p: Path) -> bool:
        """检测 PDF 是否加密。"""
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            try:
                from pypdf import PdfReader  # type: ignore[no-redef]
            except ImportError:
                return False  # 无法检测，不阻断
        try:
            reader = PdfReader(str(p))
            return reader.is_encrypted
        except Exception:  # noqa: BLE001
            return False  # 检测失败，不阻断

    # ------------------------------------------------------------------
    # pdfplumber 实现
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_pdfplumber(p: Path) -> dict:
        try:
            import pdfplumber
        except ImportError as exc:
            raise ImportError from exc

        text_parts: list[str] = []
        characters = 0
        truncated = False
        with pdfplumber.open(str(p)) as pdf:
            total_pages = len(pdf.pages)
            if total_pages > 500:
                return {'raw_text': '', 'metadata': {'total_pages': total_pages},
                        'error': 'PDF 超过 500 页，请拆分文件后重试'}
            for i, page in enumerate(pdf.pages):
                try:
                    text = (page.extract_text() or '').strip()
                finally:
                    page.close()
                if text:
                    part = f"--- 第 {i + 1} 页 ---\n{text}"
                    remaining = 500_000 - characters
                    text_parts.append(part[:remaining])
                    characters += len(part) + 2
                    if characters >= 500_000:
                        truncated = True
                        break

        raw = "\n\n".join(text_parts)
        logger.debug(
            "PDF 解析(pdfplumber): %s → %d/%d 页有文字 / %d 字",
            p.name,
            len(text_parts),
            total_pages,
            len(raw),
        )
        return {
            "raw_text": raw,
            "metadata": {
                "suffix": "pdf",
                "total_pages": total_pages,
                "text_pages": len(text_parts),
                "engine": "pdfplumber",
                "truncated": truncated,
            },
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
        total_pages = len(reader.pages)
        if total_pages > 500:
            return {'raw_text': '', 'metadata': {'total_pages': total_pages},
                    'error': 'PDF 超过 500 页，请拆分文件后重试'}
        text_parts: list[str] = []
        characters = 0
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                part = f"--- 第 {i + 1} 页 ---\n{text}"
                text_parts.append(part[:max(0, 500_000 - characters)])
                characters += len(part) + 2
                if characters >= 500_000:
                    break

        raw = "\n\n".join(text_parts)
        logger.debug(
            "PDF 解析(PyPDF2): %s → %d/%d 页有文字 / %d 字",
            p.name,
            len(text_parts),
            total_pages,
            len(raw),
        )
        return {
            "raw_text": raw,
            "metadata": {
                "suffix": "pdf",
                "total_pages": total_pages,
                "text_pages": len(text_parts),
                "engine": "pypdf2",
                "truncated": characters >= 500_000,
            },
        }


register("pdf", PDFParser)
register("PDF", PDFParser)
