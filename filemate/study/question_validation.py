"""生成和判题前的题目结构校验，不补造答案或选项。"""

from __future__ import annotations

import re
from typing import Any

ALIASES = {"选择题": "choice", "单选题": "choice", "多选题": "choice", "填空题": "fill",
           "判断题": "short_answer", "简答题": "short_answer", "计算题": "short_answer", "论述题": "short_answer"}


def text_field(value: Any, name: str, maximum: int, *, optional: bool = False) -> str:
    """拒绝隐式字符串化和空必填字段。"""
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{name}必须为长度不超过{maximum}的文本")
    result = value.strip()
    if not result and not optional:
        raise ValueError(f"{name}不能为空")
    return result


def validate_question(item: Any, *, legacy: bool = False) -> dict[str, Any]:
    """兼容已有字段名，校验选择题的选项与参考答案一致。"""
    if not isinstance(item, dict):
        raise TypeError("题目必须为对象")
    kind = item.get("question_type", item.get("type", "short_answer" if legacy else None))
    if kind is None:
        raise ValueError("缺少有效题型")
    if not isinstance(kind, str):
        raise TypeError("题型必须为文本")
    kind = ALIASES.get(kind, kind)
    if kind not in {"choice", "fill", "short_answer"}:
        raise ValueError("不支持的题型")
    stem = text_field(item.get("stem", item.get("question")), "题干", 4000)
    answer = text_field(item.get("answer"), "答案", 4000)
    analysis = text_field(item.get("analysis", item.get("explanation", "")), "解析", 8000, optional=True)
    options = item.get("options", [])
    if not isinstance(options, list) or len(options) > 8:
        raise ValueError("选项必须为最多8项的数组")
    options = [text_field(option, "选项", 1000) for option in options]
    if kind == "choice":
        if len(options) < 2:
            raise ValueError("选择题至少需要2个有效选项")
        bodies = []
        for index, option in enumerate(options):
            match = re.match(r"^([A-Z])[.、:：)）]\s*(.+)$", option, re.IGNORECASE)
            if match and match[1].upper() != chr(65 + index):
                raise ValueError("选择题选项标号必须连续且不重复")
            bodies.append(match[2].strip() if match else option)
        if len({body.casefold() for body in bodies}) != len(bodies):
            raise ValueError("选择题选项内容重复")
        options = [f"{chr(65 + index)}. {body}" for index, body in enumerate(bodies)]
        if answer in bodies:
            answer = chr(65 + bodies.index(answer))
        else:
            match = re.fullmatch(r"([A-Z])[.、:：)）]\s*(.+)", answer, re.IGNORECASE)
            if match:
                index = ord(match[1].upper()) - 65
                if index >= len(bodies) or bodies[index] != match[2].strip():
                    raise ValueError("参考答案与选项内容不一致")
                answer = match[1].upper()
            else:
                answer = answer.upper()
                if not re.fullmatch(r"[A-H]+", answer) or len(set(answer)) != len(answer):
                    raise ValueError("选择题答案必须对应实际选项")
                if any(ord(letter) - 65 >= len(options) for letter in answer):
                    raise ValueError("选择题答案超出选项范围")
                answer = "".join(sorted(answer))
    elif options:
        raise ValueError("非选择题不得携带选项")
    return {**item, "question_type": kind, "stem": stem, "options": options,
            "answer": answer, "analysis": analysis}


def validate_questions(raw: Any, *, maximum: int = 10) -> list[dict[str, Any]]:
    """整批校验，不悄悄丢弃坏题、截断超额内容或保留重复题干。"""
    if isinstance(raw, dict):
        raw = raw.get("questions")
    if not isinstance(raw, list) or not 1 <= len(raw) <= maximum:
        raise ValueError(f"题目必须为1至{maximum}项的数组")
    questions = [validate_question(item) for item in raw]
    stems = [question["stem"].casefold() for question in questions]
    if len(set(stems)) != len(stems):
        raise ValueError("题干重复，请重新生成")
    return questions
