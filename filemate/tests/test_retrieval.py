"""资料切分与检索测试。"""

from filemate.understanding.retrieval import rank_chunks, split_document


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


def test_rank_chunks_keeps_single_character_query_recall() -> None:
    chunks = split_document("栈是后进先出的数据结构，队列是先进先出的数据结构。", chunk_size=200)
    results = rank_chunks("栈", chunks)
    assert results
    assert "栈" in results[0]["content"]


def test_rank_chunks_two_char_query_passes_threshold() -> None:
    """双字查询如"队列"得分 0.86 > 0.5，应正常召回。"""
    chunks = split_document("栈是后进先出的数据结构，队列是先进先出的数据结构。", chunk_size=200)
    results = rank_chunks("队列", chunks)
    assert results
    assert "队列" in results[0]["content"]


def test_rank_chunks_preserves_metadata() -> None:
    chunks = split_document(
        "--- 第 3 页 ---\n内存管理是操作系统核心功能。",
        chunk_size=200,
    )
    results = rank_chunks("内存管理", chunks)
    assert results[0]["page_number"] == 3
    assert "chunk_index" in results[0]


def test_rank_chunks_reverse_order() -> None:
    """排名与得分正相关。"""
    chunks = [
        {"content": "进程是资源分配的基本单位线程是CPU调度的基本单位内存管理", "chunk_index": 0},
        {"content": "进程", "chunk_index": 1},
    ]
    results = rank_chunks("进程", chunks)
    scores = [c["score"] for c in results]
    assert scores == sorted(scores, reverse=True)


def test_rank_chunks_filters_non_matching_content() -> None:
    chunks = [
        {"content": "苹果是一种水果", "chunk_index": 0},
        {"content": "香蕉是一种水果", "chunk_index": 1},
    ]
    results = rank_chunks("TCP 三次握手协议", chunks)
    assert results == []


