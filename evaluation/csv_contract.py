"""严格读取匿名评测 CSV，不接受额外身份字段或歧义表头。"""

from __future__ import annotations

import csv
import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

METADATA = {"sample_kind", "study_date", "consent_confirmed"}


def read_rows(
    path: Path,
    required: set[str],
    allowed: set[str],
    *,
    allow_empty: bool = False,
) -> list[dict[str, str]]:
    """验证表头、行宽和必填值，返回输入中的匿名记录快照。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames or []
        if not fields or any(not field for field in fields) or len(fields) != len(set(fields)):
            raise ValueError("CSV 表头为空或含重复字段")
        if required - set(fields):
            raise ValueError("CSV 缺少字段：" + ", ".join(sorted(required - set(fields))))
        if set(fields) - allowed:
            raise ValueError("CSV 只接受协议中的匿名字段，不能加入身份或自由文本")
        rows = []
        try:
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"CSV 第 {reader.line_num} 行字段数量与表头不一致")
                if any(not row[field].strip() for field in required):
                    raise ValueError(f"CSV 第 {reader.line_num} 行存在缺失值")
                rows.append(row)
        except csv.Error as exc:
            raise ValueError("CSV 格式无法解析") from exc
    if not rows and not allow_empty:
        raise ValueError("CSV 尚无真实实验记录或合成回归输入")
    return rows


def anonymous_id(value: str) -> bool:
    """只接受短 ASCII 匿名代码，格式检查不替代人工匿名化。"""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value or ""))


def validate_kind(path: Path, kind: str) -> None:
    """禁止将仓库示例或模板声明为真实研究。"""
    if kind not in {"synthetic", "real"}:
        raise ValueError("sample_kind 必须为 synthetic 或 real")
    if kind == "real" and any(
        marker in path.name.lower() for marker in (".example", ".template", ".synthetic")
    ):
        raise ValueError("示例或模板不能标记为真实研究")


def validate_metadata(rows: list[dict[str, str]], kind: str) -> None:
    """验证样本标签和日期，真实记录另需逐行声明已知情同意。"""
    for row in rows:
        if (kind == "real" and row.get("sample_kind") != "real") or (
            row.get("sample_kind") and row["sample_kind"] != kind
        ):
            raise ValueError("每行需匹配 sample_kind，真实与合成数据不能混合")
        if row.get("study_date"):
            try:
                measured = date.fromisoformat(row["study_date"])
            except ValueError as exc:
                raise ValueError("study_date 必须为实际测量日期 YYYY-MM-DD") from exc
            if (
                measured.isoformat() != row["study_date"]
                or measured > datetime.now(timezone.utc).astimezone().date()
            ):
                raise ValueError("study_date 必须为实际测量日期，不能使用未来日期")
        if kind == "real" and (not row.get("study_date") or row.get("consent_confirmed") != "1"):
            raise ValueError("真实研究需实际测量日期和逐行知情同意声明")


def provenance(path: Path, rows: list[dict[str, str]], kind: str) -> dict[str, Any]:
    """输出文件指纹与测量范围，不披露匿名参与者代码。"""
    dates = sorted(row["study_date"] for row in rows if row.get("study_date"))
    return {
        "sample_kind": kind,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "dated_record_count": len(dates),
        "measurement_date_range": {"start": dates[0], "end": dates[-1]} if dates else None,
    }
