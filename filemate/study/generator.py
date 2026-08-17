"""文件出题：文本切片、AI 出题、判题与离线兜底。"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

GENERATE_SYSTEM_PROMPT = (
    "你是高校出题专家。根据学科、知识点和参考资料生成练习题，"
    "必须生成多道互不相同的题目，严禁重复题干。"
    "只输出 JSON 数组，不要输出任何解释或 Markdown。"
    "每题结构：{\"subject\": \"...\", \"knowledge_point\": \"...\", "
    "\"question_type\": \"choice|fill|short_answer\", \"stem\": \"...\", "
    "\"options\": [\"A. ...\", \"B. ...\"], \"answer\": \"...\", \"analysis\": \"...\"}"
)

ANALYZE_SYSTEM_PROMPT = (
    "你是文档分析专家。请阅读文档切片，评估知识点数量与内容完整度，"
    "并推荐一套出题计划。只输出严格 JSON，不要额外解释："
    "{\"knowledge_points\": 5, \"completeness\": \"rich|medium|poor\", "
    "\"message\": \"...\", \"menu\": ["
    "{\"question_type\": \"choice\", \"count\": 5}, "
    "{\"question_type\": \"fill\", \"count\": 2}, "
    "{\"question_type\": \"short_answer\", \"count\": 1}]}"
)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """按段落聚合切片，避免知识被切断。"""
    if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size 必须大于 0，overlap 必须在 [0, chunk_size) 内")
    text = text.strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 1 <= chunk_size:
            buffer = f"{buffer}\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        if len(paragraph) > chunk_size:
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end])
                if end >= len(paragraph):
                    break
                start = end - overlap if end - overlap > start else end
        else:
            buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return chunks


def _normalize(
    raw: Any,
    subject: str,
    knowledge_point: str,
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raw = raw.get("questions", []) if isinstance(raw, dict) else []
    questions: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("stem"):
            continue
        options = item.get("options") if isinstance(item.get("options"), list) else []
        questions.append(
            {
                "subject": str(item.get("subject", subject)).strip() or subject,
                "knowledge_point": (
                    str(item.get("knowledge_point", knowledge_point)).strip()
                    or knowledge_point
                ),
                "question_type": (
                    str(item.get("question_type", "choice")).strip() or "choice"
                ),
                "stem": str(item["stem"]).strip(),
                "options": [str(opt).strip() for opt in options if str(opt).strip()],
                "answer": str(item.get("answer", "")).strip(),
                "analysis": str(item.get("analysis", "")).strip(),
            }
        )
    return questions


def _dedupe(
    generated: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for question in generated:
        stem = str(question.get("stem", "")).strip()
        if stem and stem not in seen:
            seen.add(stem)
            unique.append(question)
    return unique[:count]


def generate_questions_with_llm(
    llm: Callable | None,
    subject: str,
    knowledge_point: str,
    count: int,
    question_type: str = "choice",
    context: list[str] | None = None,
) -> list[dict[str, Any]]:
    """调用 LLM 出题；AI 不可用或失败时直接抛错，不生成模板题。"""
    count = max(1, min(int(count or 1), 10))
    if question_type not in {"choice", "fill", "short_answer"}:
        question_type = "choice"

    context_text = ""
    if context:
        context_text = "\n参考资料（只能基于以下内容出题）：\n" + "\n".join(
            f"- {item[:500]}" for item in context[:5]
        )
    user_prompt = (
        f"学科：{subject}\n知识点：{knowledge_point}\n题型：{question_type}\n数量：{count}"
        + context_text
    )

    if llm is None:
        raise RuntimeError("AI 出题失败：未配置或无法连接 LLM，且已关闭模板兜底")
    try:
        raw = llm(
            prompt=GENERATE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=2048,
            temperature=0.4,
        )
    except Exception as exc:
        raise RuntimeError(f"AI 出题失败：{exc}") from exc
    generated = _normalize(raw, subject, knowledge_point)
    if not generated:
        raise RuntimeError("AI 出题失败：模型未返回有效题目，且已关闭模板兜底")
    return _dedupe(generated, count)


def analyze_document_with_llm(
    llm: Callable | None,
    filename: str,
    chunks: list[str],
) -> dict[str, Any]:
    """AI 预分析文档并返回题型菜单；AI 不可用或失败时直接抛错。"""
    if llm is None:
        raise RuntimeError("AI 分析失败：未配置或无法连接 LLM，且已关闭规则菜单兜底")
    if not chunks:
        raise RuntimeError("AI 分析失败：文档没有可用文本切片")
    try:
        context = "\n\n".join(
            f"[{i + 1}] {chunk[:800]}" for i, chunk in enumerate(chunks[:12])
        )
        raw = llm(
            prompt=ANALYZE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"文件名：{filename}\n\n{context}"}],
            max_tokens=1024,
            temperature=0.2,
        )
    except Exception as exc:
        raise RuntimeError(f"AI 分析失败：{exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("menu"), list):
        raise RuntimeError(  # noqa: TRY004 - 外部模型响应无效，不是调用方类型错误
            "AI 分析失败：模型未返回有效题型菜单，且已关闭规则菜单兜底"
        )
    menu = []
    for item in raw["menu"]:
        if not isinstance(item, dict):
            continue
        qtype = str(item.get("question_type", "choice")).strip()
        if qtype not in {"choice", "fill", "short_answer"}:
            continue
        count = max(0, min(int(item.get("count", 0) or 0), 10))
        menu.append({"question_type": qtype, "count": count})
    if not menu:
        raise RuntimeError("AI 分析失败：模型未返回有效题型菜单，且已关闭规则菜单兜底")
    return {
        "knowledge_points": int(raw.get("knowledge_points", len(chunks)) or 0),
        "completeness": str(raw.get("completeness", "medium")).strip() or "medium",
        "message": str(raw.get("message", "已分析文档内容")).strip(),
        "menu": menu,
    }


def check_answer(question: Any, user_answer: str) -> bool:
    """按题型判题：单选、填空、简答关键词重合。"""
    answer = str(
        question.get("answer")
        if isinstance(question, dict)
        else getattr(question, "answer", "") or ""
    ).strip().lower()
    submitted = (user_answer or "").strip().lower()
    if not answer:
        return False
    question_type = str(
        question.get("question_type")
        if isinstance(question, dict)
        else getattr(question, "question_type", "choice")
    ).strip()
    if question_type == "choice":
        return bool(submitted) and submitted.startswith(answer[:1])
    if question_type == "fill":
        return bool(submitted) and (answer in submitted or submitted in answer)
    answer_tokens = [w for w in re.split(r"[\s，。；、,.;]+", answer) if len(w) > 1]
    if not answer_tokens:
        return False
    matched = sum(1 for token in answer_tokens if token in submitted)
    return matched / len(answer_tokens) >= 0.5
