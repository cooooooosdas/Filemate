from filemate.execution.storage import SQLiteStorage
from filemate.understanding.interview import (
    InterviewEvaluator,
    build_interview_questions,
    build_source_grounded_question,
    build_wrong_grounded_question,
    generate_interview_questions_with_llm,
    select_question_ids_with_llm,
)


class FakeLLM:
    def __init__(self, payload) -> None:
        self.payload = payload

    def call(self, **kwargs):
        return self.payload


def test_interview_fluency_is_explicit_and_low_weight() -> None:
    answer = "我先分析问题，再制定方案并完成验证。" * 10
    result = InterviewEvaluator(None).evaluate(
        "请介绍一个项目。",
        answer,
        "后端开发",
        {
            "duration_seconds": 60,
            "filler_count": 2,
            "long_pause_count": 1,
            "source": "speech_recognition",
            "markers": [
                {"second": 8.4, "kind": "filler", "label": "任意前端文案"},
                {"second": 24.2, "kind": "long_pause", "label": "任意前端文案"},
            ],
        },
    )

    assert "流畅性" in result["dimensions"]
    assert result["fluency"]["chars_per_minute"] > 0
    assert result["fluency"]["filler_count"] == 2
    assert result["fluency"]["long_pause_count"] == 1
    assert result["fluency"]["markers"] == [
        {"second": 8.4, "kind": "filler", "label": "出现口头语"},
        {"second": 24.2, "kind": "long_pause", "label": "较长停顿"},
    ]
    assert "语音节奏参考" in result["feedback"]


def test_typed_interview_answer_does_not_invent_fluency() -> None:
    result = InterviewEvaluator(None).evaluate(
        "请介绍一个项目。",
        "我负责接口设计和测试。",
        "后端开发",
    )

    assert "流畅性" not in result["dimensions"]
    assert "fluency" not in result


def _make_storage(tmp_path):
    storage = SQLiteStorage(tmp_path / "interview-ai.db")
    storage.init_schema()
    return storage


def test_select_question_ids_validates_and_deduplicates() -> None:
    candidates = [
        {"id": "a", "text": "问题 A"},
        {"id": "b", "text": "问题 B"},
        {"id": "c", "text": "问题 C"},
    ]
    llm = FakeLLM('["a", "c", "missing", "a"]')
    picked = select_question_ids_with_llm(
        llm,
        candidates,
        target_role="Java 后端",
        scenario="求职面试",
        difficulty="标准",
        limit=5,
    )
    assert picked == ["a", "c"]


def test_generate_interview_questions_deduplicates_and_limits() -> None:
    llm = FakeLLM('["题目一", "题目一", "题目二"]')
    questions = generate_interview_questions_with_llm(
        llm,
        target_role="软件杯答辩",
        scenario="竞赛答辩",
        difficulty="压力面",
        count=5,
    )
    assert questions == ["题目一", "题目二"]


def test_source_grounded_question_names_selected_evidence() -> None:
    question = build_source_grounded_question(
        "FileMate 项目申报书.pdf",
        "竞赛答辩",
        "创新赛道",
    )

    assert "FileMate 项目申报书.pdf" in question
    assert "材料中能够支撑" in question


def test_wrong_grounded_question_uses_stem_without_reference_answer() -> None:
    question = build_wrong_grounded_question(
        "数据库课件",
        {"question": "B+ 树为什么适合范围查询？", "answer": "叶子节点有序"},
    )

    assert "B+ 树为什么适合范围查询" in question
    assert "数据库课件" in question
    assert "叶子节点有序" not in question


def test_wrong_grounded_question_applies_confirmed_error_cause() -> None:
    question = build_wrong_grounded_question(
        "算法课件",
        {"stem": "说明 BFS 的执行过程", "answer": "使用队列逐层访问"},
        error_cause="reasoning_break",
        knowledge_label="广度优先搜索",
    )

    assert "广度优先搜索" in question
    assert "条件、步骤、结论" in question
    assert "使用队列逐层访问" not in question


def test_build_interview_questions_ai_selects_then_fills_deterministically(
    tmp_path,
) -> None:
    storage = _make_storage(tmp_path)
    ids = [
        storage.create_interview_question(
            scenario="求职面试",
            difficulty="标准",
            text=f"求职标准题 {index}",
        )
        for index in range(8)
    ]
    llm = FakeLLM(f'["{ids[0]}", "{ids[1]}"]')

    questions, question_ids = build_interview_questions(
        storage,
        llm,
        scenario="求职面试",
        difficulty="标准",
        target_role="Java 后端",
        limit=5,
    )

    assert len(questions) == 5
    assert question_ids[:2] == [ids[0], ids[1]]
    assert len(question_ids) == 5


def test_build_interview_questions_isolates_scenario_and_difficulty(tmp_path) -> None:
    storage = _make_storage(tmp_path)
    expected_ids = [
        storage.create_interview_question(
            scenario="求职面试",
            difficulty="标准",
            text=f"求职标准题 {index}",
        )
        for index in range(5)
    ]
    wrong_scenario_id = storage.create_interview_question(
        scenario="竞赛答辩",
        difficulty="标准",
        text="竞赛标准题",
    )
    wrong_difficulty_id = storage.create_interview_question(
        scenario="求职面试",
        difficulty="压力面",
        text="求职压力题",
    )
    llm = FakeLLM(f'["{wrong_scenario_id}", "{wrong_difficulty_id}"]')

    questions, question_ids = build_interview_questions(
        storage,
        llm,
        scenario="求职面试",
        difficulty="标准",
        target_role="Java 后端",
        limit=5,
    )

    assert set(question_ids) == set(expected_ids)
    assert all(question.startswith("求职标准题") for question in questions)


def test_build_interview_questions_generates_when_bank_is_insufficient(
    tmp_path,
) -> None:
    storage = _make_storage(tmp_path)
    storage.create_interview_question(
        scenario="竞赛答辩",
        difficulty="压力面",
        text="竞赛压力题一",
    )
    storage.create_interview_question(
        scenario="竞赛答辩",
        difficulty="压力面",
        text="竞赛压力题二",
    )
    llm = FakeLLM('["AI 补题一", "AI 补题二", "AI 补题三"]')

    questions, question_ids = build_interview_questions(
        storage,
        llm,
        scenario="竞赛答辩",
        difficulty="压力面",
        target_role="软件杯答辩",
        limit=5,
    )

    assert len(questions) == 5
    assert any("AI 补题" in question for question in questions)
    assert len([question_id for question_id in question_ids if question_id]) == 2
    assert question_ids[2:] == [None, None, None]


def test_build_interview_questions_falls_back_without_llm(tmp_path) -> None:
    storage = _make_storage(tmp_path)
    for index in range(3):
        storage.create_interview_question(
            scenario="保研复试",
            difficulty="入门",
            text=f"保研入门题 {index}",
        )

    questions, question_ids = build_interview_questions(
        storage,
        None,
        scenario="保研复试",
        difficulty="入门",
        target_role="计算机方向",
        limit=5,
    )

    assert len(questions) == 5
    assert len([question_id for question_id in question_ids if question_id]) == 3
