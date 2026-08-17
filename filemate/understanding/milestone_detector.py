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
        """从文本中提取所有关键时间节点。空文本返回空列表。失败时自动重试一次。"""
        if not text or not text.strip():
            return []

        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "milestone.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:6000]

        # 第一次：max_tokens=2048；失败后重试 max_tokens=4096
        for attempt, max_tokens in [(1, 2048), (2, 4096)]:
            try:
                result = self.llm.call_structured(
                    prompt=prompt,
                    messages=[{"role": "user", "content": snippet}],
                    max_tokens=max_tokens,
                )
                if not isinstance(result, list):
                    logger.debug("里程碑识别返回非数组: %s", type(result))
                    continue
                # 规范：只保留有 date 字段的记录，按 order 排序
                # 去重键用 (event, date)：同一天可能有多个不同节点
                # （如"报名截止"和"初赛开始"同为 2026-08-01），只按 date 去重会丢事件
                events = []
                seen: set[tuple[str, str]] = set()
                for idx, item in enumerate(result):
                    event = str(item.get("event", "")).strip()
                    date = str(item.get("date", "")).strip()
                    order = item.get("order", idx + 1)
                    key = (event, date)
                    if event and self._looks_like_date(date) and key not in seen:
                        events.append({
                            "event": event,
                            "date": date,
                            "order": self._safe_order(order, idx),
                        })
                        seen.add(key)
                events.sort(key=lambda x: x["order"])
                # 强制重排为连续序号
                for i, ev in enumerate(events, 1):
                    ev["order"] = i
                logger.debug("识别到 %d 个里程碑", len(events))
                return events
            except Exception as exc:
                logger.warning("里程碑识别第%d次失败: %s", attempt, exc)
                continue

        logger.error("里程碑识别在 %d 次尝试后全部失败", 2)
        return []

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_date(value: str) -> bool:
        import re
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value).strip()))

    @staticmethod
    def _safe_order(value: Any, idx: int) -> int:
        """order 转 int。LLM 偶发返回"第一"/null，此时退回下标，避免整批丢弃。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.debug("order 非法，退回下标: %r", value)
            return idx + 1
