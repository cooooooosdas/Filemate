"""Persist document limitations without exposing decoder internals."""

from typing import Any


def parse_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    """Keep supported parser evidence and actionable scope warnings."""
    allowed = {"filename", "suffix", "size_bytes", "total_pages", "text_pages", "pages",
               "slides", "engine", "is_image_based", "truncated", "enrichment_incomplete",
               "tables", "charts"}
    metadata = {key: value for key, value in (parsed.get("metadata") or {}).items() if key in allowed}
    warnings = []
    if metadata.get("truncated"):
        warnings.append("正文超过解析上限，当前仅保留前500000字，请拆分资料以读取其余内容。")
    if metadata.get("enrichment_incomplete"):
        warnings.append("已提取正文；超过50页的PDF未提取表格和图表结构，请按章节拆分。")
    metadata["parse_warnings"] = warnings
    return metadata
