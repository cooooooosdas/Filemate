"""本地文档切分与可解释词法检索。"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

PAGE_MARKER = re.compile(r"---\s*第\s*(\d+)\s*页\s*---")
LATIN_TOKEN = re.compile(r"[a-zA-Z0-9_]+")
HAN_RUN = re.compile(r"[一-鿿]+")


def _tokens(text: str) -> list[str]:
    """提取英文词及中文一至三字词，兼顾短查询召回。"""
    lowered = text.lower()
    tokens = LATIN_TOKEN.findall(lowered)
    for run in HAN_RUN.findall(lowered):
        tokens.extend(run)
        tokens.extend(run[index:index + 2] for index in range(len(run) - 1))
        tokens.extend(run[index:index + 3] for index in range(len(run) - 2))
    return tokens


def split_document(
    text: str,
    *,
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    """按页标记和自然段切分文档，并保留可引用位置。"""
    if not text.strip():
        return []
    if chunk_size < 200 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("无效的文档切分参数")

    markers = list(PAGE_MARKER.finditer(text))
    sections: list[tuple[int | None, str]] = []
    if markers:
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            sections.append((int(marker.group(1)), text[start:end].strip()))
    else:
        sections.append((None, text.strip()))

    chunks: list[dict[str, Any]] = []
    for page_number, section in sections:
        if not section:
            continue
        start = 0
        while start < len(section):
            end = min(len(section), start + chunk_size)
            if end < len(section):
                boundary = max(
                    section.rfind("\n", start + chunk_size // 2, end),
                    section.rfind("。", start + chunk_size // 2, end),
                )
                if boundary > start:
                    end = boundary + 1
            content = section[start:end].strip()
            if content:
                chunks.append(
                    {
                        "chunk_index": len(chunks),
                        "page_number": page_number,
                        "content": content,
                        "metadata": {
                            "char_start": start,
                            "char_end": end,
                        },
                    }
                )
            if end >= len(section):
                break
            start = max(start + 1, end - overlap)
    return chunks


def rank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """使用轻量 BM25 评分返回存在词法重叠的可解释检索结果。"""
    query_tokens = _tokens(query)
    if not query_tokens or not chunks:
        return []

    documents = [_tokens(str(chunk.get("content", ""))) for chunk in chunks]
    average_length = sum(map(len, documents)) / max(1, len(documents))
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))

    query_frequency = Counter(query_tokens)
    scored: list[dict[str, Any]] = []
    for chunk, document in zip(chunks, documents, strict=True):
        frequencies = Counter(document)
        score = 0.0
        for token, query_count in query_frequency.items():
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1 + (len(documents) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.2 * (
                0.25 + 0.75 * len(document) / max(1.0, average_length)
            )
            score += query_count * inverse_frequency * frequency * 2.2 / denominator
        if score > 0:
            item = dict(chunk)
            item["score"] = round(score, 6)
            scored.append(item)

    scored.sort(key=lambda item: (-item["score"], item.get("chunk_index", 0)))
    return scored[:limit]
