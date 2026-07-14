"""LLM 统一封装层。所有模块通过此层调用，不直接依赖具体供应商。"""
from .client import LLMClient
from .config import LLMConfig
__all__ = ["LLMClient", "LLMConfig"]
