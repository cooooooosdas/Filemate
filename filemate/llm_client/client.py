"""LLMClient 统一调用入口。"""

from __future__ import annotations

from typing import Any

from .config import LLMConfig
from .providers.base import BaseLLMProvider
from .providers.step_speed import StepSpeedProvider
from .exceptions import (
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
)


class LLMClient:
    """统一 LLM 调用客户端。

    用法::

        client = LLMClient()
        reply = client.call(prompt="...", messages=[{"role": "user", "content": text}])
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        if config is None:
            config = LLMConfig.from_env()
        self.config = config
        self._provider: BaseLLMProvider = self._build(config)

    # ------------------------------------------------------------------
    # 供应商路由
    # ------------------------------------------------------------------

    @staticmethod
    def _build(config: LLMConfig) -> BaseLLMProvider:
        name = (config.provider or "step_speed").lower()
        if name == "step_speed":
            return StepSpeedProvider(config)
        raise LLMConfigError(f"不支持的 LLM 供应商: {name}")

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def call(
        self,
        prompt: str = "",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        retry: int = 3,
        timeout: float = 60.0,
    ) -> str:
        """调用 LLM 并返回纯文本回复。"""
        raise NotImplementedError("TODO(胡希): 实现重试 / 超时 / 降级")

    def call_structured(
        self,
        prompt: str = "",
        messages: list[dict[str, str]] | None = None,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """调用 LLM 并把回复解析为 JSON 对象。"""
        raise NotImplementedError("TODO(胡希): 实现")

    def get_usage(self) -> dict[str, int]:
        """返回本次 token 用量统计（prompt_tokens / completion_tokens）。"""
        raise NotImplementedError("TODO(胡希): 实现")
