"""ModuleRegistry - 全局单例模块管理器。

FileMate 核心组件的全局注册表，提供：
- LLM Client 复用
- Parser 策略选择
- OCR 引擎管理
- Storage 持久化

设计原则：
- 延迟初始化（懒加载）
- 线程安全
- 可配置替换
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Self

from filemate.execution.file_ops import FileOps
from filemate.execution.scheduler import CalendarBuilder
from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient, LLMConfig
from filemate.llm_client.request_credentials import REQUEST_API_KEY
from filemate.perception import FileParser, OCRBackend

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """全局单例模块注册表。

    使用方式::

        registry = ModuleRegistry.get_instance()
        llm = registry.get_llm()
        parser = registry.get_parser()
        storage = registry.get_storage()
    """

    _instance: ModuleRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._llm: LLMClient | None = None
        self._parser: FileParser | None = None
        self._ocr: OCRBackend | None = None
        self._storage: SQLiteStorage | None = None
        self._calendar: CalendarBuilder | None = None
        self._file_ops: FileOps | None = None
        self._config: LLMConfig | None = None
        self._initialized = False

    @classmethod
    def get_instance(cls) -> ModuleRegistry:
        """获取全局单例实例（线程安全）。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置实例（主要用于测试）。"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._initialized = False
                cls._instance._llm = None
                cls._instance._parser = None
                cls._instance._ocr = None
                cls._instance._storage = None
                cls._instance._calendar = None
                cls._instance._file_ops = None

    # =====================================================================
    # LLM
    # =====================================================================

    def get_llm(self, force_refresh: bool = False) -> LLMClient:
        """获取 LLM 客户端（延迟初始化）。"""
        if REQUEST_API_KEY.get():
            # 请求专属密钥不能写进跨账号复用的全局客户端或配置。
            return LLMClient(LLMConfig.from_env())
        if self._llm is None or force_refresh:
            if self._config is None:
                self._config = LLMConfig.from_env()
            self._llm = LLMClient(self._config)
            logger.info("LLM 客户端初始化完成: provider=%s", self._config.provider)
        return self._llm

    def set_llm_config(self, config: LLMConfig) -> None:
        """设置 LLM 配置（将在下次 get_llm 时生效）。"""
        self._config = config
        self._llm = None  # 强制重新初始化
        logger.info("LLM 配置已更新")

    # =====================================================================
    # Parser
    # =====================================================================

    def get_parser(self, force_refresh: bool = False) -> FileParser:
        """获取文件解析器。"""
        if self._parser is None or force_refresh:
            self._parser = FileParser()
            logger.info("FileParser 初始化完成")
        return self._parser

    # =====================================================================
    # OCR
    # =====================================================================

    def get_ocr(self) -> OCRBackend:
        """获取 OCR 引擎。"""
        if self._ocr is None:
            self._ocr = OCRBackend()
            logger.info("OCR 引擎初始化完成: available=%s", self._ocr.available)
        return self._ocr

    # =====================================================================
    # Storage
    # =====================================================================

    def get_storage(self, db_path: str = "filemate.db", force_refresh: bool = False) -> SQLiteStorage:
        """获取 SQLite 存储（延迟初始化）。"""
        if self._storage is None or force_refresh:
            self._storage = SQLiteStorage(db_path)
            self._storage.init_schema()
            logger.info("SQLiteStorage 初始化完成: db_path=%s", db_path)
        return self._storage

    def set_storage_path(self, db_path: str) -> None:
        """设置数据库路径（将在下次 get_storage 时生效）。"""
        self._storage = None  # 强制重新初始化
        logger.info("存储路径已更新: %s", db_path)

    # =====================================================================
    # Calendar
    # =====================================================================

    def get_calendar(self) -> CalendarBuilder:
        """获取日历构建器。"""
        if self._calendar is None:
            self._calendar = CalendarBuilder()
            logger.info("CalendarBuilder 初始化完成")
        return self._calendar

    # =====================================================================
    # FileOps
    # =====================================================================

    def get_file_ops(self) -> FileOps:
        """获取文件操作工具。"""
        if self._file_ops is None:
            self._file_ops = FileOps()
            logger.info("FileOps 初始化完成")
        return self._file_ops

    # =====================================================================
    # Utility
    # =====================================================================

    def reload_all(self) -> None:
        """重新加载所有模块（配置变更时使用）。"""
        logger.info("开始重新加载所有模块...")
        self.get_llm(force_refresh=True)
        self.get_parser(force_refresh=True)
        self.get_storage(force_refresh=True)
        logger.info("所有模块重新加载完成")

    def get_stats(self) -> dict[str, Any]:
        """获取模块状态统计。"""
        return {
            "llm_initialized": self._llm is not None,
            "parser_initialized": self._parser is not None,
            "ocr_available": self._ocr.available if self._ocr else False,
            "storage_initialized": self._storage is not None,
            "config": {
                "provider": self._config.provider if self._config else None,
                "model": self._config.model if self._config else None,
            } if self._config else None,
        }

    # =====================================================================
    # Context Manager
    # =====================================================================

    def __enter__(self) -> Self:
        """支持 with 语句（自动初始化）。"""
        self.get_llm()
        self.get_parser()
        self.get_storage()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出时保持模块实例复用，不主动清理。"""


# 便捷函数
def get_registry() -> ModuleRegistry:
    """获取全局 ModuleRegistry 实例的快捷方式。"""
    return ModuleRegistry.get_instance()


def get_llm() -> LLMClient:
    """获取 LLM 客户端的快捷方式。"""
    return ModuleRegistry.get_instance().get_llm()


def get_parser() -> FileParser:
    """获取文件解析器的快捷方式。"""
    return ModuleRegistry.get_instance().get_parser()


def get_storage(db_path: str = "filemate.db") -> SQLiteStorage:
    """获取 SQLite 存储的快捷方式。"""
    return ModuleRegistry.get_instance().get_storage(db_path)
