"""按真实判题历史生成可解释的下一题建议，不调用模型或生成能力分。"""

from __future__ import annotations

from typing import Any

from .problems import PROBLEMS

DIFFICULTY_ORDER = {"简单": 0, "中等": 1, "困难": 2}
VALID_VERDICTS = {"AC", "WA", "TLE", "MLE", "RE", "CE"}


def recommend_problems(
    submissions: list[dict[str, Any]], profile: dict[str, Any], *, limit: int = 3,
) -> list[dict[str, Any]]:
    """优先未复习错误、低通过率分类和未练题，稳定排序并附提交证据。"""
    catalog = {problem["id"]: problem for problem in PROBLEMS}
    observed = [item for item in submissions
                if item.get("status") == "completed" and item.get("active")
                and not item.get("data_error") and item.get("problem_id") in catalog
                and item.get("result", {}).get("verdict") in VALID_VERDICTS]
    histories = {identifier: [item for item in observed if item["problem_id"] == identifier]
                 for identifier in catalog}
    unresolved = {wrong["problem_id"]: wrong for wrong in profile.get("wrongbook", [])
                  if not wrong["mastered"]}
    latest_failed = next((item for item in observed
                          if item["problem_id"] in unresolved and item["result"]["verdict"] != "AC"), None)
    focus_tags = set(catalog[latest_failed["problem_id"]]["tags"]) if latest_failed else set()
    weak_tags = set(profile.get("lowest_acceptance_tags", []))
    ranked = []
    for index, problem in enumerate(PROBLEMS):
        identifier, tags = problem["id"], set(problem["tags"])
        history = histories[identifier]
        evidence = []
        if identifier in unresolved:
            wrong = unresolved[identifier]
            reason = (f"这道题有{wrong['error_count']}次错误，最近连续通过{wrong['correct_streak']}次；"
                      "按当前复习规则，连续两次AC后才标记已复习。")
            evidence = [wrong["latest_error_id"], wrong["latest_submission_id"]]
            stage = "基础巩固" if problem["difficulty"] == "简单" else "错题重练"
            tier = 0 if latest_failed and identifier == latest_failed["problem_id"] else 1
        elif not history and tags & (focus_tags | weak_tags):
            shared = sorted(tags & (focus_tags | weak_tags))
            reason = f"与最近待复习错误或至少三次提交的低通过率分类相关：{'、'.join(shared)}；这道题尚未练习。"
            stage, tier = "同类训练", 2
            evidence = [item["submission_id"] for item in observed
                        if item["result"]["verdict"] != "AC"
                        and set(catalog[item["problem_id"]]["tags"]) & set(shared)][:5]
        elif not history:
            reason = "尚无这道题的有效提交，按难度从基础开始；不据此判断你的能力。"
            stage = "基础入门" if problem["difficulty"] == "简单" else "进阶练习"
            tier = 3
        else:
            accepted = sum(item["result"]["verdict"] == "AC" for item in history)
            reason = f"已有{len(history)}次有效提交，其中{accepted}次AC；可以换一种解法巩固并说明复杂度。"
            evidence = [item["submission_id"] for item in history[:5]]
            stage, tier = "巩固复习", 4
        score = (tier, DIFFICULTY_ORDER[problem["difficulty"]], len(history), index)
        ranked.append((score, {"problem_id": identifier, "title": problem["title"],
                               "difficulty": problem["difficulty"], "stage": stage,
                               "reason": reason, "basis_submission_ids": list(dict.fromkeys(evidence)),
                               "knowledge_nodes": problem["knowledge_nodes"],
                               "method": "local_evidence_rules_v1"}))
    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[:max(1, min(limit, 8))]]
