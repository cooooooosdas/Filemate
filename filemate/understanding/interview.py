"""AI 模拟面试问题编排与回答评估。"""

from __future__ import annotations

import json
from typing import Any

QUESTION_BANK = {
    "求职面试": [
        "请用一分钟做自我介绍，并说明你与目标岗位的匹配点。",
        "请讲一个你解决复杂问题的经历，你具体采取了哪些行动？",
        "当团队意见冲突时，你如何推动项目继续前进？",
        "请介绍一个最能体现你专业能力的项目，并说明结果。",
        "如果入职后遇到陌生任务，你会如何快速上手？",
    ],
    "竞赛答辩": [
        "请用一分钟说明项目解决的核心痛点与目标用户。",
        "与现有方案相比，你们最关键的创新点是什么？",
        "系统的核心技术链路是什么，为什么选择这套方案？",
        "你们如何证明项目有效，而不是只完成了功能展示？",
        "如果获得进一步支持，下一阶段最优先解决什么问题？",
    ],
    "保研复试": [
        "请介绍你的研究兴趣以及形成这一兴趣的经历。",
        "请说明你参与过的一个项目和你的具体贡献。",
        "遇到实验结果与预期不符时，你会如何分析？",
        "请解释一个你最熟悉的专业概念，并举例说明。",
        "你未来三年的学习与研究计划是什么？",
    ],
}


def build_questions(scenario: str, target_role: str) -> list[str]:
    """生成一组稳定可演示的问题。"""
    questions = list(QUESTION_BANK.get(scenario, QUESTION_BANK["求职面试"]))
    if target_role.strip():
        questions[0] = f"请用一分钟做自我介绍，并说明你为什么适合{target_role.strip()}。"
    return questions


class InterviewEvaluator:
    """使用 LLM 评估回答，失败时提供可用的规则回退。"""

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def evaluate(self, question: str, answer: str, target_role: str) -> dict[str, Any]:
        """返回总分、维度分和改进建议。"""
        prompt = f"""你是严谨的大学生模拟面试官。请评估回答，只返回 JSON。
目标岗位/方向：{target_role}
问题：{question}
回答：{answer}
JSON 结构：{{"score": 0-100, "dimensions": {{"内容": 0-100, "结构": 0-100, "表达": 0-100, "岗位匹配": 0-100}}, "feedback": "两句具体建议"}}"""
        try:
            response = self.llm.call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
            )
            content = getattr(response, "content", str(response)).strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(content)
            dimensions = {
                key: max(0.0, min(100.0, float(value)))
                for key, value in result.get("dimensions", {}).items()
            }
            return {
                "score": max(0.0, min(100.0, float(result["score"]))),
                "dimensions": dimensions,
                "feedback": str(result.get("feedback", "请补充具体行动与结果。")),
            }
        except Exception:  # noqa: BLE001 - 面试演示必须在模型不可用时降级
            length_score = min(90.0, 35.0 + len(answer.strip()) * 0.35)
            return {
                "score": round(length_score, 2),
                "dimensions": {
                    "内容": round(length_score, 2),
                    "结构": max(35.0, round(length_score - 8, 2)),
                    "表达": min(88.0, round(length_score + 3, 2)),
                    "岗位匹配": max(30.0, round(length_score - 12, 2)),
                },
                "feedback": "建议使用“情境—行动—结果”结构，并补充可量化成果。",
            }
