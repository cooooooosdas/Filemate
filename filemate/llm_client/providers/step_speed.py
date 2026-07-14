"""Step 3.7 Speed 供应商实现。"""

from .base import BaseLLMProvider
from ..config import LLMConfig
from ..exceptions import LLMConfigError


class StepSpeedProvider(BaseLLMProvider):
    """对接用户自有 Step 3.7 Speed 大批量调用渠道。"""

    def __init__(self, config: LLMConfig) -> None:
        if not config.api_key:
            raise LLMConfigError("LLM_API_KEY 未配置，请在 .env 中设置")
        self.config = config

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> str:
        """TODO(胡希): 对接 Step API 端点并返回纯文本。"""
        raise NotImplementedError("TODO(胡希): 对接 Step 3.7 Speed API")
