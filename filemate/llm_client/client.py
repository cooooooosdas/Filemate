"""LLMClient 统一调用入口。"""

from __future__ import annotations

import json
import logging
import math
import time
import weakref
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit

from .config import LLMConfig
from .exceptions import (
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from .models.response import validated_usage
from .providers.base import BaseLLMProvider
from .providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)
_USAGE: ContextVar[dict[weakref.ReferenceType[Any], tuple[tuple[str, int], ...]] | None] = ContextVar(
    'filemate_llm_usage', default=None,
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
        self._usage_ref = weakref.ref(self)

    def _remember_usage(self, usage: dict[str, int]) -> None:
        """复制上下文状态，避免共享客户端在并发请求间泄漏用量。"""
        retained = {key: value for key, value in (_USAGE.get() or {}).items() if key() is not None}
        retained[self._usage_ref] = tuple(usage.items())
        _USAGE.set(retained)

    # ------------------------------------------------------------------
    # 供应商路由
    # ------------------------------------------------------------------

    @staticmethod
    def _build(config: LLMConfig) -> BaseLLMProvider:
        name = (config.provider or "auto").lower()

        # 自动根据 base_url 检测 provider 类型
        if not name or name == "auto":
            base_url = (config.base_url or "").lower()
            if "deepseek" in base_url:
                name = "deepseek"
            elif "openai" in base_url:
                name = "openai_compatible"
            else:
                raise LLMConfigError(
                    "无法从 LLM_BASE_URL 识别供应商；当前默认使用 DeepSeek，"
                    "请设置 https://api.deepseek.com"
                )

        if name == "deepseek":
            parsed = urlsplit(config.base_url)
            if (
                parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"
                or parsed.netloc.lower() not in {"api.deepseek.com", "api.deepseek.com:443"}
                or parsed.path.rstrip("/") not in {"", "/v1"}
                or parsed.query or parsed.fragment
            ):
                raise LLMConfigError(
                    "DeepSeek 必须使用官方 LLM_BASE_URL=https://api.deepseek.com"
                )
            if config.model != "deepseek-v4-flash":
                raise LLMConfigError(
                    "FileMate 当前统一使用 LLM_MODEL=deepseek-v4-flash"
                )
            return OpenAICompatibleProvider(config)

        if name in ("openai", "openai_compatible"):
            return OpenAICompatibleProvider(config)

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
        retry: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """调用 LLM 并返回纯文本回复。只对可恢复错误（限流/超时）重试。"""
        self._remember_usage({})
        retry = self.config.max_retries if retry is None else retry
        timeout = self.config.timeout if timeout is None else timeout
        if type(retry) is not int or not 1 <= retry <= 3:
            raise LLMConfigError("模型调用次数必须为1至3次")
        if (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= 300
        ):
            raise LLMConfigError("模型调用超时必须为0至300秒之间的有限值")
        if type(max_tokens) is not int or not 1 <= max_tokens <= 65536:
            raise LLMConfigError("模型输出上限必须为1至65536个token")
        if messages is None:
            messages = []
        if prompt:
            messages = [{"role": "system", "content": prompt}] + messages

        last_exc: Exception | None = None
        deadline = time.monotonic() + timeout
        for attempt in range(1, retry + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LLMTimeoutError("模型调用重试预算已耗尽，请稍后重试") from last_exc
            try:
                response = self._provider.chat_with_metadata(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    timeout=remaining,
                )
                self._remember_usage(validated_usage(response.usage))
                return response.text
            except LLMRateLimitError as exc:
                # 只对限流错误重试
                last_exc = exc
                if attempt < retry:
                    wait = min(2 ** attempt, 30)
                    if time.monotonic() + wait >= deadline:
                        raise LLMTimeoutError("模型调用重试预算已耗尽，请稍后重试") from exc
                    logger.warning("模型限流，%ds 后重试 (%d/%d)", wait, attempt, retry)
                    time.sleep(wait)
            except LLMTimeoutError as exc:
                # 只对超时错误重试
                logger.warning("超时，%d/%d 次重试", attempt, retry)
                last_exc = exc
            except LLMAPIError as exc:
                # 不对业务层面错误（配置错误、无效请求等）重试
                logger.error("模型API错误（不重试）: %s", type(exc).__name__)
                raise

        raise LLMAPIError(f"模型调用在{retry}次尝试后仍失败，请稍后重试") from last_exc

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
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:])
        # 去除尾部 ```（可能夹在末尾空行之后）
        cleaned = cleaned.rstrip()
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
        """返回当前上下文最近成功调用的真实计数，未知字段缺省。"""
        return dict((_USAGE.get() or {}).get(self._usage_ref, ()))
