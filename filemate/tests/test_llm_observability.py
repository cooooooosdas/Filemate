"""Synthetic regression tests for model usage, retry budgets and request isolation."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar, copy_context
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from filemate.llm_client import LLMClient, LLMConfig
from filemate.llm_client.exceptions import LLMAPIError, LLMConfigError, LLMTimeoutError
from filemate.llm_client.request_credentials import model_request_key


@pytest.fixture
def model_server():
    replies = []
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            status, data = replies.pop(0)
            content = json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Request-ID', 'synthetic-request-01')
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = LLMClient(LLMConfig(
        provider='openai_compatible', api_key='synthetic-fixture-only',
        base_url=f'http://127.0.0.1:{server.server_port}/v1', model='synthetic-model',
    ))
    try:
        yield client, replies, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def response(usage=None, text='synthetic reply'):
    data = {'choices': [{'message': {'content': text}}], 'model': 'synthetic-model'}
    if usage is not None:
        data['usage'] = usage
    return data


def test_real_http_usage_is_preserved_and_failure_clears_previous_usage(model_server):
    client, replies, received = model_server
    replies.extend([(200, response({'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10})),
                    (401, {'error': {'message': 'synthetic-secret-must-not-leak'}})])
    assert client.call('Synthetic input', retry=1, timeout=2) == 'synthetic reply'
    assert client.get_usage() == {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}
    assert len(received) == 1
    with pytest.raises(LLMAPIError):
        client.call('Synthetic input', retry=1, timeout=2)
    assert client.get_usage() == {}


@pytest.mark.parametrize('usage,expected', [
    (None, {}), ({}, {}), ('invalid', {}),
    ({'prompt_tokens': 0, 'completion_tokens': 0}, {'prompt_tokens': 0, 'completion_tokens': 0}),
    ({'prompt_tokens': 7}, {'prompt_tokens': 7}),
    ({'prompt_tokens': True, 'completion_tokens': -1, 'total_tokens': 2.5}, {}),
    ({'prompt_tokens': 2**63, 'completion_tokens': '3'}, {}),
])
def test_unknown_and_invalid_usage_never_become_fabricated_zero(model_server, usage, expected):
    client, replies, _ = model_server
    replies.append((200, response(usage)))
    assert client.call(retry=1, timeout=2) == 'synthetic reply'
    assert client.get_usage() == expected


def test_invalid_content_is_rejected_even_with_valid_usage(model_server):
    client, replies, _ = model_server
    replies.append((200, response({'prompt_tokens': 7}, text={'unexpected': 'content'})))
    with pytest.raises(LLMAPIError, match='响应格式'):
        client.call(retry=1, timeout=2)
    assert client.get_usage() == {}


def test_shared_client_usage_is_isolated_between_threads(monkeypatch):
    from filemate.llm_client.models.response import LLMResponse

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only'))
    barrier = threading.Barrier(2)

    def chat(messages, **kwargs):
        count = int(messages[0]['content'])
        return LLMResponse(text='ok', usage={'prompt_tokens': count})

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat, raising=False)

    def run(count):
        client.call(messages=[{'role': 'user', 'content': str(count)}], retry=1)
        barrier.wait(timeout=2)
        return client.get_usage()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, count) for count in (7, 13)]
        assert [future.result(timeout=3) for future in futures] == [
            {'prompt_tokens': 7}, {'prompt_tokens': 13},
        ]
    assert client.get_usage() == {}


def test_shared_client_usage_is_isolated_between_request_contexts(monkeypatch):
    from filemate.llm_client.models.response import LLMResponse

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only'))
    monkeypatch.setattr(client._provider, 'chat_with_metadata',
                        lambda messages, **kwargs: LLMResponse('ok', usage={'prompt_tokens': int(messages[0]['content'])}), raising=False)
    first, second = copy_context(), copy_context()
    for context, count in ((first, 7), (second, 13)):
        context.run(client.call, messages=[{'role': 'user', 'content': str(count)}], retry=1)
    assert first.run(client.get_usage) == {'prompt_tokens': 7}
    assert second.run(client.get_usage) == {'prompt_tokens': 13}


@pytest.mark.parametrize('parameters', [
    {'retry': 0}, {'retry': True}, {'retry': 4}, {'timeout': 0}, {'timeout': float('nan')},
    {'timeout': float('inf')}, {'max_tokens': -1}, {'max_tokens': True},
])
def test_invalid_call_bounds_do_not_send_http(model_server, parameters):
    client, _, received = model_server
    with pytest.raises(LLMConfigError):
        client.call(**parameters)
    assert received == []


def test_retries_share_a_deadline_and_do_not_sleep_after_last_attempt(monkeypatch):
    import filemate.llm_client.client as module
    from filemate.llm_client.exceptions import LLMRateLimitError

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only'))
    clock = [0.0]
    timeouts, sleeps = [], []
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])

    def chat(messages, **kwargs):
        timeouts.append(kwargs['timeout'])
        clock[0] += 0.25
        raise LLMRateLimitError('synthetic rate limit')

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat, raising=False)
    monkeypatch.setattr(module.time, 'sleep', sleep)
    with pytest.raises(LLMAPIError):
        client.call(retry=2, timeout=10)
    assert timeouts == [10, 7.75]
    assert sleeps == [2]


def test_retry_does_not_start_another_request_after_deadline(monkeypatch):
    import filemate.llm_client.client as module

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only'))
    clock, timeouts = [0.0], []
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])

    def chat(messages, **kwargs):
        timeouts.append(kwargs['timeout'])
        clock[0] += kwargs['timeout']
        raise LLMTimeoutError('synthetic timeout')

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat, raising=False)
    with pytest.raises(LLMTimeoutError):
        client.call(retry=3, timeout=1)
    assert timeouts == [1]


def test_registry_never_caches_request_credentials(monkeypatch):
    from filemate.core.registry import ModuleRegistry

    monkeypatch.setattr('filemate.llm_client.config.resolve_api_key',
                        lambda: ('synthetic-shared-only', 'environment'))
    registry = ModuleRegistry()
    with model_request_key('synthetic-account-a-only'):
        first = registry.get_llm()
        assert first.config.api_key == 'synthetic-account-a-only'
        assert registry._llm is None and registry._config is None
    shared = registry.get_llm()
    with model_request_key('synthetic-account-b-only'):
        second = registry.get_llm()
        assert second.config.api_key == 'synthetic-account-b-only'
    assert registry.get_llm() is shared
    assert shared.config.api_key == 'synthetic-shared-only'


@pytest.mark.parametrize('mode', ['parallel', 'serial_then_parallel'])
def test_agent_workers_inherit_request_context_without_cross_worker_mutation(mode):
    from filemate.core.agent_coordinator import Agent, AgentCoordinator
    from filemate.core.session import ProcessingSession
    from filemate.llm_client.request_credentials import REQUEST_API_KEY

    owner = ContextVar('synthetic-test-owner', default='unbound')
    barrier = threading.Barrier(2)

    class ProbeAgent(Agent):
        def execute(self, session, context):
            key, identity = REQUEST_API_KEY.get(), owner.get()
            owner.set(self.name)
            barrier.wait(timeout=3)
            return {'key': key, 'owner': identity, 'own_context': owner.get()}

    coordinator = AgentCoordinator()
    coordinator.add_agent(ProbeAgent('first'))
    coordinator.add_agent(ProbeAgent('second'))
    token = owner.set('synthetic-account-owner')
    try:
        with model_request_key('synthetic-own-only'):
            session = ProcessingSession(session_id='synthetic-session', source_path='synthetic.txt')
            if mode == 'parallel':
                results = coordinator.run_parallel(session)
            else:
                results = coordinator.run_serial_then_parallel(session, [], coordinator._agents)
        assert all(result.success for result in results)
        assert [result.output for result in sorted(results, key=lambda result: result.agent_name)] == [
            {'key': 'synthetic-own-only', 'owner': 'synthetic-account-owner', 'own_context': name}
            for name in ('first', 'second')
        ]
        assert owner.get() == 'synthetic-account-owner'
    finally:
        owner.reset(token)


def test_default_call_honors_config_timeout_and_retry_bound(monkeypatch):
    import filemate.llm_client.client as module
    from filemate.llm_client.models.response import LLMResponse

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only', timeout=2, max_retries=1))
    monkeypatch.setattr(module.time, 'monotonic', lambda: 0)
    captured = []

    def chat(messages, **kwargs):
        captured.append(kwargs['timeout'])
        return LLMResponse('ok')

    monkeypatch.setattr(client._provider, 'chat_with_metadata', chat)
    assert client.call() == 'ok'
    assert captured == [2]


def test_text_only_provider_remains_supported_with_unknown_usage():
    from filemate.llm_client.providers.base import BaseLLMProvider

    class TextProvider(BaseLLMProvider):
        def chat(self, messages, **kwargs):
            return 'text-only provider'

    client = LLMClient(LLMConfig(api_key='synthetic-fixture-only'))
    client._provider = TextProvider()
    assert client.call() == 'text-only provider'
    assert client.get_usage() == {}


def test_provider_returns_bounded_request_metadata_without_changing_chat_contract(model_server):
    client, replies, _ = model_server
    replies.extend([(200, response({'total_tokens': 10})), (200, response())])
    metadata = client._provider.chat_with_metadata([], timeout=2)
    assert metadata.model == 'synthetic-model'
    assert metadata.request_id == 'synthetic-request-01'
    assert metadata.usage == {'total_tokens': 10}
    assert client._provider.chat([], timeout=2) == 'synthetic reply'
