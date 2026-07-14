"""实体抽取：从文本中提取课程名、截止时间等关键信息。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 输出字段契约（与技术决策定稿 §4.2 保持一致）
ENTITY_FIELDS = ("course_name", "task_description", "deadline", "location", "extra_entities")


class EntityExtractor:
    """实体抽取器。

    接口契约::

        extract(text: str) -> {
            "course_name": str | None,
            "task_description": str | None,
            "deadline": "YYYY-MM-DD" | None,
            "location": str | None,
            "extra_entities": dict,
        }
    """

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def extract(self, text: str) -> dict[str, Any]:
        """提取实体。空文本直接返回空结果。"""
        if not text or not text.strip():
            return {k: None for k in ENTITY_FIELDS[:-1]} | {"extra_entities": {}}

        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "extract.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:4000]

        try:
            result = self.llm.call_structured(
                prompt=prompt,
                messages=[{"role": "user", "content": snippet}],
            )
            # 规范输出
            out: dict[str, Any] = {}
            for field in ENTITY_FIELDS[:-1]:
                val = result.get(field)
                out[field] = val if val else None
            # deadline 格式校验
            deadline = out.get("deadline")
            if deadline and not self._looks_like_date(deadline):
                logger.debug("deadline 格式异常，丢弃: %s", deadline)
                out["deadline"] = None
            out["extra_entities"] = result.get("extra_entities") or {}
            return out
        except Exception as exc:
            logger.error("实体抽取失败: %s", exc)
            return {k: None for k in ENTITY_FIELDS[:-1]} | {"extra_entities": {}}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_date(value: str) -> bool:
        import re
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()))
