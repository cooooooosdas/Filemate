"""PaddleOCR 封装（可选依赖，不可用时优雅降级）。"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OCRBackend:
    """OCR 后端。

    - PaddleOCR 可用 → 真实识别
    - PaddleOCR 不可用 → ``recognize()`` 返回空字符串 + 打日志
    """

    def __init__(self, *, lang: str = "ch") -> None:
        """
        Parameters
        ----------
        lang : str
            识别语言，"ch" = 中文，"en" = 英文，"ch_en" = 中英混合。
        """
        self.lang = lang
        self._available = self._probe()

    def _probe(self) -> bool:
        try:
            from paddleocr import PaddleOCR  # noqa: F401
            return True
        except ImportError:
            logger.info("PaddleOCR 未安装，OCR 功能不可用（仅影响图片文件）")
            return False

    @property
    def available(self) -> bool:
        return self._available

    def recognize(self, image_path: str | Path) -> str:
        """识别图片中的文字。不可用时返回空字符串。"""
        p = Path(image_path)
        if not p.exists():
            logger.warning("OCR 目标不存在: %s", p)
            return ""
        if not self._available:
            logger.debug("OCR 跳过（PaddleOCR 不可用）: %s", p.name)
            return ""

        try:
            from paddleocr import PaddleOCR
            ocr = PaddleOCR(use_angle_cls=True, lang=self.lang, show_log=False)
            result = ocr.ocr(str(p), cls=True)
            lines: list[str] = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0].strip()
                    if text:
                        lines.append(text)
            text = "\n".join(lines)
            logger.debug("OCR 识别: %s → %d 字", p.name, len(text))
            return text
        except Exception as exc:
            logger.exception("OCR 识别失败: %s", p)
            return ""
