"""围绕同一错题的首答、追问、复答与结构回看。"""

from __future__ import annotations

from typing import Any

STRUCTURE_CUES = {
    "依据": ("因为", "由于", "依据", "根据", "原因", "所以", "因此"),
    "例子": ("例如", "比如", "举例", "案例", "假设", "为例"),
    "步骤": ("首先", "然后", "最后", "第一", "第二", "步骤", "先"),
    "边界": ("条件", "前提", "适用", "不适用", "边界", "除非"),
}


def describe_answer_structure(answer: str) -> dict[str, Any]:
    """统计可观察的表达线索，不判断知识内容是否正确。"""
    clean = "".join(answer.split())
    return {
        "character_count": len(clean),
        "cues": [
            name for name, phrases in STRUCTURE_CUES.items()
            if any(phrase in clean for phrase in phrases)
        ],
    }


def build_targeted_followup(answer: str, error_cause: str) -> str:
    """根据首答可观察的缺口生成不暴露参考答案的追问。"""
    structure = describe_answer_structure(answer)
    cues = set(structure["cues"])
    if structure["character_count"] < 25:
        return "你的首答较简短。请补充关键概念、得出结论的依据，并举一个具体情境。"
    if error_cause == "expression_gap" and "依据" not in cues:
        return "请先说结论，再说明支持它的依据；哪些条件变化会让结论不同？"
    if error_cause == "reasoning_break" and "步骤" not in cues:
        return "请把推理拆成条件、关键步骤和结论，并指出你最需要核对的一步。"
    if error_cause == "concept_gap" and "边界" not in cues:
        return "这个概念在什么条件下适用？请给出一个不适用的情境。"
    if "依据" not in cues:
        return "你为什么这样判断？请补充依据，并说明它如何支持你的结论。"
    if "例子" not in cues:
        return "请举一个具体例子，把刚才的依据用到这个情境里。"
    return "如果题目条件发生变化，哪一步需要重新检查？请解释原因。"


def build_reanswer_prompt() -> str:
    """要求用户在同一题上独立复答。"""
    return (
        "现在回到最初那道题。请不看参考答案，重新完整作答："
        "先给结论，再讲依据、关键步骤和适用条件；也可指出仍不确定的地方。"
    )


def build_expression_review(first_answer: str, final_answer: str) -> dict[str, Any]:
    """比较两次表达的表面结构，并明确保留内容评估边界。"""
    first = describe_answer_structure(first_answer)
    final = describe_answer_structure(final_answer)
    added = [cue for cue in final["cues"] if cue not in first["cues"]]
    removed = [cue for cue in first["cues"] if cue not in final["cues"]]
    return {
        "method": "local_structure_v1",
        "content_accuracy": "unassessed",
        "first": first,
        "final": final,
        "added_cues": added,
        "removed_cues": removed,
        "summary": (
            "复答新增了" + "、".join(added) + "等表达线索；请对照原资料核实内容。"
            if added else "已完成同题复答；请对照原资料核实内容，表达线索未见新增。"
        ),
    }
