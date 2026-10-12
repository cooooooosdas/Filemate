"""专项面试的问题链与用户主动授权的跨次练习记忆。"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Literal

from filemate.execution.storage import SQLiteStorage, _now_iso

InterviewScenario = Literal[
    "求职面试", "竞赛答辩", "保研复试", "知识讲解",
    "技术面", "项目面", "算法面", "HR面", "压力面", "英语面",
]

SPECIALIST_QUESTIONS = {
    "技术面": [
        "请解释目标岗位中你最熟悉的一项技术，说明原理和适用边界。",
        "面对一个运行变慢的系统，你会如何定位瓶颈？需要哪些证据？",
        "请比较两种你实际使用过的技术方案，说明选择的依据。",
        "如果发生并发冲突或数据不一致，你如何发现和处理？",
        "如何验证一次技术改动的正确性，并在失败时恢复？",
    ],
    "项目面": [
        "请说明所选项目的目标、你的职责和实际完成的部分。",
        "请按数据流说明项目的核心模块和接口，以及你负责的链路。",
        "请介绍你实际做过的一项设计选择，说明理由和代价。",
        "你如何验证项目结果？请区分真实记录、演示和尚未验证的部分。",
        "请说明一个尚未解决的限制，以及下一步可验证的改进。",
    ],
    "算法面": [
        "给定一个整数数组和目标值，如何找出和为目标值的两个不同下标？请说明思路。",
        "你的方案如何处理重复值、负数和无解情况？",
        "请推导时间与空间复杂度，并比较一个替代方案。",
        "请给出能暴露边界错误的测试用例，并逐步执行算法。",
        "如果输入无法全部放入内存，你会怎样调整方案？",
    ],
    "HR面": [
        "请说明你希望申请这个方向的原因，并用一段真实经历支撑。",
        "讲一次你与他人合作的经历，以及你具体承担了什么。",
        "面对意见分歧，你采取了什么行动？结果如何？",
        "请介绍一次挫折，以及你之后实际改变了什么。",
        "你希望怎样成长？请说明未来三个月可以执行的一步。",
    ],
    "压力面": [
        "请提出一个你能够用事实支持的观点；如果证据不足，请明确说明。",
        "你的结论是否存在反例？请正面说明适用边界。",
        "如果你提出的方案失败，你首先检查什么，而不是归因于他人？",
        "在时间不足时，你会怎样取舍，并向团队说明风险？",
        "请用三句话回应对你方案的质疑，保留事实与不确定性。",
    ],
    "英语面": [
        "Please introduce yourself and explain your interest in the target role using a real example.",
        "Describe a problem you actually solved. What did you personally do?",
        "Explain a technical concept you know well to a non-technical teammate.",
        "Tell me about a disagreement and how you handled it.",
        "What would you improve next, and how would you verify the result?",
    ],
}

FOLLOWUP_AREAS = (
    ("completeness", "请补充这部分的前提、具体行动与结果。", "Please explain the context, your actions, and the outcome."),
    ("logic", "请把依据、推理步骤和结论连起来，说明为什么这样判断。", "Please connect your evidence, reasoning, and conclusion."),
    ("technical_coverage", "请解释相关技术原理和适用边界，并给出一个例子。", "Please explain the technical principle, its limits, and one example."),
    ("technical_expression", "请把相关模块、输入输出和你的职责讲清楚。", "Please clarify the components, their inputs and outputs, and your responsibility."),
)


def grounded_followup(
    answer: str, scenario: str, step: int, analysis: dict[str, Any] | None = None,
    *, previous_session: bool = False,
) -> str:
    """只引用真实回答，模型分析有效时优先追问其中尚未展开的部分。"""
    areas = (analysis or {}).get("areas", {})
    focus = next((item for item in FOLLOWUP_AREAS
                  if isinstance(areas, dict) and isinstance(areas.get(item[0]), dict)
                  and areas[item[0]].get("status") in {"partial", "missing"}), None)
    if focus is None:
        focus = FOLLOWUP_AREAS[max(0, step - 1) % len(FOLLOWUP_AREAS)]
    if scenario == "算法面":
        instructions = (
            "请解释方案如何处理重复值、负数和无解情况。",
            "请推导时间与空间复杂度，并比较一种替代方案。",
            "请给出边界测试并逐步执行算法，检查下标和终止条件。",
            "如果输入无法全部放入内存，你会怎样调整方案？",
        )
        focus = (focus[0], instructions[max(0, step - 1) % len(instructions)], focus[2])
    evidence = areas.get(focus[0], {}).get("evidence", "") if isinstance(areas, dict) else ""
    # 不把模型改进建议当成用户做过的事；引用必须是原回答的连续子串。
    if not isinstance(evidence, str) or not evidence.strip() or evidence not in answer:
        evidence = answer.strip()
    quote = evidence[:160 if scenario == "英语面" else 90].strip()
    if scenario == "英语面":
        origin = "In your previous practice" if previous_session else "In your last answer"
        return f'{origin}, you said: “{quote}”. {focus[2]} Distinguish facts from assumptions.'
    origin = "上次练习" if previous_session else "刚才的回答"
    return f"你在{origin}中提到：“{quote}”。{focus[1]}请区分已做事实和设想。"


def project_questions(name: str, details: str) -> list[str]:
    """只把用户填写的项目原文作为提问依据。"""
    quote = details.strip()[:180]
    return [
        f"你填写的项目是“{name}”，描述为：“{quote}”。请说明目标、你的职责和已完成部分。",
        *SPECIALIST_QUESTIONS["项目面"][1:],
    ]


class InterviewPracticeRepository:
    """复用现有私有记忆和事件表，不另造用户画像或复制回答。"""

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def _row(self, memory_id: str) -> dict[str, Any] | None:
        row = self.storage._conn().execute(
            "SELECT m.*, s.target_role, s.scenario, s.agent_run_id FROM agent_memories m "
            "JOIN interview_sessions s ON s.interview_id=m.scope_id "
            "WHERE m.memory_id=? AND m.source_type='interview_practice' "
            "AND m.source_id=s.interview_id AND m.memory_type='session'", (memory_id,),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _active(row: dict[str, Any]) -> bool:
        return not row["deleted_at"] and (not row["expires_at"] or row["expires_at"] > _now_iso())

    def for_session(self, interview_id: str) -> dict[str, Any] | None:
        row = self.storage._conn().execute(
            "SELECT memory_id FROM agent_memories WHERE scope_id=? AND source_id=? "
            "AND source_type='interview_practice' AND deleted_at IS NULL "
            "ORDER BY rowid DESC LIMIT 1", (interview_id, interview_id),
        ).fetchone()
        return self.get(row["memory_id"]) if row else None

    def get(self, memory_id: str) -> dict[str, Any] | None:
        row = self._row(memory_id)
        if row is None or not self._active(row):
            return None
        interview = self.storage.get_interview(row["scope_id"])
        if interview is None:
            return None
        run = self.storage.get_agent_run(row["agent_run_id"]) if row["agent_run_id"] else None
        refs = run.get("context_refs", {}) if run else {}
        source_id = refs.get("source_id")
        if source_id and self.storage.get_source(source_id) is None:
            return None
        return {"memory_id": memory_id, "interview": interview, "context": refs}

    def list(self, *, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.storage._conn().execute(
            "SELECT m.memory_id, m.scope_id AS interview_id, m.created_at, "
            "s.target_role, s.scenario, COUNT(t.turn_id) AS answer_count "
            "FROM agent_memories m JOIN interview_sessions s ON s.interview_id=m.scope_id "
            "JOIN interview_turns t ON t.interview_id=s.interview_id "
            "WHERE m.source_type='interview_practice' AND m.source_id=s.interview_id "
            "AND m.memory_type='session' AND m.deleted_at IS NULL "
            "AND (m.expires_at IS NULL OR m.expires_at>?) "
            "GROUP BY m.memory_id ORDER BY s.updated_at DESC, m.rowid DESC LIMIT ?",
            (_now_iso(), max(1, min(limit, 100))),
        ).fetchall()
        return [dict(row) for row in rows if self.get(row["memory_id"]) is not None]

    def remember(self, interview: dict[str, Any], *, commit: bool = True) -> None:
        identifier = interview["interview_id"]
        self.storage.save_agent_memory(
            memory_type="session", scope_id=identifier, source_type="interview_practice",
            source_id=identifier, summary="用户主动允许这场已保存练习用于后续面试追问；不复制回答。",
            allowed_agents=["面试 Agent"],
            commit=commit,
        )

    def preview(self, memory_id: str) -> dict[str, Any]:
        row = self._row(memory_id)
        if row is None:
            raise LookupError("面试记忆不存在")
        body = {"memory_id": memory_id, "interview_id": row["scope_id"],
                "created_at": row["created_at"]}
        token = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return {**body, "confirmation_token": token, "target_role": row["target_role"],
                "scope": "停止后续面试复用这场回答；原回答、录像、报告和已经生成的问题保留。"}

    def forget(self, memory_id: str, token: str) -> dict[str, bool]:
        conn = self.storage._conn()
        with self.storage._write_lock:
            preview = self.preview(memory_id)
            if not hmac.compare_digest(preview["confirmation_token"], token):
                raise ValueError("记忆预览不匹配，请重新确认")
            with conn:
                changed = conn.execute(
                    "UPDATE agent_memories SET deleted_at=?, updated_at=? "
                    "WHERE memory_id=? AND source_type='interview_practice' AND deleted_at IS NULL",
                    (_now_iso(), _now_iso(), memory_id),
                ).rowcount
                if changed:
                    conn.execute(
                        "INSERT INTO interview_review_events(interview_id,action,detail,created_at) "
                        "VALUES (?, 'practice_memory_forgotten', ?, ?)",
                        (preview["interview_id"], json.dumps({"memory_id": memory_id}), _now_iso()),
                    )
        return {"forgotten": True}
