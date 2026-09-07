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

    def fake_post(url: str, json: dict, headers: dict, timeout: float) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = json
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


def test_access_error_is_explicit_and_not_retried(monkeypatch) -> None:
    calls = 0

    def fake_post(url: str, json: dict, headers: dict, timeout: float):
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
