"""LLM 配置：从本机安全凭据与环境变量加载。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .credential_store import resolve_api_key
from .request_credentials import REQUEST_API_KEY


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = field(default="", repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout: float = 60.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> LLMConfig:
        request_key = REQUEST_API_KEY.get()
        if request_key:
            return cls(api_key=request_key)
        api_key, _ = resolve_api_key()
        return cls(
            provider=os.environ.get("LLM_PROVIDER", "deepseek"),
            api_key=api_key,
            base_url=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("LLM_MODEL", "deepseek-v4-flash"),
        )
