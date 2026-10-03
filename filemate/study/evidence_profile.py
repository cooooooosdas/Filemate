"""以可追溯行为记录构建描述性画像，不推断学生真实能力。"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

MIN_SAMPLES = 5
STALE_DAYS = 90
DIMENSIONS = {"内容", "结构", "表达", "岗位匹配", "内容准确性", "逻辑结构", "表达流畅性", "岗位匹配度"}


def _time(value: Any, now: datetime) -> datetime | None:
    """SQLite旧无时区时间按其UTC写入合同解释。"""
    try:
        parsed = datetime.fromisoformat(value)
        parsed = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        return parsed.astimezone(timezone.utc) if parsed <= now else None
    except (TypeError, ValueError):
        return None


def _number(value: Any, maximum: float) -> float | None:
    """排除布尔、缺失、非数值及异常范围。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= maximum else None


def _decoded(value: Any) -> Any:
    """兼容SQLite原始JSON与已解码数据，损坏记录保持只读。"""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _quiz_href(row: dict[str, Any]) -> str:
    """优先恢复已关联资料的题集，旧记录仍保留产物标识。"""
    query = {"artifact": row["artifact_id"]}
    if row.get("source_id"):
        query["source"] = row["source_id"]
    return "/ai-tools?" + urlencode(query)


def _metric(rows: list[dict[str, Any]], *, label: str, unit: str, basis: str,
            value: float | None, excluded: int, now: datetime) -> dict[str, Any]:
    """样本和时间来自全部有效记录，链接仅展示最近五条。"""
    ordered = sorted(rows, key=lambda row: (row["time"], row["record_id"]), reverse=True)
    latest = ordered[0]["time"] if ordered else None
    status = "pending_assessment"
    if rows:
        status = "insufficient_samples" if len(rows) < MIN_SAMPLES else "observed"
        if latest < now - timedelta(days=STALE_DAYS):
            status = "historical_only"
    return {"label": label, "value": round(value, 2) if value is not None else None,
            "sample_count": len(rows), "sample_unit": unit, "minimum_samples": MIN_SAMPLES,
            "updated_at": latest.isoformat() if latest else None, "status": status,
            "basis": basis, "excluded_count": excluded,
            "records": [{key: row[key] for key in ("record_id", "record_type", "href")}
                        for row in ordered[:5]]}


def build_evidence_profile(*, attempts: list[dict[str, Any]], wrongs: list[dict[str, Any]],
                           plans: list[dict[str, Any]], interviews: list[dict[str, Any]],
                           source_id: str | None = None,
                           now: datetime | None = None) -> dict[str, Any]:
    """相同输入与截止时间得到稳定结果，汇总不写回原始记录。"""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("画像截止时间须带时区")
    valid: dict[str, list[dict[str, Any]]] = {key: [] for key in ("quiz", "wrong", "plan", "interview")}
    excluded = dict.fromkeys(valid, 0)
    dimensions: dict[str, list[dict[str, Any]]] = {}
    pending = unassessed = archived = 0
    for row in attempts:
        moment = _time(row.get("created_at"), current)
        correct = _number(row.get("is_correct"), 1)
        if moment is None or correct not in {0, 1} or _number(row.get("score"), 1) is None:
            excluded["quiz"] += 1
            continue
        valid["quiz"].append({"time": moment, "record_id": row["attempt_id"],
            "record_type": "quiz_attempt", "value": correct,
            "href": _quiz_href(row)})
    for row in wrongs:
        moment = _time(row.get("updated_at"), current)
        mastered = _number(row.get("mastered"), 1)
        if moment is None or mastered not in {0, 1}:
            excluded["wrong"] += 1
            continue
        pending += mastered == 0
        valid["wrong"].append({"time": moment, "record_id": row["wrong_id"],
            "record_type": "wrong_question", "value": mastered,
            "href": _quiz_href(row)})
    for row in plans:
        if row.get("status") == "archived":
            archived += 1
            continue
        moment = _time(row.get("updated_at"), current)
        content, completed = _decoded(row.get("plan_data")), _decoded(row.get("completed_days"))
        days = content.get("daily_plan") if isinstance(content, dict) else None
        if (moment is None or row.get("status") not in {"active", "completed"}
                or not isinstance(days, list) or not days or not all(isinstance(day, dict) for day in days)
                or not isinstance(completed, list)):
            excluded["plan"] += 1
            continue
        day_ids = list(range(len(days)))
        if (any(type(day) is not int or day < 0 for day in completed)
                or len(set(completed)) != len(completed)
                or not set(completed) <= set(day_ids)):
            excluded["plan"] += 1
            continue
        for day in day_ids:
            valid["plan"].append({"time": moment, "record_id": f"{row['plan_id']}:{day}",
                "record_type": "study_plan_day", "value": float(day in completed),
                "href": "/study-plan?" + urlencode({"plan": row["plan_id"]})})
    for interview in interviews:
        for row in interview.get("turns", []):
            if row.get("analysis_data_error"):
                excluded["interview"] += 1
                continue
            if row.get("scoring_mode") != "llm" or row.get("score") is None:
                unassessed += 1
                continue
            moment = _time(row.get("created_at"), current)
            score = _number(row.get("score"), 100)
            if moment is None or score is None:
                excluded["interview"] += 1
                continue
            record = {"time": moment, "record_id": row["turn_id"], "record_type": "interview_turn",
                "value": score, "href": "/interview?" + urlencode({"interview": interview["interview_id"]})}
            valid["interview"].append(record)
            scores = row.get("dimensions")
            for name, value in (scores if isinstance(scores, dict) else {}).items():
                numeric = _number(value, 100)
                if name in DIMENSIONS and numeric is not None:
                    dimensions.setdefault(name, []).append({**record, "value": numeric})
    metadata = {
        "quiz": ("练习作答正确率", "次作答", "有效客观判题记录中答对次数 / 作答次数；重复作答逐次计入，不等同于独立题目或知识掌握。"),
        "wrong": ("错题复练状态", "道错题", "同题连续答对两次记为平台已掌握；已掌握错题 / 全部有效错题，不证明延迟保持或知识迁移。"),
        "plan": ("学习计划完成率", "个计划学习日", "有效未撤销计划中完成学习日 / 总学习日；不同计划的相同日期分别计入，只表示勾选完成。"),
        "interview": ("面试模型参考分", "条已评估回答", "仅对scoring_mode=llm且有效的逐回答分数取算术平均；排除本地回退，不等同于导师校准结果。"),
    }
    metrics = {}
    for key, rows in valid.items():
        label, unit, basis = metadata[key]
        mean = sum(row["value"] for row in rows) / len(rows) if rows else None
        metrics[key] = _metric(rows, label=label, unit=unit, basis=basis,
            value=mean if key == "interview" or mean is None else mean * 100,
            excluded=excluded[key], now=current)
    return {"version": "learning-evidence-v1", "scope": "source" if source_id else "device",
            "source_id": source_id, "window": "all_saved_valid_records",
            "minimum_samples": MIN_SAMPLES, "stale_after_days": STALE_DAYS,
            "metrics": metrics, "dimensions": {name: _metric(rows, label=name,
                unit="条已评估回答", basis=metadata["interview"][2],
                value=sum(row["value"] for row in rows) / len(rows), excluded=0, now=current)
                for name, rows in sorted(dimensions.items())},
            "pending_wrong_count": pending, "unassessed_interview_turns": unassessed,
            "mastered_wrong_count": sum(row["value"] for row in valid["wrong"]),
            "total_study_days": len(valid["plan"]),
            "completed_study_days": int(sum(row["value"] for row in valid["plan"])),
            "archived_plans_excluded": archived,
            "notice": "统计描述本机记录；5条为显示摘要的工程门槛，不是能力认证或研究样本量标准。90天无新证据标为历史记录。"}
