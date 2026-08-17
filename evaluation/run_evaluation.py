"""运行 FileMate 可复现离线评测。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filemate.understanding.interview import InterviewEvaluator
from filemate.understanding.retrieval import rank_chunks, split_document

ROOT = Path(__file__).resolve().parent


def _load(name: str) -> list[dict[str, Any]]:
    return json.loads((ROOT / "datasets" / name).read_text(encoding="utf-8"))


def evaluate_retrieval() -> dict[str, Any]:
    """计算引用检索 Recall@1、Recall@3 与 MRR。"""
    cases = _load("retrieval_cases.json")
    top_one = 0
    top_three = 0
    reciprocal_ranks = []
    details = []
    for case in cases:
        ranked = rank_chunks(case["query"], split_document(case["document"], chunk_size=200), limit=3)
        pages = [item.get("page_number") for item in ranked]
        expected = case["expected_page"]
        rank = pages.index(expected) + 1 if expected in pages else None
        top_one += int(rank == 1)
        top_three += int(rank is not None)
        reciprocal_ranks.append(1 / rank if rank else 0)
        details.append({"id": case["id"], "expected_page": expected, "retrieved_pages": pages, "rank": rank})
    count = len(cases)
    return {
        "case_count": count,
        "recall_at_1": round(top_one / count, 4),
        "recall_at_3": round(top_three / count, 4),
        "mrr": round(sum(reciprocal_ranks) / count, 4),
        "details": details,
    }


def evaluate_interview_fallback() -> dict[str, Any]:
    """验证无模型时评分稳定落入预期区间。"""
    cases = _load("interview_cases.json")
    evaluator = InterviewEvaluator(None)
    passed = 0
    details = []
    for case in cases:
        result = evaluator.evaluate(case["question"], case["answer"], "通用岗位")
        in_range = case["min_score"] <= result["score"] <= case["max_score"]
        passed += int(in_range)
        details.append({"id": case["id"], "score": result["score"], "expected_range": [case["min_score"], case["max_score"]], "passed": in_range})
    return {"case_count": len(cases), "range_pass_rate": round(passed / len(cases), 4), "details": details}


def main() -> None:
    """生成机器可读评测报告。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "mode": "offline_reproducible",
        "retrieval": evaluate_retrieval(),
        "interview_fallback": evaluate_interview_fallback(),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
