"""AI 学习工具单元测试。"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from filemate.understanding.ai_tools import AIChatbot, StudyPlanGenerator


class FakeLLM:
    """返回固定学习计划的测试模型。"""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.messages: list[dict[str, str]] = []

    def call(self, *, messages, max_tokens):
        self.messages = messages
        assert max_tokens == 6000
        return f"```json\n{json.dumps(self.payload, ensure_ascii=False)}\n```"


def test_study_plan_generator_normalizes_plan() -> None:
    exam_date = (date.today() + timedelta(days=7)).isoformat()
    llm = FakeLLM(
        {
            "title": "数据结构冲刺计划",
            "strategy": "先理解，再主动回忆",
            "topics": [{"name": "图", "priority": "high", "reason": "重点"}],
            "daily_plan": [
                {
                    "date": (date.today() + timedelta(days=1)).isoformat(),
                    "focus": "图遍历",
                    "tasks": "手写 BFS 与 DFS",
                    "duration_minutes": 120,
                    "review_method": "主动回忆",
                }
            ],
            "checkpoints": [],
        }
    )

    plan = StudyPlanGenerator(llm).generate(
        "图的存储结构包括邻接矩阵和邻接表。",
        exam_date,
        daily_minutes=60,
        weak_topics=["图"],
    )

    assert plan["exam_date"] == exam_date
    assert plan["daily_plan"][0]["tasks"] == ["手写 BFS 与 DFS"]
    assert plan["daily_plan"][0]["duration_minutes"] == 60
    assert "薄弱知识点：图" in llm.messages[0]["content"]


@pytest.mark.parametrize(
    ("exam_date", "daily_minutes", "message"),
    [
        ("not-a-date", 60, "YYYY-MM-DD"),
        (date.today().isoformat(), 60, "晚于今天"),
        ((date.today() + timedelta(days=2)).isoformat(), 10, "15 到 480"),
    ],
)
def test_study_plan_generator_validates_input(
    exam_date: str,
    daily_minutes: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        StudyPlanGenerator(FakeLLM({})).generate(
            "课程资料",
            exam_date,
            daily_minutes=daily_minutes,
        )


def test_study_plan_generator_rejects_empty_daily_plan() -> None:
    exam_date = (date.today() + timedelta(days=3)).isoformat()
    with pytest.raises(ValueError, match="每日计划"):
        StudyPlanGenerator(FakeLLM({"daily_plan": []})).generate(
            "课程资料",
            exam_date,
        )


class ChatLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def call(self, *, messages, max_tokens):
        self.messages = messages
        assert max_tokens == 2000
        return "你认为这个结论依赖哪个前提？[引用1]"


def test_chatbot_socratic_mode_uses_guided_prompt() -> None:
    llm = ChatLLM()
    answer = AIChatbot(llm).answer(
        "我不理解三次握手",
        "[引用1] TCP 通过三次握手确认双方收发能力。",
        mode="socratic",
    )

    assert "苏格拉底教学法" in llm.messages[0]["content"]
    assert "不要直接给最终答案" in llm.messages[0]["content"]
    assert "[引用1]" in answer
