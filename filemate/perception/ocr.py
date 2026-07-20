"""PaddleOCR 封装（可选依赖，不可用时优雅降级）。

PaddleOCR 3.x API:
- 引擎: 默认 paddle（需 PaddlePaddle），可改用 onnxruntime（轻量）
- 模型: 默认 PP-OCRv6，可通过 ocr_version 切换
- predict() 返回 OCRResult 列表，含 rec_texts / rec_scores / dt_polys
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paddleocr import PaddleOCR as _PaddleOCR

logger = logging.getLogger(__name__)

# ── 默认参数 ──
_DEFAULT_OCR_VERSION = "PP-OCRv6"


class OCRBackend:
    """OCR 后端（懒加载 PaddleOCR 引擎，首次调用时初始化）。

    - PaddleOCR 可用 → 真实识别
    - PaddleOCR 不可用 → ``recognize()`` 返回空字符串 + 打日志

    用法::

        ocr = OCRBackend(lang="ch")
        if ocr.available:
            text = ocr.recognize("screenshot.png")
    """

    def __init__(
        self,
        *,
        lang: str = "ch",
        ocr_version: str = _DEFAULT_OCR_VERSION,
        engine: str | None = None,
    ) -> None:
        """
        Parameters
        ----------
        lang : str
            识别语言。"ch" = 中文，"en" = 英文。
        ocr_version : str
            PP-OCR 版本，默认 PP-OCRv6。可设 "PP-OCRv5" 等。
        engine : str | None
            推理引擎。None = 自动选择，"onnxruntime" = 免 PaddlePaddle。
        """
        self.lang = lang
        self.ocr_version = ocr_version
        self.engine = engine
        self._ocr: _PaddleOCR | None = None
        self._available: bool | None = None  # None = 未探测

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        """PaddleOCR 是否可用（首次访问时自动探测）。"""
        if self._available is None:
            self._available = self._probe()
        return self._available

    def recognize(self, image_path: str | Path) -> str:
        """识别图片中的文字，返回拼接后的文本。不可用时返回空字符串。"""
        p = Path(image_path)
        if not p.exists():
            logger.warning("OCR 目标不存在: %s", p)
            return ""
        if not self.available:
            logger.debug("OCR 跳过（PaddleOCR 不可用）: %s", p.name)
            return ""

        try:
            engine = self._get_engine()
            result = engine.predict(str(p))
            lines: list[str] = []
            for res in result:
                rec_texts = res.get("rec_texts", []) if isinstance(res, dict) else getattr(res, "rec_texts", [])
                for text in rec_texts:
                    text = (text or "").strip()
                    if text:
                        lines.append(text)
            text = "\n".join(lines)
            logger.debug("OCR 识别: %s → %d 字", p.name, len(text))
            return text
        except Exception:
            logger.exception("OCR 识别失败: %s", p)
            return ""

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _probe(self) -> bool:
        try:
            from paddleocr import PaddleOCR  # noqa: F401
            return True
        except ImportError:
            logger.info("PaddleOCR 未安装，OCR 功能不可用")
            return False

    def _get_engine(self) -> _PaddleOCR:
        """懒初始化 PaddleOCR 引擎（模型只加载一次）。"""
        if self._ocr is not None:
            return self._ocr

        from paddleocr import PaddleOCR

        kwargs: dict = {
            "lang": self.lang,
            "ocr_version": self.ocr_version,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        }
        if self.engine:
            kwargs["engine"] = self.engine

        logger.info(
            "初始化 PaddleOCR: lang=%s version=%s engine=%s",
            self.lang, self.ocr_version, self.engine or "auto",
        )
        self._ocr = PaddleOCR(**kwargs)
        return self._ocr
