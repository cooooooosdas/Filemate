"""DeepSeek 等 OpenAI 兼容模型的 HTTP 适配器。"""

from __future__ import annotations

import logging
from typing import Any

import requests

from ..config import LLMConfig
from ..exceptions import (
    LLMAccessError,
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    """通过 Chat Completions API 调用 OpenAI 兼容模型。"""

    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise LLMConfigError("DeepSeek API 密钥未配置，请在应用设置中填写")
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
        """发起一次 Chat Completions 调用并返回纯文本。"""
        base_url_lower = self.config.base_url.lower()
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if "deepseek" in base_url_lower:
            # 结构化抽取依赖最终 content，默认关闭思考以稳定延迟和输出长度。
            payload["thinking"] = {"type": "disabled"}
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug("LLM API 调用: %s | messages=%d 条", url, len(messages))

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.Timeout as exc:
            raise LLMTimeoutError(f"LLM API 调用超时（{timeout}s）") from exc
        except requests.ConnectionError as exc:
            raise LLMAPIError(f"LLM API 连接失败: {exc}") from exc

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            raise LLMRateLimitError(f"触发限流，{retry_after}s 后重试")

        if resp.status_code in {401, 402, 403}:
            raise LLMAccessError(
                f"LLM API 访问被拒绝（{resp.status_code}），请检查密钥、余额和账号权限: "
                f"{resp.text[:300]}"
            )

        if resp.status_code != 200:
            raise LLMAPIError(
                f"LLM API 返回 {resp.status_code}: {resp.text[:500]}"
            )

        body = resp.json()
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMAPIError(f"LLM API 响应格式异常: {body}") from exc

        return text
