"""LLM 供应商抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models.response import LLMResponse


class BaseLLMProvider(ABC):
    """所有供应商必须实现 chat()。"""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> str:
        """返回纯文本回复。"""
        ...

    def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """兼容只返回文本的适配器，其用量保持未知。"""
        return LLMResponse(text=self.chat(messages, **kwargs))
