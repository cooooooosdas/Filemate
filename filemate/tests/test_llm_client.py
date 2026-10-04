import ast
from pathlib import Path

import pytest

import filemate.llm_client.config as config_module
from filemate.llm_client.client import LLMClient
from filemate.llm_client.config import LLMConfig
from filemate.llm_client.exceptions import LLMAccessError, LLMConfigError
from filemate.llm_client.providers.openai_compatible import OpenAICompatibleProvider


class _FakeResponse:
    status_code = 200

    @staticmethod
    def json() -> dict:
        return {"choices": [{"message": {"content": "OK"}}]}


class _FakeAccessDeniedResponse:
    status_code = 401
    text = '{"error":{"type":"billing_error","message":"credit exhausted"}}'


def test_deepseek_base_url_uses_openai_compatible_provider() -> None:
    config = LLMConfig(
        provider="auto",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    provider = LLMClient._build(config)
    assert isinstance(provider, OpenAICompatibleProvider)


def test_default_config_uses_deepseek_v4_flash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)

    config = LLMConfig.from_env()

    assert config.provider == "deepseek"
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-flash"


def test_config_uses_secure_store_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "environment-key")
    monkeypatch.setattr(
        config_module,
        "resolve_api_key",
        lambda: ("secure-user-key", "secure_store"),
    )

    config = LLMConfig.from_env()

    assert config.api_key == "secure-user-key"


def test_unknown_legacy_config_is_rejected_without_sending_key() -> None:
    config = LLMConfig(
        provider="auto",
        api_key="legacy-key",
        base_url="https://legacy-model.example/v1",
        model="legacy-flash",
    )

    with pytest.raises(LLMConfigError, match="无法从 LLM_BASE_URL"):
        LLMClient._build(config)


def test_deepseek_disables_thinking(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, headers: dict, timeout: float, **kwargs) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["redirects"] = kwargs["allow_redirects"]
        return _FakeResponse()

    monkeypatch.setattr(
        "filemate.llm_client.providers.openai_compatible.requests.post",
        fake_post,
    )

    config = LLMConfig(
        provider="deepseek",
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )
    provider = OpenAICompatibleProvider(config)
    text = provider.chat(
        [{"role": "user", "content": "hi"}],
        max_tokens=32,
    )

    assert text == "OK"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["redirects"] is False


def test_access_error_is_explicit_and_not_retried(monkeypatch) -> None:
    calls = 0

    def fake_post(url: str, json: dict, headers: dict, timeout: float, **kwargs):
        nonlocal calls
        del url, json, headers, timeout
        calls += 1
        return _FakeAccessDeniedResponse()

    monkeypatch.setattr(
        "filemate.llm_client.providers.openai_compatible.requests.post",
        fake_post,
    )
    client = LLMClient(
        LLMConfig(
            provider="deepseek",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
    )

    with pytest.raises(LLMAccessError, match="密钥、余额和账号权限"):
        client.call(messages=[{"role": "user", "content": "hi"}], retry=3)

    assert calls == 1


@pytest.mark.parametrize("base", [
    "https://api.deepseek.com.attacker.example", "http://api.deepseek.com",
    "https://api.deepseek.com@attacker.example", "https://api.deepseek.com/redirect",
    "https://api.deepseek.com?token=anything",
])
def test_deepseek_rejects_nonofficial_destination_before_sending_key(base):
    with pytest.raises(LLMConfigError, match="官方"):
        LLMClient(LLMConfig(api_key="sk-synthetic-only", base_url=base))


def test_request_key_is_private_and_ignores_shared_provider_override(monkeypatch):
    from filemate.llm_client.request_credentials import model_request_key

    monkeypatch.setattr(config_module, "resolve_api_key", lambda: ("sk-shared", "environment"))
    monkeypatch.setenv("LLM_BASE_URL", "https://attacker.example")
    with model_request_key("sk-own-synthetic-only"):
        config = LLMConfig.from_env()
        assert config.api_key == "sk-own-synthetic-only"
        assert config.base_url == "https://api.deepseek.com"
        assert config.provider == "deepseek"
        assert "sk-own-synthetic-only" not in repr(config)
    assert LLMConfig.from_env().api_key == "sk-shared"


@pytest.mark.parametrize("status", [401, 402, 403, 404, 500, 302])
def test_upstream_error_never_echoes_credential(status, monkeypatch):
    from filemate.llm_client.exceptions import LLMAPIError

    response = type("Response", (), {"status_code": status, "text": "sk-sensitive-upstream-echo"})()
    monkeypatch.setattr("filemate.llm_client.providers.openai_compatible.requests.post", lambda *args, **kwargs: response)
    with pytest.raises(LLMAPIError) as raised:
        LLMClient(LLMConfig(api_key="sk-sensitive-upstream-echo")).call(retry=1)
    assert "sk-sensitive" not in str(raised.value)


def test_all_model_routes_accept_scoped_credentials():
    import re

    from filemate.llm_client.request_credentials import is_model_request

    source = Path(__file__).resolve().parents[2] / "server.py"
    routes = []
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        uses_llm = any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "LLMClient" for call in ast.walk(node))
        if not uses_llm:
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "post":
                routes.append(re.sub(r"\{[^}]+\}", "synthetic", decorator.args[0].value))
    assert len(routes) >= 12
    assert all(is_model_request("POST", path) for path in routes)
