"""解析器注册表。"""

from typing import Type

_REGISTRY: dict[str, type] = {}


def register(suffix: str, cls: type) -> None:
    _REGISTRY[suffix.lower()] = cls


def get_parser(suffix: str):
    cls = _REGISTRY.get(suffix.lower())
    if cls is None:
        raise ValueError(f"不支持的格式: .{suffix}")
    return cls()
