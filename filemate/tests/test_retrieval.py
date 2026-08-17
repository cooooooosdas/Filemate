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
