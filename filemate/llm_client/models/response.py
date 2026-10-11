"""LLM 响应模型。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


def validated_usage(value: Any) -> dict[str, int]:
    """保留供应商实际返回的合法计数，不将未知用量补成零。"""
    if not isinstance(value, dict):
        return {}
    return {
        name: count for name in ('prompt_tokens', 'completion_tokens', 'total_tokens')
        if type(count := value.get(name)) is int and 0 <= count <= 2**31 - 1
    }


def safe_request_id(value: Any) -> str:
    """只接受有界标识，避免把供应商响应正文或头注入日志。"""
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value) else ''


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    request_id: str = ""

    @property
    def parsed(self) -> dict[str, Any]:
        return json.loads(self.text)
