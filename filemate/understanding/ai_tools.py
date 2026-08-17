"""AI工具箱：PDF摘要、知识卡生成、题目提取、笔记提取、AI问答。"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _parse_json_result(result: Any) -> Any:
    """解析模型返回的 JSON，并兼容 Markdown 代码块。"""
    content = getattr(result, "content", str(result)).strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())


class AISummarizer:
    """AI摘要生成器。从PDF/文档中生成简洁的笔记摘要。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def summarize(self, text: str, max_length: int = 500) -> str:
        """生成文档摘要。

        Parameters
        ----------
        text : str
            文档原文（可包含多页内容）
        max_length : int
            摘要最大字数，默认500

        Returns
        -------
        str
            生成的摘要文本
        """
        if not text or not text.strip():
            return ""

        prompt = f"""你是一个专业的学习助手。请仔细阅读以下文档内容，然后生成一个简洁、准确的摘要。

要求：
1. 提取文档的核心要点
2. 保持逻辑连贯性
3. 摘要长度控制在{max_length}字以内
4. 使用清晰的中文表达

文档内容：
---
{text[:8000]}
---

请直接输出摘要，不要添加任何前缀或解释："""

        try:
            # 使用messages而不是prompt，避免云知声API的兼容性问题
            messages = [{"role": "user", "content": prompt}]
            result = self.llm.call(messages=messages, max_tokens=2000)
            return str(result).strip() if result else ""
        except Exception as exc:
            logger.error("摘要生成失败: %s", exc)
            return f"摘要生成失败: {exc}"


class KnowledgeCardGenerator:
    """知识卡生成器。从文档中智能生成知识卡片（Anki格式）。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def generate_cards(
        self,
        text: str,
        num_cards: int = 10,
        card_format: str = "front_back",
    ) -> list[dict[str, str]]:
        """从文档中生成知识卡片。

        Parameters
        ----------
        text : str
            文档原文
        num_cards : int
            生成的卡片数量，默认10
        card_format : str
            卡片格式："front_back"（正面/背面）或 "qa"（问答）

        Returns
        -------
        list[dict]
            知识卡片列表，每张卡片包含 "front" 和 "back" 字段
        """
        if not text or not text.strip():
            return []

        if card_format == "qa":
            prompt = f"""你是一个专业的学习助手。请从以下文档中提取关键知识点，生成{num_cards}个问答形式的知识卡片。

要求：
1. 问题要简洁明确，覆盖核心知识点
2. 答案要准确、完整
3. 每张卡片包含 "question"（问题）和 "answer"（答案）字段
4. 直接返回JSON数组格式，不要添加任何说明

文档内容：
---
{text[:8000]}
---

请直接返回JSON数组："""
        else:
            prompt = f"""你是一个专业的学习助手。请从以下文档中提取关键知识点，生成{num_cards}个知识卡片。

要求：
1. 正面（front）是问题或概念，背面（back）是答案或解释
2. 每张卡片要独立、完整
3. 每张卡片包含 "front"（正面）和 "back"（背面）字段
4. 直接返回JSON数组格式，不要添加任何说明

文档内容：
---
{text[:8000]}
---

请直接返回JSON数组："""

        try:
            result = self.llm.call(messages=[{"role": "user", "content": prompt}], max_tokens=4000)
            content = getattr(result, "content", str(result))

            # 尝试解析JSON
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            cards = json.loads(content.strip())

            # 规范化字段名
            normalized = []
            for card in cards:
                if isinstance(card, dict):
                    if "question" in card and "answer" in card:
                        normalized.append({"front": card["question"], "back": card["answer"]})
                    elif "front" in card and "back" in card:
                        normalized.append({"front": card["front"], "back": card["back"]})
                    elif "front" in card:
                        normalized.append({"front": card["front"], "back": card.get("back", "")})
                    else:
                        # 尝试从其他字段推断
                        keys = list(card.keys())
                        if len(keys) >= 2:
                            normalized.append({"front": str(card[keys[0]]), "back": str(card[keys[1]])})
                        elif len(keys) == 1:
                            normalized.append({"front": str(card[keys[0]]), "back": ""})

            return normalized[:num_cards]
        except json.JSONDecodeError as exc:
            logger.error("知识卡JSON解析失败: %s, content: %s", exc, content[:200])
            return []
        except Exception as exc:
            logger.error("知识卡生成失败: %s", exc)
            return []


class QuestionExtractor:
    """题目提取器。从文档中智能提取练习题目。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def extract_questions(
        self,
        text: str,
        question_types: Optional[list[str]] = None,
        num_questions: int = 10,
    ) -> list[dict[str, Any]]:
        """从文档中提取练习题目。

        Parameters
        ----------
        text : str
            文档原文
        question_types : list[str], optional
            题目类型筛选，可选：["选择题", "填空题", "判断题", "简答题", "计算题"]
            默认全部类型
        num_questions : int
            生成的题目数量，默认10

        Returns
        -------
        list[dict]
            题目列表，每道题包含 "type"（类型）、"question"（题目）、"options"（选项，如适用）、
            "answer"（答案）、"explanation"（解析，如适用）等字段
        """
        if not text or not text.strip():
            return []

        type_filter = ""
        if question_types:
            type_filter = f"只提取以下类型的题目：{', '.join(question_types)}"

        prompt = f"""你是一个专业的教育助手。请从以下文档中提取练习题目，{type_filter}。

要求：
1. 题目要从文档内容中生成，确保准确性
2. 每道题包含 "type"（类型）、"question"（题目）、"answer"（答案）
3. 选择题需要包含 "options" 字段（ABCD选项）
4. 简答题需要包含 "answer"（参考答案）
5. 返回 {num_questions} 道题目
6. 直接返回JSON数组格式，不要添加任何说明

文档内容：
---
{text[:8000]}
---

请直接返回JSON数组："""

        try:
            result = self.llm.call(messages=[{"role": "user", "content": prompt}], max_tokens=4000)
            content = getattr(result, "content", str(result))

            # 清理JSON格式
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            questions = json.loads(content.strip())

            # 规范化题目格式
            normalized = []
            for q in questions:
                if isinstance(q, dict):
                    normalized.append({
                        "type": q.get("type", "简答题"),
                        "question": q.get("question", q.get("题目", "")),
                        "options": q.get("options", q.get("选项", [])),
                        "answer": q.get("answer", q.get("答案", "")),
                        "explanation": q.get("explanation", q.get("解析", "")),
                    })

            return normalized[:num_questions]
        except json.JSONDecodeError as exc:
            logger.error("题目JSON解析失败: %s, content: %s", exc, content[:200])
            return []
        except Exception as exc:
            logger.error("题目提取失败: %s", exc)
            return []


class NoteExtractor:
    """笔记提取器。从文档中提取结构化笔记。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def extract_notes(
        self,
        text: str,
        format: str = "outline",
    ) -> dict[str, Any]:
        """从文档中提取结构化笔记。

        Parameters
        ----------
        text : str
            文档原文
        format : str
            笔记格式："outline"（大纲）、"markdown"（Markdown）、"mindmap"（思维导图）

        Returns
        -------
        dict
            结构化笔记，包含 "title"（标题）、"sections"（章节列表）等字段
        """
        if not text or not text.strip():
            return {"title": "", "sections": [], "format": format}

        prompt = f"""你是一个专业的学习助手。请从以下文档中提取结构化笔记。

要求：
1. 提取文档的标题和主要章节
2. 每个章节包含标题和要点
3. 使用Markdown格式
4. 返回包含 "title"（文档标题）、"sections"（章节列表）、"format"（格式）的JSON对象

笔记格式：{format}

文档内容：
---
{text[:8000]}
---

请直接返回JSON对象："""

        try:
            result = self.llm.call(messages=[{"role": "user", "content": prompt}], max_tokens=4000)
            content = getattr(result, "content", str(result))

            # 清理JSON格式
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]

            notes = json.loads(content.strip())
            notes["format"] = format
            return notes
        except json.JSONDecodeError as exc:
            logger.error("笔记JSON解析失败: %s, content: %s", exc, content[:200])
            return {"title": "", "sections": [], "format": format, "error": str(exc)}
        except Exception as exc:
            logger.error("笔记提取失败: %s", exc)
            return {"title": "", "sections": [], "format": format, "error": str(exc)}


class AIChatbot:
    """AI问答机器人。基于文档内容进行问答。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def answer(
        self,
        question: str,
        context: str,
        chat_history: list[dict] | None = None,
        mode: str = "answer",
    ) -> str:
        """基于文档内容回答问题。

        Parameters
        ----------
        question : str
            用户问题
        context : str
            文档上下文（可以是之前的对话摘要或文档内容）
        chat_history : list[dict], optional
            对话历史，每条记录包含 "role"（"user"或"assistant"）和 "content"

        Returns
        -------
        str
            AI回答内容
        """
        if not question or not question.strip():
            return "请提供有效的问题"

        if not context or not context.strip():
            return "没有提供文档上下文，请先上传文档"

        messages = []

        # 添加系统提示
        mode_rules = {
            "answer": "直接回答问题，先给结论，再给简洁解释。",
            "socratic": (
                "采用苏格拉底教学法：不要直接给最终答案；先判断学习者卡在哪里，"
                "然后只提出一个能够推进思考的具体问题。必要时给一个小提示。"
            ),
            "feynman": (
                "采用费曼训练法：把用户输入视为他对概念的讲解；指出一个讲对的地方、"
                "一个缺口，再提出一个让他用更简单语言补充说明的问题。"
            ),
        }
        selected_rule = mode_rules.get(mode, mode_rules["answer"])
        system_prompt = f"""你是一个专业的学习助手。请根据提供的文档内容帮助用户学习。

要求：
1. 只根据给定的文档内容回答，不要编造信息
2. 如果文档中没有相关信息，请明确告知用户
3. 文档片段带有“[引用N]”标记时，在对应结论后保留该引用标记
4. 回答要准确、简洁
5. 使用中文回答
6. 当前教学方式：{selected_rule}"""

        messages.append({"role": "system", "content": system_prompt})

        # 添加历史对话
        if chat_history:
            for msg in chat_history[-5:]:  # 最多5条历史
                if "role" in msg and "content" in msg:
                    messages.append({"role": msg["role"], "content": msg["content"]})

        # 添加当前问题和上下文
        user_content = f"""请根据以下文档内容回答问题。

文档内容：
---
{context[:6000]}
---

学习者输入：{question}

请按当前教学方式回应："""

        messages.append({"role": "user", "content": user_content})

        try:
            result = self.llm.call(messages=messages, max_tokens=2000)
            return str(result).strip()
        except Exception as exc:
            logger.error("AI问答失败: %s", exc)
            return f"回答生成失败: {exc}"


class StudyPlanGenerator:
    """根据课程资料与考试日期生成可执行的复习计划。"""

    def __init__(self, llm_client) -> None:
        self.llm = llm_client

    def generate(
        self,
        text: str,
        exam_date: str,
        daily_minutes: int = 60,
        goal: str = "掌握核心知识并通过考试",
        weak_topics: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """生成按天拆解、带检查点的个性化学习计划。"""
        if not text or not text.strip():
            raise ValueError("学习资料内容为空")

        try:
            target_date = date.fromisoformat(exam_date)
        except ValueError as exc:
            raise ValueError("考试日期必须使用 YYYY-MM-DD 格式") from exc

        today = date.today()
        total_days = (target_date - today).days
        if total_days < 1:
            raise ValueError("考试日期必须晚于今天")
        if not 15 <= daily_minutes <= 480:
            raise ValueError("每日学习时长应在 15 到 480 分钟之间")

        weak_text = "、".join(weak_topics or []) or "暂无，由你从资料中识别"
        prompt = f"""你是面向大学生的学习规划助手。请根据课程资料制定从今天到考试前的复习计划。

当前日期：{today.isoformat()}
考试日期：{exam_date}
可用天数：{total_days} 天
每日可投入：{daily_minutes} 分钟
学习目标：{goal or '掌握核心知识并通过考试'}
薄弱知识点：{weak_text}

要求：
1. 先识别最重要的知识主题并给出优先级（high/medium/low）
2. 计划覆盖理解、主动回忆、练习和最终模拟，不要只安排阅读
3. 每天任务总时长不得超过 {daily_minutes} 分钟
4. 越接近考试越强调错题复盘和模拟测试
5. 仅返回 JSON 对象，结构必须如下：
{{
  "title": "计划标题",
  "strategy": "整体策略",
  "topics": [{{"name": "主题", "priority": "high", "reason": "原因"}}],
  "daily_plan": [
    {{
      "date": "YYYY-MM-DD",
      "focus": "当日重点",
      "tasks": ["具体任务"],
      "duration_minutes": 60,
      "review_method": "主动回忆/费曼法/练习等"
    }}
  ],
  "checkpoints": [{{"date": "YYYY-MM-DD", "goal": "检查目标"}}]
}}

课程资料：
---
{text[:12000]}
---"""

        result = self.llm.call(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=6000,
        )
        plan = _parse_json_result(result)
        if not isinstance(plan, dict):
            raise ValueError("模型返回的学习计划不是 JSON 对象")

        daily_plan = plan.get("daily_plan")
        if not isinstance(daily_plan, list) or not daily_plan:
            raise ValueError("模型未生成有效的每日计划")

        normalized_days = []
        for item in daily_plan:
            if not isinstance(item, dict):
                continue
            tasks = item.get("tasks", [])
            if isinstance(tasks, str):
                tasks = [tasks]
            normalized_days.append(
                {
                    "date": str(item.get("date", "")),
                    "focus": str(item.get("focus", "复习核心知识")),
                    "tasks": [str(task) for task in tasks if str(task).strip()],
                    "duration_minutes": min(
                        daily_minutes,
                        max(15, int(item.get("duration_minutes", daily_minutes))),
                    ),
                    "review_method": str(item.get("review_method", "主动回忆")),
                }
            )

        if not normalized_days:
            raise ValueError("模型未生成有效的每日任务")

        return {
            "title": str(plan.get("title", "个性化复习计划")),
            "exam_date": exam_date,
            "total_days": total_days,
            "daily_minutes": daily_minutes,
            "goal": goal,
            "strategy": str(plan.get("strategy", "循序渐进，结合主动回忆与练习")),
            "topics": plan.get("topics", []),
            "daily_plan": normalized_days,
            "checkpoints": plan.get("checkpoints", []),
        }


# 便捷函数
def create_ai_tools(llm_client):
    """创建所有AI工具实例。"""
    return {
        "summarizer": AISummarizer(llm_client),
        "knowledge_card": KnowledgeCardGenerator(llm_client),
        "question_extractor": QuestionExtractor(llm_client),
        "note_extractor": NoteExtractor(llm_client),
        "chatbot": AIChatbot(llm_client),
        "study_plan": StudyPlanGenerator(llm_client),
    }
