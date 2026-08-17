"""分类模块：关键词规则兜底 + LLM Prompt 分类。"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from filemate.core.categories import CATEGORIES


class Classifier:
    """文件分类器。优先关键词命中，否则走 LLM。

    接口契约（输入/输出）：:

        classify(text: str, filename: str = "") ->
            {"category": str, "confidence": float, "course_name": str | None, "reason": str, "method": str}
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

    def _keyword_hit(self, text: str, filename: str = "") -> tuple[str, float] | None:
        """关键词命中返回 (category, confidence)。未命中返回 None。

        同时匹配解析文本和文件名，提高短文本/模板文件的命中率。
        """
        haystack = (text + " " + filename).lower()
        scores: dict[str, int] = {}
        for category, keywords in self._rules.items():
            for kw in keywords:
                if kw.lower() in haystack:
                    scores[category] = scores.get(category, 0) + 1
        if not scores:
            return None
        best = max(scores, key=scores.get)
        # 若第二名的得分接近第一名（≤1 分之差），说明关键词存在重叠，
        # 降级走 LLM 判断更可靠。
        #
        # 此逻辑为 W3 分类优化的三项措施之一，在 PR #4 review 修复置信度
        # 公式时被一并删除。实测影响：57 份样本准确率 86.79% → 75.47%
        # （LLM 调用 22 → 1 次，21 份模糊样本改由关键词硬猜，净输 6 份）。
        # 置信度数值不参与类别判断（类别只取决于 max(scores)），故公式改动
        # 本身无害，此处仅恢复被误删的降级逻辑，保留新公式。
        runner_up = sorted(scores.values(), reverse=True)
        if len(runner_up) > 1 and runner_up[0] - runner_up[1] <= 1:
            logger.debug("规则模糊: %s vs 其他，降级 LLM", best)
            return None
        # 规则命中的置信度必须高于 LLM 兜底默认值，且随命中数递增。
        best_score = scores[best]
        confidence = min(0.55 + best_score * 0.10, 0.92)
        return best, confidence

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def classify(self, text: str, filename: str = "") -> dict[str, Any]:
        """分类。规则命中 → 直接返回；否则走 LLM。"""
        # 空文本 → 直接待确认
        if not text or not text.strip():
            return {"category": "待确认", "confidence": 0.0, "course_name": None, "reason": "空文本", "method": "none"}

        # 规则兜底
        hit = self._keyword_hit(text, filename)
        if hit:
            category, confidence = hit
            logger.debug("规则命中: %s (%.0f%%)", category, confidence * 100)
            return {"category": category, "confidence": confidence, "course_name": None, "reason": "关键词规则命中", "method": "rule"}

        # 走 LLM
        return self._classify_llm(text, filename)

    def _classify_llm(self, text: str, filename: str) -> dict[str, Any]:
        """调用 LLM 做分类。失败时自动重试一次。"""
        prompt_path = (
            Path(__file__).resolve().parent / "prompts" / "classify.md"
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        snippet = text[:2000]
        user_msg = f"文件名: {filename}\n\n文件内容:\n{snippet}"

        # 第一次 max_tokens=512；失败后重试 max_tokens=1024
        for attempt, max_tokens in [(1, 512), (2, 1024)]:
            try:
                result = self.llm.call_structured(
                    prompt=prompt,
                    messages=[{"role": "user", "content": user_msg}],
                    max_tokens=max_tokens,
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
                    "method": "llm",
                }
            except Exception as exc:
                logger.warning("LLM 分类第%d次失败: %s", attempt, exc)
                continue

        logger.error("LLM 分类在 %d 次尝试后全部失败", 2)
        return {"category": "待确认", "confidence": 0.0, "course_name": None, "reason": "LLM 重试后仍失败", "method": "none"}
