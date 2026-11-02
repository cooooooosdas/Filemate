"""Shared conservative boundary for numeric learning evidence."""

import math
from typing import Any

from filemate.wrongbook.engine import RULE_VERSION

# 旧记录保留原规则含义，新记录必须是独立客观核对；未知版本不外推。
TRUSTED_SQL = """is_correct IN (0,1) AND score=is_correct AND (
    rule_version='legacy-v1' OR (rule_version='review-interval-v2'
    AND judgement_status='verified' AND judgement_method='objective_rule' AND answer_revealed=0))"""


def trusted_attempt(row: dict[str, Any]) -> bool:
    """Accept compatible historical results and independently verified new results."""
    correct = row.get("is_correct")
    if correct not in (0, 1):
        return False
    if "score" in row:
        score = row["score"]
        if not isinstance(score, (int, float)) or not math.isfinite(score) or score != correct:
            return False
    version = row.get("rule_version", "legacy-v1")
    return version == "legacy-v1" or (
        version == RULE_VERSION and row.get("judgement_status") == "verified"
        and row.get("judgement_method") == "objective_rule" and row.get("answer_revealed", 0) == 0)
