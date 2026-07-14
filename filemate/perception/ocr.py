"""PaddleOCR 封装（可选依赖）。"""

from __future__ import annotations

from pathlib import Path


class OCRBackend:
    """OCR 后端封装。PaddleOCR 不可用时优雅降级。"""

    def __init__(self) -> None:
        self._available = False
        try:
            import paddle  # noqa: F401
            self._available = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        return self._available

    def recognize(self, image_path: str | Path) -> str:
        """TODO(汤新阳): 集成 PaddleOCR。"""
        raise NotImplementedError("TODO(汤新阳): OCR 集成")
