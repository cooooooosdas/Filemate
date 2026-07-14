"""LLMClient 统一调用入口。"""

from __future__ import annotations

import json
import logging
import time
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

logger = logging.getLogger(__name__)


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
        self._last_usage: dict[str, int] = {}

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
        """调用 LLM 并返回纯文本回复。支持重试与指数退避。"""
        if messages is None:
            messages = []
        if prompt:
            messages = [{"role": "system", "content": prompt}] + messages

        last_exc: Exception | None = None
        for attempt in range(1, retry + 1):
            try:
                text = self._provider.chat(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    timeout=timeout,
                )
                self._last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
                return text
            except LLMRateLimitError as exc:
                wait = min(2 ** attempt, 30)
                logger.warning("限流，%ds 后重试 (%d/%d)", wait, attempt, retry)
                time.sleep(wait)
                last_exc = exc
            except LLMTimeoutError as exc:
                logger.warning("超时，%d/%d 次重试", attempt, retry)
                last_exc = exc
            except LLMAPIError as exc:
                logger.error("API 错误: %s", exc)
                last_exc = exc
                break

        raise LLMAPIError(
            f"LLM 调用在 {retry} 次重试后仍失败: {last_exc}"
        ) from last_exc

    def call_structured(
        self,
        prompt: str = "",
        messages: list[dict[str, str]] | None = None,
        schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """调用 LLM 并把回复解析为 JSON 对象。"""
        json_instruction = (
            "请仅返回严格 JSON，不要额外解释。"
            if schema is None
            else f"请仅返回符合以下 JSON Schema 的内容，不要额外解释：\n{json.dumps(schema, ensure_ascii=False)}"
        )
        full_messages = [
            {"role": "system", "content": json_instruction},
        ]
        if prompt:
            full_messages.append({"role": "system", "content": prompt})
        if messages:
            full_messages.extend(messages)

        text = self.call(messages=full_messages, **kwargs)

        # 尝试提取被 ```json ... ``` 包裹的内容
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[1:])
        if cleaned.endswith("```"):
            cleaned = "\n".join(cleaned.splitlines()[:-1])
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMAPIError(
                f"LLM 返回内容无法解析为 JSON: {cleaned[:200]!r}"
            ) from exc

    def get_usage(self) -> dict[str, int]:
        """返回最近一次调用的 token 用量。"""
        return dict(self._last_usage)
