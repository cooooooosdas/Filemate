"""学习增强算法与现役错题存储的回归测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from filemate.execution.storage import SQLiteStorage
from filemate.study import (
    REVIEW_INTERVALS,
    check_answer,
    chunk_text,
    is_due,
    next_review_date_str,
    review_stage_after,
)
from filemate.study.generator import (
    analyze_document_with_llm,
    generate_questions_with_llm,
)


def test_chunk_text_handles_empty_and_short_text() -> None:
    assert chunk_text("") == []
    assert chunk_text("第一段\n第二段") == ["第一段\n第二段"]


def test_chunk_text_does_not_duplicate_buffer_before_long_paragraph() -> None:
    chunks = chunk_text("短段\n" + "甲" * 12, chunk_size=10, overlap=2)

    assert chunks == ["短段", "甲" * 10, "甲" * 4]
    assert "短段" not in chunks[-1]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (10, -1), (10, 10)],
)
def test_chunk_text_rejects_invalid_window(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("内容", chunk_size=chunk_size, overlap=overlap)


def test_generate_and_analyze_require_llm() -> None:
    with pytest.raises(RuntimeError, match="AI 分析失败"):
        analyze_document_with_llm(None, "test.md", ["内容"])
    with pytest.raises(RuntimeError, match="AI 出题失败"):
        generate_questions_with_llm(None, "数学", "线性代数", count=3)


def test_generate_questions_normalizes_and_deduplicates() -> None:
    def fake_llm(**_kwargs):
        return [
            {
                "question_type": "choice",
                "stem": "矩阵乘法满足什么性质？",
                "options": ["A. 结合律", "B. 交换律"],
                "answer": "A",
            },
            {
                "question_type": "choice",
                "stem": "矩阵乘法满足什么性质？",
                "answer": "A",
            },
        ]

    questions = generate_questions_with_llm(
        fake_llm,
        "数学",
        "线性代数",
        count=3,
        question_type="choice",
    )

    assert len(questions) == 1
    assert questions[0]["subject"] == "数学"


def test_check_answer_handles_choice_fill_and_short_answer() -> None:
    assert check_answer({"question_type": "choice", "answer": "A"}, "A. 结合律")
    assert not check_answer({"question_type": "choice", "answer": "A"}, "")
    assert check_answer({"question_type": "fill", "answer": "线性表"}, "线性表")
    assert not check_answer({"question_type": "fill", "answer": "线性表"}, "")
    assert check_answer(
        {"question_type": "short_answer", "answer": "栈 先进后出 线性"},
        "栈是一种先进后出的线性结构",
    )


def test_review_schedule_boundaries() -> None:
    today = date(2026, 8, 8)

    assert REVIEW_INTERVALS == {1: 1, 2: 3, 3: 7, 4: 15, 5: 30}
    assert review_stage_after(5) == 5
    assert next_review_date_str(2, today) == "2026-08-11"
    assert is_due("2026-08-08", today)
    assert not is_due("invalid", today)


def test_wrong_answer_resets_mastered_question(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "study.db")
    storage.init_schema()
    source_id = storage.save_source(
        original_name="数据结构.txt",
        source_path=str(tmp_path / "数据结构.txt"),
        raw_text="栈是先进后出的线性结构。",
    )
    artifact_id = storage.save_artifact(
        artifact_type="questions",
        source_id=source_id,
        content=[{"question": "栈的特点？", "answer": "先进后出"}],
    )

    storage.record_quiz_attempt(
        artifact_id=artifact_id,
        question_index=0,
        user_answer="先进先出",
        is_correct=False,
        score=0.0,
        feedback="错误",
    )
    for _ in range(2):
        storage.record_quiz_attempt(
            artifact_id=artifact_id,
            question_index=0,
            user_answer="先进后出",
            is_correct=True,
            score=1.0,
            feedback="正确",
        )
    assert storage.list_wrong_questions(mastered=True)

    storage.record_quiz_attempt(
        artifact_id=artifact_id,
        question_index=0,
        user_answer="先进先出",
        is_correct=False,
        score=0.0,
        feedback="错误",
    )

    pending = storage.list_wrong_questions(mastered=False)
    assert len(pending) == 1
    assert pending[0]["correct_streak"] == 0
    assert pending[0]["interval_days"] == 0
