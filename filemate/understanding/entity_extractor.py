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
        """提取实体。空文本直接返回空结果。失败时自动重试一次。"""
        if not text or not text.strip():
            return {k: None for k in ENTITY_FIELDS[:-1]} | {"extra_entities": {}}

        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "extract.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:4000]

        # W4 联调发现两类失败，均导致整份样本字段全丢：
        #   1. LLM 返回空字符串 '' —— 原 2 次重试顶不住，需 3 次
        #   2. JSON 在 extra_entities 嵌套对象处被截断 —— max_tokens 不足
        # 故重试 2→3 次，max_tokens 起点 1000→1500 并递增到 4000。
        attempts = [(1, 1500), (2, 2500), (3, 4000)]
        for attempt, max_tokens in attempts:
            try:
                result = self.llm.call_structured(
                    prompt=prompt,
                    messages=[{"role": "user", "content": snippet}],
                    max_tokens=max_tokens,
                )
                if not isinstance(result, dict):
                    logger.debug("实体抽取返回非字典: %s", type(result))
                    continue
                # 规范输出：忽略 LLM 返回的 file_type 字段（内部判断用）
                result.pop("file_type", None)
                out: dict[str, Any] = {}
                for field in ENTITY_FIELDS[:-1]:
                    val = result.get(field)
                    out[field] = val if val else None
                # deadline 格式校验
                deadline = out.get("deadline")
                if deadline and not self._looks_like_date(deadline):
                    logger.debug("deadline 格式异常，丢弃: %s", deadline)
                    out["deadline"] = None
                out["extra_entities"] = self._flatten(result.get("extra_entities"))
                return out
            except Exception as exc:
                logger.warning("实体抽取第%d次失败: %s", attempt, exc)
                continue

        logger.error("实体抽取在 %d 次尝试后全部失败", len(attempts))
        return {k: None for k in ENTITY_FIELDS[:-1]} | {"extra_entities": {}}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_date(value: str) -> bool:
        import re
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()))

    @staticmethod
    def _flatten(raw: Any) -> dict[str, Any]:
        """把 extra_entities 压平成一层键值对。

        LLM 有时在 extra_entities 里嵌套子对象（如 `"contact": {"name": ...}`），
        既会撑爆 max_tokens 导致 JSON 截断，也让下游读取不可预期。此处压平为
        `contact.name` 形式，列表转逗号连接的字符串。
        """
        if not isinstance(raw, dict):
            return {}
        flat: dict[str, Any] = {}
        for key, val in raw.items():
            if isinstance(val, dict):
                for sub_key, sub_val in val.items():
                    flat[f"{key}.{sub_key}"] = sub_val
            elif isinstance(val, list):
                flat[key] = ", ".join(str(v) for v in val)
            else:
                flat[key] = val
        return flat
