"""合成回归：模型结构校验、旧数组合同和错误内容隔离。"""

import json
import traceback

import pytest

from filemate.llm_client.client import LLMClient
from filemate.llm_client.config import LLMConfig
from filemate.llm_client.exceptions import LLMAPIError, LLMConfigError


@pytest.fixture
def model(monkeypatch):
    client = LLMClient(LLMConfig(api_key="synthetic-regression-only"))
    replies = []
    monkeypatch.setattr(client, "call", lambda **kwargs: replies.pop(0))
    return client, replies


SCHEMA = {
    "type": "object", "required": ["items"], "additionalProperties": False,
    "properties": {"items": {"type": "array", "minItems": 1, "items": {
        "$ref": "#/$defs/item",
    }}},
    "$defs": {"item": {"type": "object", "required": ["count", "status"],
                       "additionalProperties": False,
                       "properties": {"count": {"type": "integer", "minimum": 0},
                                      "status": {"enum": ["grounded", "pending"]}}}},
}


@pytest.mark.parametrize("reply", [
    [], {}, {"items": []}, {"items": [{"count": "2", "status": "grounded"}]},
    {"items": [{"count": True, "status": "grounded"}]},
    {"items": [{"count": -1, "status": "grounded"}]},
    {"items": [{"count": 2, "status": "fabricated"}]},
    {"items": [{"count": 2, "status": "grounded", "secret": "synthetic-private"}]},
])
def test_schema_rejects_wrong_root_nested_types_and_unknown_fields(model, reply):
    client, replies = model
    replies.append(json.dumps(reply))
    with pytest.raises(LLMAPIError, match="数据结构"):
        client.call_structured(schema=SCHEMA)


def test_internal_references_fenced_json_and_legacy_array(model):
    client, replies = model
    data = {"items": [{"count": 2, "status": "grounded"}]}
    replies.extend(["```json\n" + json.dumps(data) + "\n```", '[{"event":"答辩"}]', '[1,2]'])
    assert client.call_structured(schema=SCHEMA) == data
    assert client.call_structured() == [{"event": "答辩"}]
    assert client.call_structured(schema={"type": "array", "items": {"type": "integer"}}) == [1, 2]


@pytest.mark.parametrize("reply", [
    'not-json-synthetic-private', '{"secret":"synthetic-private",broken}',
    '{"value":NaN}', '{"value":Infinity}', '{"value":-Infinity}',
    '{"value":1e400}', 'null', 'true', '123', '"synthetic-private"',
])
def test_invalid_output_does_not_leak_private_text_in_traceback(model, reply):
    client, replies = model
    replies.append(reply)
    with pytest.raises(LLMAPIError) as error:
        client.call_structured()
    formatted = "".join(traceback.format_exception(error.type, error.value, error.tb))
    assert "synthetic-private" not in formatted


@pytest.mark.parametrize("schema", [
    {"type": "unknown"}, {"$schema": "https://example.invalid/unsupported"},
    {"type": "array", "items": {"type": 42}},
])
def test_invalid_schema_is_rejected_before_spending_model_budget(model, schema):
    client, replies = model
    client._remember_usage({"total_tokens": 9})
    replies.append('{"untouched":true}')
    with pytest.raises(LLMConfigError):
        client.call_structured(schema=schema)
    assert len(replies) == 1
    assert client.get_usage() == {}


@pytest.mark.parametrize("reference", ["https://example.invalid/private", "file:///private.json"])
def test_schema_references_cannot_fetch_network_or_local_files(model, monkeypatch, reference):
    import urllib.request

    def forbidden(*args, **kwargs):
        pytest.fail("Schema must not fetch external resources")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    client, replies = model
    replies.append('{"private":"synthetic-private"}')
    with pytest.raises(LLMAPIError, match="数据结构"):
        client.call_structured(schema={"$ref": reference})
