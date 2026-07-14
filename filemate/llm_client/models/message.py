"""LLM 消息模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str
    content: str
    name: str = ""

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d
