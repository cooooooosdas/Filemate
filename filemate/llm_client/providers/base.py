"""LLM 供应商抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod


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
