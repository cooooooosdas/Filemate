"""仅在单次模型请求内使用浏览器提供的凭据。"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

REQUEST_API_KEY: ContextVar[str] = ContextVar("filemate_request_api_key", default="")
MODEL_PATHS = (
    r"/api/llm/test", r"/process", r"/ai/(summarize|knowledge-cards|questions|notes|study-plan|chat)",
    r"/knowledge/sources/[^/]+/artifacts", r"/api/knowledge-graph/drafts",
    r"/interviews", r"/interviews/[^/]+/answers",
    r"/interviews/[^/]+/turns/[^/]+/analyze",
    r"/api/programming/submissions/[^/]+/review",
    r"/api/resume/generate",
)


def is_model_request(method: str, path: str) -> bool:
    """只对现役模型生成路由开放临时凭据。"""
    return method == "POST" and any(re.fullmatch(pattern, path) for pattern in MODEL_PATHS)


def validate_api_key(value: str) -> str:
    """拒绝空白及不能安全放入HTTP请求头的密钥。"""
    value = value.strip()
    if not re.fullmatch(r"[\x21-\x7e]{10,512}", value):
        raise ValueError("API 密钥格式无效，请只粘贴密钥正文")
    return value


@contextmanager
def model_request_key(value: str) -> Iterator[None]:
    """结束请求后恢复上下文，不修改全局环境或凭据库。"""
    token = REQUEST_API_KEY.set(value)
    try:
        yield
    finally:
        REQUEST_API_KEY.reset(token)
