"""解析器注册表。"""

from __future__ import annotations

from typing import Any

_REGISTRY: dict[str, Any] = {}


def register(suffix: str, cls: Any) -> None:
    """注册一个解析器。后缀不区分大小写，统一存小写。"""
    _REGISTRY[suffix.lower()] = cls


def get_parser(suffix: str):
    """根据后缀返回解析器实例。未注册则抛 ValueError。"""
    suffix = suffix.lower()

    if suffix in _REGISTRY:
        parser = _REGISTRY[suffix]
        return parser() if isinstance(parser, type) else parser

    # 懒加载：尝试导入对应模块
    _try_lazy_import(suffix)

    if suffix in _REGISTRY:
        parser = _REGISTRY[suffix]
        return parser() if isinstance(parser, type) else parser

    raise ValueError(f"不支持的格式: .{suffix}")


def _try_lazy_import(suffix: str) -> None:
    """按需导入解析器模块（延迟到真正使用时再 import，减少启动时间）。"""
    mapping = {
        "pdf": ".pdf",
        "docx": ".word",
        "doc": ".word",
        "pptx": ".ppt",
        "ppt": ".ppt",
        "txt": ".txt",
    }
    module_path = mapping.get(suffix)
    if module_path:
        try:
            from importlib import import_module
            import_module(module_path, package=__name__)
        except ImportError:
            pass
