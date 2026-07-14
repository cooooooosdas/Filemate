"""Step 3.7 Speed 供应商实现（OpenAI 兼容接口）。"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .base import BaseLLMProvider
from ..config import LLMConfig
from ..exceptions import (
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class StepSpeedProvider(BaseLLMProvider):
    """对接 Step 3.7 Speed 大批量调用渠道。

    配置来源（按优先级）：
    1. 构造函数显式传入的 LLMConfig
    2. 环境变量（.env）
    """

    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise LLMConfigError("LLM_API_KEY 未配置，请在 .env 中设置")
        if not config.base_url:
            raise LLMConfigError("LLM_BASE_URL 未配置，请在 .env 中设置")
        if not config.model:
            raise LLMConfigError("LLM_MODEL 未配置，请在 .env 中设置")
        self.config = config

    # ------------------------------------------------------------------
    # BaseLLMProvider 接口
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> str:
        """发起一次 Step API 调用，返回纯文本回复。"""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        logger.debug("Step API 调用: %s | messages=%d 条", url, len(messages))

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.Timeout as exc:
            raise LLMTimeoutError(f"Step API 调用超时（{timeout}s）") from exc
        except requests.ConnectionError as exc:
            raise LLMAPIError(f"Step API 连接失败: {exc}") from exc

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise LLMRateLimitError(f"触发限流，{retry_after}s 后重试")

        if resp.status_code != 200:
            raise LLMAPIError(
                f"Step API 返回 {resp.status_code}: {resp.text[:500]}"
            )

        body = resp.json()
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMAPIError(f"Step API 响应格式异常: {body}") from exc

        return text
