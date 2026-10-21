"""Synthetic adversarial citation and relation validation cases."""

import importlib

import pytest


def extraction():
    return importlib.import_module("filemate.course_graph.extraction")


def validate(payload, text, chunks=None):
    return extraction().validate_candidates(payload, text, "synthetic-source", chunks or [])


def test_partial_invalid_keeps_valid():
    text = "栈：后进先出。"
    payload = {"nodes": [{"label": "栈", "excerpt": text},
                         {"label": "队列", "excerpt": "伪造引用"}], "edges": []}
    result = validate(payload, text)
    assert [n["validation"] for n in result["nodes"]] == ["valid", "invalid"]
    assert result["nodes"][0]["parsed"]["excerpt"] == text
    assert result["nodes"][1]["decision"] == "pending"
    assert "quote_not_found" in result["nodes"][1]["error_codes"]
    assert result["nodes"][0]["item_id"] == validate(payload, text)["nodes"][0]["item_id"]


def pair(text, relation="prerequisite", left="栈", right="队列"):
    return {"nodes": [{"label": term, "excerpt": text} for term in [left, right]],
            "edges": [{"from": left, "to": right, "relation": relation, "excerpt": text}]}


def test_cooccurrence_is_not_prerequisite():
    text = "栈和队列都是线性结构。"
    item = validate(pair(text), text)["edges"][0]
    assert item["validation"] == "invalid"
    assert "unsupported_relation" in item["error_codes"]


@pytest.mark.parametrize("text,left,right,expected", [
    ("栈是DFS的前置知识。", "栈", "DFS", "valid"),
    ("栈是DFS的前置知识。", "DFS", "栈", "invalid"),
    ("栈不是DFS的前置知识。", "栈", "DFS", "invalid"),
    ("栈可能是DFS的前置知识。", "栈", "DFS", "invalid"),
])
def test_explicit_direction_and_negation(text, left, right, expected):
    assert validate(pair(text, left=left, right=right), text)["edges"][0]["validation"] == expected


def test_literal_aliases_only():
    text = "Stack（栈）：后进先出的线性表。BFS：按层遍历。"
    result = validate({"nodes": [
        {"label": "Stack", "aliases": ["栈"], "excerpt": "Stack（栈）：后进先出的线性表。"},
        {"label": "BFS", "aliases": ["广度优先搜索"], "excerpt": "BFS：按层遍历。"},
    ], "edges": []}, text)
    assert [n["validation"] for n in result["nodes"]] == ["valid", "invalid"]
    assert result["nodes"][0]["parsed"]["aliases"] == ["栈"]
    assert "unsupported_alias" in result["nodes"][1]["error_codes"]


def test_envelope_limits_and_missing_pages():
    with pytest.raises(ValueError, match="invalid_envelope"):
        validate({"nodes": [{"label": "栈", "excerpt": "栈"}] * 81, "edges": []}, "栈")
    result = validate({"nodes": [{"label": "栈", "excerpt": "栈"}], "edges": []}, "栈")
    assert result["nodes"][0]["parsed"]["page"] is None
    assert result["nodes"][0]["parsed"]["char_start"] == 0
    assert result["nodes"][0]["parsed"]["char_end"] == 1


def test_definition_is_literal_and_extra_fields_invalid():
    result = validate({"nodes": [
        {"label": "栈", "definition": "先进先出", "excerpt": "栈：后进先出。"},
        {"label": "栈", "excerpt": "栈：后进先出。", "mastery": 100},
    ], "edges": []}, "栈：后进先出。")
    assert all(n["validation"] == "invalid" for n in result["nodes"])
    assert "unsupported_definition" in result["nodes"][0]["error_codes"]
    assert "invalid_item" in result["nodes"][1]["error_codes"]


def test_dangling_endpoints_and_unknown_type_rejected():
    p = {"nodes": [{"label": "栈", "excerpt": "栈依赖数组。"}], "edges": [
        {"from": "栈", "to": "数组", "relation": "depends_on", "excerpt": "栈依赖数组。"},
        {"from": "栈", "to": "栈", "relation": "delete_data", "excerpt": "栈依赖数组。"},
    ]}
    result = validate(p, "栈依赖数组。")
    assert all(e["validation"] == "invalid" for e in result["edges"])
    assert "missing_endpoint" in result["edges"][0]["error_codes"]


def test_local_rules_extract_definitions_and_explicit_aliases():
    text = "栈：后进先出的线性表。Stack（栈）：同一个术语的原文明示。栈是DFS的前置知识。"
    p = extraction().extract_local_course(text)
    assert any(n["label"] == "Stack" and n["aliases"] == ["栈"] for n in p["nodes"])
    result = validate(p, text)
    assert result["edges"][0]["validation"] == "valid"
    assert not result["issues"]


def test_coverage_and_original_bad_fields_are_bounded():
    p = {"nodes": [{"label": "栈", "excerpt": "栈"}, {"label": "x" * 10_000}], "edges": []}
    result = validate(p, "栈" * 20_001)
    assert result["coverage"] == {"input_characters": 20_000, "source_truncated": True}
    assert len(result["nodes"][1]["original"]["label"]) <= 120


def test_provider_one_call_with_envelope_schema_and_no_silent_retry():
    class Client:
        def __init__(self):
            self.calls = []

        def call_structured(self, **kwargs):
            self.calls.append(kwargs)
            raise RuntimeError("synthetic provider failure")

    client = Client()
    with pytest.raises(RuntimeError):
        extraction().CourseGraphProvider(client).extract("栈" * 20_001)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["timeout"] == 45 and call["retry"] == 1 and call["max_tokens"] == 6000
    assert call["schema"]["properties"]["nodes"]["maxItems"] == 80
    assert len(call["messages"][0]["content"]) == 20_000
