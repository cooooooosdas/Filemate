"""AI 模拟面试问题编排与回答评估。"""

from __future__ import annotations

import json
import re
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


def _parse_json_text(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[1:])
    cleaned = cleaned.rstrip()
    if cleaned.endswith("```"):
        cleaned = "\n".join(cleaned.splitlines()[:-1])
    return json.loads(cleaned.strip())


def select_question_ids_with_llm(
    llm: Any,
    candidates: list[dict[str, Any]],
    *,
    target_role: str,
    scenario: str,
    difficulty: str,
    limit: int = 5,
) -> list[str]:
    """让 AI 从题库中挑选最匹配的题目 ID；失败或无效时返回空列表。"""
    if llm is None or not candidates or not hasattr(llm, "call"):
        return []

    lines = "\n".join(
        f"{index}. [{item['id']}] {str(item.get('text', ''))[:120]}"
        for index, item in enumerate(candidates, start=1)
    )
    prompt = (
        "你是资深模拟面试官。根据面试场景、难度和目标岗位，从候选题目中"
        "挑选最合适的题目 ID，只返回 JSON 字符串数组，不要 Markdown，不要解释。"
    )
    user_prompt = (
        f"场景：{scenario}\n难度：{difficulty}\n目标岗位/方向：{target_role}\n"
        f"需要选出 {limit} 道：\n{lines}"
    )
    try:
        text = llm.call(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=2048,
            temperature=0.2,
        )
        data = _parse_json_text(text)
    except Exception:  # noqa: BLE001 - LLM 失败时回退到确定性选题
        return []

    if not isinstance(data, list):
        return []
    valid_ids = {str(item["id"]) for item in candidates}
    picked: list[str] = []
    for item in data:
        question_id = str(item)
        if question_id in valid_ids and question_id not in picked:
            picked.append(question_id)
        if len(picked) >= limit:
            break
    return picked


def generate_interview_questions_with_llm(
    llm: Any,
    *,
    target_role: str,
    scenario: str,
    difficulty: str,
    count: int,
    context_excerpt: str = "",
) -> list[str]:
    """让 AI 针对性生成面试题；失败或无效时返回空列表。"""
    if llm is None or count <= 0 or not hasattr(llm, "call"):
        return []

    prompt = (
        "你是资深模拟面试官。请根据场景、难度和目标岗位生成针对性面试题，"
        "只返回 JSON 字符串数组，不要 Markdown，不要解释。"
    )
    user_prompt = (
        f"场景：{scenario}\n难度：{difficulty}\n目标岗位/方向：{target_role}\n"
        f"生成 {count} 道题"
    )
    if context_excerpt.strip():
        user_prompt += (
            "\n用户已明确选择以下本地材料作为出题依据。只围绕其中可核验的"
            f"信息提问，不复述敏感原文：\n{context_excerpt[:2000]}"
        )
    try:
        text = llm.call(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=2048,
            temperature=0.6,
        )
        data = _parse_json_text(text)
    except Exception:  # noqa: BLE001 - LLM 失败时回退到静态题目
        return []

    if not isinstance(data, list):
        return []
    questions: list[str] = []
    for item in data:
        if isinstance(item, str) and item.strip() and item.strip() not in questions:
            questions.append(item.strip())
        if len(questions) >= count:
            break
    return questions


def build_interview_questions(
    storage: Any,
    llm: Any,
    *,
    scenario: str,
    difficulty: str,
    target_role: str,
    limit: int = 5,
    context_excerpt: str = "",
) -> tuple[list[str], list[str | None]]:
    """AI 选题 + AI 补题 + 确定性回退，返回 (题目列表, 题库题目 ID 列表)。"""
    candidates = storage.list_interview_questions(
        scenario=scenario,
        difficulty=difficulty,
        enabled=True,
        limit=500,
    )
    selected_ids = select_question_ids_with_llm(
        llm,
        candidates,
        target_role=target_role,
        scenario=scenario,
        difficulty=difficulty,
        limit=limit,
    )
    by_id = {str(item["id"]): item for item in candidates}
    questions = [by_id[question_id]["text"] for question_id in selected_ids if question_id in by_id]
    question_ids: list[str | None] = [
        question_id for question_id in selected_ids if question_id in by_id
    ]
    used_ids = set(question_ids)

    for item in storage.select_interview_questions(
        scenario=scenario,
        difficulty=difficulty,
        limit=limit,
    ):
        if len(questions) >= limit:
            break
        question_id = str(item["id"])
        if question_id in used_ids:
            continue
        used_ids.add(question_id)
        questions.append(item["text"])
        question_ids.append(question_id)

    missing = limit - len(questions)
    if missing > 0:
        for question in generate_interview_questions_with_llm(
            llm,
            target_role=target_role,
            scenario=scenario,
            difficulty=difficulty,
            count=missing,
            context_excerpt=context_excerpt,
        ):
            if len(questions) >= limit:
                break
            if question not in questions:
                questions.append(question)

    missing = limit - len(questions)
    if missing > 0:
        for question in build_questions(scenario, target_role):
            if len(questions) >= limit:
                break
            if question not in questions:
                questions.append(question)

    question_ids = question_ids[:limit]
    while len(question_ids) < len(questions):
        question_ids.append(None)
    return questions[:limit], question_ids


def build_source_grounded_question(
    source_name: str,
    scenario: str,
    target_role: str,
) -> str:
    """根据用户明确选择的资料生成可追溯的本地问题。"""
    safe_name = source_name.strip()[:80] or "所选资料"
    target = target_role.strip() or "目标方向"
    templates = {
        "求职面试": (
            f"结合你选择的《{safe_name}》，请说明其中哪项经历或成果最能证明"
            f"你胜任{target}，并给出具体证据。"
        ),
        "竞赛答辩": (
            f"结合《{safe_name}》，请说明项目最关键的创新如何落地，"
            "并指出材料中能够支撑这一结论的事实。"
        ),
        "保研复试": (
            f"结合《{safe_name}》，请介绍一项与你申请{target}相关的学习或研究经历，"
            "并说明你的具体贡献。"
        ),
    }
    return templates.get(scenario, templates["求职面试"])


class InterviewEvaluator:
    """使用 LLM 评估回答，失败时提供可用的规则回退。"""

    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def evaluate(
        self,
        question: str,
        answer: str,
        target_role: str,
        fluency_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
            result = {
                "score": max(0.0, min(100.0, float(result["score"]))),
                "dimensions": dimensions,
                "feedback": str(result.get("feedback", "请补充具体行动与结果。")),
                "scoring_mode": "llm",
            }
        except Exception:  # noqa: BLE001 - 面试演示必须在模型不可用时降级
            result = {
                "score": None,
                "dimensions": {},
                "feedback": "回答已保存，内容质量尚未评估。可以继续练习，或结合原资料自行复盘。",
                "scoring_mode": "local_fallback",
            }
        return self._with_fluency(result, answer, fluency_metrics)

    @staticmethod
    def _with_fluency(
        evaluation: dict[str, Any],
        answer: str,
        metrics: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """把浏览器语音节奏转成透明、低权重的流畅性参考分。"""
        if not metrics or metrics.get("source") != "speech_recognition":
            return evaluation

        duration = max(0.0, min(3600.0, float(metrics.get("duration_seconds", 0))))
        if duration < 2:
            return evaluation

        spoken_chars = len(re.sub(r"\s+", "", answer))
        chars_per_minute = round(spoken_chars * 60 / duration, 2)
        filler_count = max(0, min(100, int(metrics.get("filler_count", 0))))
        long_pause_count = max(0, min(100, int(metrics.get("long_pause_count", 0))))
        marker_labels = {"long_pause": "较长停顿", "filler": "出现口头语"}
        markers = []
        for marker in metrics.get("markers", [])[:100]:
            if not isinstance(marker, dict) or marker.get("kind") not in marker_labels:
                continue
            second = max(0.0, min(duration, float(marker.get("second", 0))))
            markers.append(
                {
                    "second": round(second, 2),
                    "kind": marker["kind"],
                    "label": marker_labels[marker["kind"]],
                }
            )

        if 120 <= chars_per_minute <= 260:
            pace_score = 100.0
        elif chars_per_minute < 120:
            pace_score = max(35.0, 100.0 - (120 - chars_per_minute) * 0.75)
        else:
            pace_score = max(35.0, 100.0 - (chars_per_minute - 260) * 0.45)

        fluency_score = max(
            0.0,
            min(
                100.0,
                pace_score - min(24, filler_count * 4) - min(24, long_pause_count * 6),
            ),
        )
        fluency_score = round(fluency_score, 2)
        if evaluation.get("score") is not None:
            base_score = float(evaluation["score"])
            evaluation["score"] = round(base_score * 0.85 + fluency_score * 0.15, 2)
        evaluation.setdefault("dimensions", {})["流畅性"] = fluency_score
        evaluation["fluency"] = {
            "duration_seconds": round(duration, 2),
            "chars_per_minute": chars_per_minute,
            "filler_count": filler_count,
            "long_pause_count": long_pause_count,
            "reference_score": fluency_score,
            "source": "speech_recognition",
            "markers": markers,
        }
        fluency_feedback = (
            f"语音节奏参考：约 {chars_per_minute:.0f} 字/分钟，"
            f"检测到 {filler_count} 个口头语、{long_pause_count} 次较长停顿。"
        )
        evaluation["feedback"] = f"{evaluation.get('feedback', '')} {fluency_feedback}".strip()
        return evaluation
