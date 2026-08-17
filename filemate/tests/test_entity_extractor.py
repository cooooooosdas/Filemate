"""实体抽取模块单元测试。

全部用 _Stub 假 LLM，不产生真实 API 调用，CI 可直接跑。
"""
from __future__ import annotations

import pytest

from filemate.understanding.entity_extractor import ENTITY_FIELDS, EntityExtractor


class _Stub:
    """可配置的假 LLM 客户端。

    Parameters
    ----------
    payload
        call_structured 的返回值。
    raises
        非 None 时，call_structured 抛出该异常。
    """

    def __init__(self, payload=None, raises: Exception | None = None) -> None:
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def call_structured(self, prompt="", messages=None, **kw):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.payload

    def call(self, prompt="", messages=None, **kw):
        return ""


_FULL_PAYLOAD = {
    "course_name": "操作系统",
    "task_description": "实验三 进程调度",
    "deadline": "2026-04-15",
    "location": "实验楼 A301",
    "extra_entities": {"teacher": "蒋社想"},
}


class TestEntityExtractorEmptyText:
    """空文本走 fallback，不应调用 LLM。"""

    @pytest.mark.parametrize("text", ["", "   ", "\n\t "])
    def test_empty_text_returns_empty_result(self, text: str) -> None:
        stub = _Stub(payload=_FULL_PAYLOAD)
        result = EntityExtractor(stub).extract(text)

        assert stub.calls == 0, "空文本不该触发 LLM 调用"
        assert result["extra_entities"] == {}
        for field in ENTITY_FIELDS[:-1]:
            assert result[field] is None


class TestEntityExtractorNormal:
    """正常抽取。"""

    def test_all_fields_present(self) -> None:
        result = EntityExtractor(_Stub(payload=_FULL_PAYLOAD)).extract("某课程通知全文")
        for field in ENTITY_FIELDS:
            assert field in result, f"输出缺少字段: {field}"

    def test_values_passed_through(self) -> None:
        result = EntityExtractor(_Stub(payload=_FULL_PAYLOAD)).extract("某课程通知全文")
        assert result["course_name"] == "操作系统"
        assert result["task_description"] == "实验三 进程调度"
        assert result["deadline"] == "2026-04-15"
        assert result["location"] == "实验楼 A301"
        assert result["extra_entities"] == {"teacher": "蒋社想"}

    def test_file_type_stripped(self) -> None:
        """LLM 返回的 file_type 是内部判断用字段，不应出现在输出契约里。"""
        payload = {**_FULL_PAYLOAD, "file_type": "course"}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert "file_type" not in result

    def test_empty_string_normalized_to_none(self) -> None:
        payload = {**_FULL_PAYLOAD, "course_name": "", "location": ""}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["course_name"] is None
        assert result["location"] is None


class TestEntityExtractorDeadlineValidation:
    """deadline 只接受 YYYY-MM-DD。"""

    @pytest.mark.parametrize(
        "bad_deadline",
        ["下周五", "2026/04/15", "4月15日", "2026-4-15", "2026-04-15 18:00", "尽快"],
    )
    def test_invalid_deadline_discarded(self, bad_deadline: str) -> None:
        payload = {**_FULL_PAYLOAD, "deadline": bad_deadline}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["deadline"] is None, f"非法格式 {bad_deadline} 应被丢弃"

    def test_valid_deadline_kept(self) -> None:
        payload = {**_FULL_PAYLOAD, "deadline": "2026-12-31"}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["deadline"] == "2026-12-31"


class TestEntityExtractorExtraEntities:
    """extra_entities 缺省或为 null 时应回落到空字典。"""

    @pytest.mark.parametrize("value", [None, {}, "", 0])
    def test_falsy_extra_entities_becomes_dict(self, value) -> None:
        payload = {**_FULL_PAYLOAD, "extra_entities": value}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["extra_entities"] == {}

    def test_missing_extra_entities_key(self) -> None:
        payload = {k: v for k, v in _FULL_PAYLOAD.items() if k != "extra_entities"}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["extra_entities"] == {}


class TestEntityExtractorFailure:
    """LLM 异常/返回非法类型时的兜底。

    重试次数为 3（W4 联调发现 LLM 高频返回空字符串，原 2 次顶不住）。
    """

    def test_exception_returns_empty_after_retry(self) -> None:
        stub = _Stub(raises=RuntimeError("API 超时"))
        result = EntityExtractor(stub).extract("正文")

        assert stub.calls == 3, "应重试两次（共 3 次尝试）"
        assert result["extra_entities"] == {}
        for field in ENTITY_FIELDS[:-1]:
            assert result[field] is None

    @pytest.mark.parametrize("bad_payload", [None, [], "字符串", 42])
    def test_non_dict_payload_returns_empty(self, bad_payload) -> None:
        stub = _Stub(payload=bad_payload)
        result = EntityExtractor(stub).extract("正文")

        assert stub.calls == 3, "非字典返回应触发重试至上限"
        for field in ENTITY_FIELDS[:-1]:
            assert result[field] is None


class TestEntityExtractorFlatten:
    """extra_entities 必须压平成一层，否则会撑爆 max_tokens 导致 JSON 截断。"""

    def test_nested_dict_flattened(self) -> None:
        payload = {**_FULL_PAYLOAD, "extra_entities": {
            "organizer": "校团委",
            "contact": {"name": "张老师", "phone": "123"},
        }}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        extra = result["extra_entities"]

        assert extra["organizer"] == "校团委"
        assert extra["contact.name"] == "张老师"
        assert extra["contact.phone"] == "123"
        assert "contact" not in extra, "嵌套子对象本身不应保留"

    def test_list_joined(self) -> None:
        payload = {**_FULL_PAYLOAD, "extra_entities": {"tags": ["竞赛", "校级", "报名"]}}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["extra_entities"]["tags"] == "竞赛, 校级, 报名"

    def test_scalar_untouched(self) -> None:
        payload = {**_FULL_PAYLOAD, "extra_entities": {"count": 3, "name": "x"}}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["extra_entities"] == {"count": 3, "name": "x"}

    @pytest.mark.parametrize("bad", [None, [], "字符串", 42, 0])
    def test_non_dict_extra_becomes_empty(self, bad) -> None:
        payload = {**_FULL_PAYLOAD, "extra_entities": bad}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        assert result["extra_entities"] == {}

    def test_flattened_result_has_no_nested_values(self) -> None:
        """压平后不应再有任何 dict 类型的值 —— 这是 Namer 能安全读取的前提。"""
        payload = {**_FULL_PAYLOAD, "extra_entities": {
            "a": {"b": "c"}, "d": ["e", "f"], "g": "h",
        }}
        result = EntityExtractor(_Stub(payload=payload)).extract("正文")
        for key, val in result["extra_entities"].items():
            assert not isinstance(val, (dict, list)), f"{key} 仍是嵌套结构: {val!r}"
