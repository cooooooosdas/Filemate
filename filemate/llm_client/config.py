"""LLM 配置：从环境变量 / .env 加载。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    provider: str = "step_speed"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    timeout: float = 60.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> LLMConfig:
        api_key = os.environ.get("LLM_API_KEY", "")
        base_url = os.environ.get("LLM_BASE_URL", "")
        model = os.environ.get("LLM_MODEL", "")
        logger.info(f"[LLM Config] API Key: {'已设置' if api_key else '未设置'}, Base URL: {base_url or '未设置'}, Model: {model or '未设置'}")
        return cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
