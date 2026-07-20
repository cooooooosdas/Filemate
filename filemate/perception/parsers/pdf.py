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

        # ── 第一引擎：pdfplumber ──
        result_plumber: dict | None = None
        total_pages = 0

        try:
            result_plumber = self._parse_pdfplumber(p)
            total_pages = result_plumber["metadata"].get("total_pages", 0)
        except ImportError:
            pass  # pdfplumber 未安装，直接跳 PyPDF2
        except Exception as exc:
            logger.warning("pdfplumber 解析失败，回退 PyPDF2: %s", exc)

        # pdfplumber 成功且有文字 → 直接返回
        if result_plumber and result_plumber["raw_text"].strip():
            return result_plumber

        # ── 第二引擎：PyPDF2 回退 ──
        try:
            result_pypdf = self._parse_pypdf2(p)
            if result_pypdf["raw_text"].strip():
                return result_pypdf  # PyPDF2 提取到了文字
            if total_pages == 0:
                total_pages = result_pypdf["metadata"].get("total_pages", 0)
        except ImportError as exc:
            if result_plumber is None:
                raise RuntimeError(
                    "PDF 解析需要 pdfplumber 或 PyPDF2。"
                    "运行: pip install pdfplumber PyPDF2"
                ) from exc
            # pdfplumber 跑通了（虽然空文本），PyPDF2 未安装，用 plumber 结果
        except Exception as exc:
            logger.warning("PyPDF2 也解析失败: %s", exc)

        # ── 两个引擎都返回空文本 → 判为图片型 PDF ──
        if total_pages > 0:
            logger.info(
                "PDF 可能为图片型扫描件（%d 页无文字层），需 OCR: %s",
                total_pages, p.name,
            )
            return {
                "raw_text": "",
                "metadata": {
                    "suffix": "pdf",
                    "total_pages": total_pages,
                    "text_pages": 0,
                },
                "note": "图片型PDF，无文字层，需OCR",
            }

        # 完全没有 page 数据 → 用 plumber 的空结果兜底
        if result_plumber is not None:
            return result_plumber

        raise RuntimeError(
            "PDF 解析需要 pdfplumber 或 PyPDF2。"
            "运行: pip install pdfplumber PyPDF2"
        )

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
        with pdfplumber.open(str(p)) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                text = text.strip()
                if text:
                    text_parts.append(f"--- 第 {i + 1} 页 ---\n{text}")

        raw = "\n\n".join(text_parts)
        logger.debug(
            "PDF 解析(pdfplumber): %s → %d/%d 页有文字 / %d 字",
            p.name, len(text_parts), total_pages, len(raw),
        )
        return {
            "raw_text": raw,
            "metadata": {
                "suffix": "pdf",
                "total_pages": total_pages,
                "text_pages": len(text_parts),
                "engine": "pdfplumber",
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
        text_parts: list[str] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                text_parts.append(f"--- 第 {i + 1} 页 ---\n{text}")

        raw = "\n\n".join(text_parts)
        logger.debug(
            "PDF 解析(PyPDF2): %s → %d/%d 页有文字 / %d 字",
            p.name, len(text_parts), total_pages, len(raw),
        )
        return {
            "raw_text": raw,
            "metadata": {
                "suffix": "pdf",
                "total_pages": total_pages,
                "text_pages": len(text_parts),
                "engine": "pypdf2",
            },
        }


register("pdf", PDFParser)
register("PDF", PDFParser)
