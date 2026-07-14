"""分类模块：关键词规则兜底 + LLM Prompt 分类。"""

from __future__ import annotations

from typing import Any


class Classifier:
    """文件分类器。优先关键词命中，否则走 LLM。"""

    def __init__(self, llm_client, rules_path: str | None = None) -> None:
        self.llm = llm_client
        self.rules_path = rules_path

    def classify(self, text: str, filename: str = "") -> dict[str, Any]:
        """TODO(张金宝): 实现规则引擎 + LLM 分类。

        输出格式::

            {
                "category": "课件" | "作业" | "竞赛通知" | "考试通知" | "待确认",
                "confidence": float,
                "course_name": str | None,
            }
        """
        raise NotImplementedError("TODO(张金宝): 分类实现")
