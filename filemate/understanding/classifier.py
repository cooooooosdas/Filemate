"""分类模块：关键词规则兜底 + LLM Prompt 分类。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 分类类别（与技术决策定稿 §4.1 保持一致）
CATEGORIES = ("课件", "作业", "竞赛通知", "考试通知", "待确认")


class Classifier:
    """文件分类器。优先关键词命中，否则走 LLM。

    接口契约（输入/输出）：:

        classify(text: str, filename: str = "") ->
            {"category": str, "confidence": float, "course_name": str | None, "reason": str}
    """

    def __init__(self, llm_client, rules_path: str | None = None) -> None:
        self.llm = llm_client
        self.rules_path = rules_path or self._default_rules_path()
        self._rules: dict[str, list[str]] = {}
        self._load_rules()

    # ------------------------------------------------------------------
    # 规则引擎
    # ------------------------------------------------------------------

    def _default_rules_path(self) -> Path:
        return (
            Path(__file__).resolve().parent / "rules" / "keywords.json"
        )

    def _load_rules(self) -> None:
        p = Path(self.rules_path)
        if not p.exists():
            logger.warning("规则文件不存在: %s", p)
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._rules = data.get("categories", {})
            logger.info("已加载 %d 条分类规则", sum(len(v) for v in self._rules.values()))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("规则文件加载失败: %s", exc)

    def _keyword_hit(self, text: str) -> tuple[str, float] | None:
        """关键词命中返回 (category, confidence)。未命中返回 None。"""
        haystack = (text + " ").lower()
        scores: dict[str, int] = {}
        for category, keywords in self._rules.items():
            for kw in keywords:
                if kw.lower() in haystack:
                    scores[category] = scores.get(category, 0) + 1
        if not scores:
            return None
        best = max(scores, key=scores.get)
        # 命中数越多置信度越高，单次命中也 ≥ 0.83
        confidence = min(0.75 + scores[best] * 0.08, 0.95)
        return best, confidence

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def classify(self, text: str, filename: str = "") -> dict[str, Any]:
        """分类。规则命中 → 直接返回；否则走 LLM。"""
        # 空文本 → 直接待确认
        if not text or not text.strip():
            return {"category": "待确认", "confidence": 0.0, "course_name": None, "reason": "空文本"}

        # 规则兜底
        hit = self._keyword_hit(text)
        if hit:
            category, confidence = hit
            logger.debug("规则命中: %s (%.0f%%)", category, confidence * 100)
            return {"category": category, "confidence": confidence, "course_name": None, "reason": "关键词规则命中"}

        # 走 LLM
        return self._classify_llm(text, filename)

    def _classify_llm(self, text: str, filename: str) -> dict[str, Any]:
        """调用 LLM 做分类。"""
        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "classify.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:2000]
        user_msg = f"文件名: {filename}\n\n文件内容:\n{snippet}"

        try:
            result = self.llm.call_structured(
                prompt=prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            # 规范输出
            category = result.get("category", "待确认")
            if category not in CATEGORIES:
                category = "待确认"
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            return {
                "category": category,
                "confidence": confidence,
                "course_name": result.get("course_name"),
                "reason": result.get("reason", ""),
            }
        except Exception as exc:
            logger.error("LLM 分类失败: %s", exc)
            return {"category": "待确认", "confidence": 0.0, "course_name": None, "reason": f"LLM 失败: {exc}"}
