"""LLM 调用异常体系。"""


class LLMError(Exception):
    """所有 LLM 异常的基类。"""


class LLMAPIError(LLMError):
    """远程 API 返回错误。"""


class LLMTimeoutError(LLMError):
    """调用超时。"""


class LLMRateLimitError(LLMAPIError):
    """触发限流。"""


class LLMConfigError(LLMError):
    """配置缺失或不合法。"""
