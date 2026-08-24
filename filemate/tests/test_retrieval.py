"""资料切分与检索测试。"""

import math

from filemate.understanding.retrieval import rank_chunks, split_document
from filemate.understanding.ai_learning import (
    _MIN_RELEVANCE_SCORE,
    bm25_rank,
    expand_query,
    rerank_chunks,
)


def test_split_document_preserves_pdf_page() -> None:
    chunks = split_document(
        "--- 第 1 页 ---\n进程是资源分配单位。\n\n"
        "--- 第 2 页 ---\n线程是 CPU 调度单位。",
        chunk_size=200,
    )

    assert [chunk["page_number"] for chunk in chunks] == [1, 2]
    assert "线程" in chunks[1]["content"]


def test_rank_chunks_returns_relevant_citation() -> None:
    chunks = split_document(
        "--- 第 1 页 ---\n数据库使用事务保证一致性。\n\n"
        "--- 第 2 页 ---\nTCP 使用三次握手建立连接。",
        chunk_size=200,
    )

    results = rank_chunks("TCP 为什么需要三次握手", chunks)

    assert results[0]["page_number"] == 2
    assert results[0]["score"] > 0


def test_split_document_empty_text() -> None:
    assert split_document("") == []
    assert split_document("   ") == []


def test_split_document_no_markers() -> None:
    chunks = split_document("进程是资源分配单位。线程是CPU调度单位。", chunk_size=200)
    assert len(chunks) >= 1
    assert all("page_number" in c for c in chunks)


def test_split_document_overlap() -> None:
    text = "A" * 100 + "B" * 100 + "C" * 100
    chunks = split_document(text, chunk_size=200, overlap=30)
    for i in range(1, len(chunks)):
        prev_end = chunks[i - 1]["content"][-30:]
        curr_start = chunks[i]["content"][:30]
        assert not set(prev_end).isdisjoint(set(curr_start)) or len(chunks) == 1


def test_split_document_invalid_params() -> None:
    import pytest
    with pytest.raises(ValueError):
        split_document("hello", chunk_size=0)
    with pytest.raises(ValueError):
        split_document("hello", chunk_size=100, overlap=100)


def test_rank_chunks_empty_query() -> None:
    chunks = split_document("进程是资源分配单位。", chunk_size=200)
    assert rank_chunks("", chunks) == []


def test_rank_chunks_no_match() -> None:
    chunks = split_document("进程是资源分配单位。", chunk_size=200)
    results = rank_chunks("量子纠缠相对论", chunks)
    assert results == []


def test_rank_chunks_chinese_tokenization() -> None:
    chunks = split_document("进程是资源分配单位。", chunk_size=200)
    results = rank_chunks("资源分配", chunks)
    assert len(results) > 0
    assert "资源" in results[0]["content"]


def test_rank_chunks_preserves_metadata() -> None:
    chunks = split_document(
        "--- 第 3 页 ---\n内存管理是操作系统核心功能。",
        chunk_size=200,
    )
    results = rank_chunks("内存管理", chunks)
    assert results[0]["page_number"] == 3
    assert "chunk_index" in results[0]


def test_bm25_rank_includes_score() -> None:
    chunks = [
        {"content": "进程是资源分配的基本单位", "chunk_index": 0},
        {"content": "线程是CPU调度的基本单位", "chunk_index": 1},
    ]
    results = bm25_rank("进程", chunks)
    assert len(results) > 0
    assert "score" in results[0]
    assert results[0]["score"] > 0


def test_bm25_rank_filters_by_threshold() -> None:
    """BM25 得分极低的无关 chunk 应被过滤。"""
    chunks = [
        {"content": "进程是资源分配的基本单位", "chunk_index": 0},
        {"content": "今天天气很好适合散步", "chunk_index": 1},
    ]
    results = bm25_rank("进程", chunks)
    relevant = [c for c in results if c.get("score", 0) >= _MIN_RELEVANCE_SCORE]
    assert all("进程" in c["content"] for c in relevant)


def test_expand_query_short_query() -> None:
    """短查询不扩展。"""
    from filemate.understanding.ai_learning import expand_query
    from unittest.mock import MagicMock
    llm = MagicMock()
    result = expand_query("进程", llm)
    assert result == ["进程"]
    llm.call.assert_not_called()


def test_rerank_chunks_fewer_than_top_k() -> None:
    """chunk 数 <= top_k 时跳过重排。"""
    chunks = [
        {"content": "进程", "chunk_index": 0},
        {"content": "线程", "chunk_index": 1},
    ]
    result = rerank_chunks("进程", chunks, llm_client=None, top_k=10)
    assert result == chunks


def test_rank_chunks_reverse_order() -> None:
    """排名与得分正相关。"""
    chunks = [
        {"content": "进程是资源分配的基本单位线程是CPU调度的基本单位内存管理", "chunk_index": 0},
        {"content": "进程", "chunk_index": 1},
    ]
    results = rank_chunks("进程", chunks)
    scores = [c["score"] for c in results]
    assert scores == sorted(scores, reverse=True)

