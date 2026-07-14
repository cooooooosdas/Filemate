"""多里程碑识别：从长通知中提取所有时间节点。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MilestoneDetector:
    """多里程碑识别器。

    接口契约::

        detect(text: str) -> [
            {"event": str, "date": "YYYY-MM-DD", "order": int},
            ...
        ]
    """

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def detect(self, text: str) -> list[dict[str, Any]]:
        """从文本中提取所有关键时间节点。空文本返回空列表。"""
        if not text or not text.strip():
            return []

        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "milestone.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:6000]

        try:
            result = self.llm.call_structured(
                prompt=prompt,
                messages=[{"role": "user", "content": snippet}],
            )
            if not isinstance(result, list):
                logger.debug("里程碑识别返回非数组: %s", type(result))
                return []
            # 规范：只保留有 date 字段的记录，按 order 排序
            events = []
            for idx, item in enumerate(result):
                event = item.get("event", "")
                date = item.get("date", "")
                order = item.get("order", idx + 1)
                if event and self._looks_like_date(date):
                    events.append({
                        "event": str(event).strip(),
                        "date": date.strip(),
                        "order": int(order),
                    })
            events.sort(key=lambda x: x["order"])
            logger.debug("识别到 %d 个里程碑", len(events))
            return events
        except Exception as exc:
            logger.error("里程碑识别失败: %s", exc)
            return []

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_date(value: str) -> bool:
        import re
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value).strip()))
