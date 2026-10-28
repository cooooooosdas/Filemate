"""HTTP owner, consent, switches, model credentials and safe failures."""
# ruff: noqa: F811

import pytest
from fastapi.testclient import TestClient

from filemate.llm_client.request_credentials import is_model_request
from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.tests.wrongbook.test_api import seed
from filemate.wrongbook.analysis_repository import ReviewAnalysisRepository
from filemate.wrongbook.learning_context import ReviewLearningContext
from filemate.wrongbook.repository import ReviewRepository


def test_only_exact_analysis_route_accepts_model_credentials():
    path = '/wrongbook/v2/w/analyses'
    assert is_model_request('POST', path)
    for suffix in ('/extra', '?key=x', '/id', '/id/cancel', '/id/adoption-confirm'):
        assert not is_model_request('POST', path+suffix)
    assert not is_model_request('GET', path)


@pytest.mark.parametrize('change', [{'allow_external_model': False}, {'allow_external_model': 1},
                                  {'unexpected': 'never-echo-sensitive-data'}])
def test_api_rejects_missing_or_fake_consent(server_module, monkeypatch, change):
    module, store = server_module
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '1')
    result = ReviewRepository(store).submit(seed(store))
    context = ReviewLearningContext(store).build(result['wrong_id'], result['attempt_id'])
    body = {'attempt_id': result['attempt_id'], 'input_digest': context['input_digest'],
        'request_key': 'synthetic-http-analysis-0001', 'allow_external_model': True, **change}
    with TestClient(module.app) as client:
        response = client.post(f"/wrongbook/v2/{result['wrong_id']}/analyses", json=body)
        assert response.status_code == 422, response.text
        assert 'never-echo-sensitive-data' not in response.text
    assert store._conn().execute('SELECT COUNT(*) FROM wrong_review_analyses').fetchone()[0] == 0


def test_disabled_still_reads_and_cancels(server_module, monkeypatch):
    module, store = server_module
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '1')
    answer = ReviewRepository(store).submit(seed(store))
    context = ReviewLearningContext(store).build(answer['wrong_id'], answer['attempt_id'])
    view, _, _ = ReviewAnalysisRepository(store).claim(context, 'synthetic-disabled-analysis-0001')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '0')
    base = f"/wrongbook/v2/{answer['wrong_id']}"
    with TestClient(module.app) as client:
        assert client.get('/wrongbook/v2/capabilities').json()['data']['analysis_enabled'] is False
        assert client.get(base+'/analyses').status_code == 200
        assert client.get(base+'/analyses/'+view['analysis_id']).status_code == 200
        assert client.get('/wrongbook/v2/analysis-requests/synthetic-disabled-analysis-0001').status_code == 200
        assert client.post(base+'/analyses', json={'attempt_id': answer['attempt_id'],
            'input_digest': context['input_digest'], 'request_key': 'synthetic-disabled-analysis-0002', 'allow_external_model': True}).status_code == 503
        response = client.post(base+'/analyses/'+view['analysis_id']+'/cancel', json={'request_key': 'synthetic-http-cancel-0001'})
        assert response.status_code == 200 and response.json()['data']['status'] == 'cancelled'


def test_two_accounts_cannot_read_analysis_context_or_receipts(account_server, monkeypatch):
    from filemate.llm_client.bounded_call import BoundedLLMRunner

    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '1')
    monkeypatch.setattr(BoundedLLMRunner, 'run', lambda *args, **kwargs: {'error_code': 'provider_unavailable'})
    with TestClient(account_server.app) as alice, TestClient(account_server.app) as bob:
        assert register(alice, keep_guest_data=False).status_code == 200
        assert register(bob, email='other@example.invalid', keep_guest_data=False).status_code == 200
        imported = alice.post('/knowledge/import', files={'file': ('synthetic.txt', '合成栈与队列'.encode(), 'text/plain')})
        sid = imported.json()['data']['source_id']
        store = next(s for s in account_server._tenant_storages.values() if s.get_source(sid))
        question = {'question_type': 'fill', 'stem': '栈的次序', 'answer': '后进先出'}
        artifact_id = store.save_artifact(source_id=sid, artifact_type='questions', content=[question])
        # 合成题集仅在测试夹具入库，认证与作答仍走真实HTTP路由。
        answer = alice.post('/wrongbook/v2/attempts', json={'artifact_id': artifact_id,
            'question_index': 0, 'expected_question': question, 'action': 'dont_know',
            'request_key': 'synthetic-private-answer-0001'}).json()['data']
        assert bob.get(f"/wrongbook/v2/{answer['wrong_id']}/learning-context?attempt_id={answer['attempt_id']}").status_code == 404
        context = alice.get(f"/wrongbook/v2/{answer['wrong_id']}/learning-context?attempt_id={answer['attempt_id']}").json()['data']
        view = alice.post(f"/wrongbook/v2/{answer['wrong_id']}/analyses", json={
            'attempt_id': answer['attempt_id'], 'input_digest': context['input_digest'],
            'request_key': 'synthetic-private-analysis-0001', 'allow_external_model': True})
        assert view.status_code == 200 and view.json()['data']['status'] == 'failed'
        assert bob.get(f"/wrongbook/v2/{answer['wrong_id']}/analyses/{view.json()['data']['analysis_id']}").status_code == 404
        assert bob.get('/wrongbook/v2/analysis-requests/synthetic-private-analysis-0001').status_code == 404


def test_http_browser_key_is_transient_and_provider_failure_is_not_account_401(server_module, monkeypatch):
    from filemate.llm_client import LLMConfig
    from filemate.llm_client.bounded_call import BoundedLLMRunner
    from filemate.llm_client.request_credentials import REQUEST_API_KEY

    module, store = server_module
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_AI', '1')
    answer = ReviewRepository(store).submit(seed(store))
    calls = []
    def fail_provider(self, config, scope, **kwargs):
        calls.append(config)
        return {'error_code': 'provider_unavailable'}
    monkeypatch.setattr(BoundedLLMRunner, 'run', fail_provider)
    # 模拟服务器另配Provider，浏览器凭据仍只允许固定DeepSeek端点。
    monkeypatch.setenv('LLM_PROVIDER', 'openai_compatible')
    monkeypatch.setenv('LLM_BASE_URL', 'http://127.0.0.1:9')
    monkeypatch.setenv('LLM_MODEL', 'different-model')
    path = f"/wrongbook/v2/{answer['wrong_id']}/analyses"
    headers = {'Origin': next(iter(module.CORS_ORIGINS)), 'X-FileMate-Action': 'model',
        'X-FileMate-LLM-Key': 'synthetic-never-real-key'}
    with TestClient(module.app) as client:
        context = client.get(f"/wrongbook/v2/{answer['wrong_id']}/learning-context?attempt_id={answer['attempt_id']}&credential_mode=browser").json()['data']
        body = {'attempt_id': answer['attempt_id'], 'input_digest': context['input_digest'],
            'request_key': 'synthetic-key-boundary-0001', 'credential_mode': 'browser', 'allow_external_model': True}
        assert client.get(f"/wrongbook/v2/{answer['wrong_id']}/learning-context?attempt_id={answer['attempt_id']}", headers=headers).status_code == 403
        assert client.post(path, headers=headers, json={**body, 'credential_mode': 'server'}).status_code == 403
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == 200 and response.json()['data']['status'] == 'failed'
        assert response.json()['data']['error_code'] == 'provider_unavailable'
        assert 'synthetic-never-real-key' not in response.text
        assert len(calls) == 1 and calls[0].api_key == headers['X-FileMate-LLM-Key']
        assert calls[0].base_url == LLMConfig().base_url
        assert calls[0].model == LLMConfig().model
        assert not REQUEST_API_KEY.get()
        assert client.get('/wrongbook/v2/analysis-requests/'+body['request_key']).json()['data']['status'] == 'failed'
        assert client.get('/wrongbook/v2/summary').status_code == 200
    assert 'synthetic-never-real-key' not in store._conn().execute('SELECT input_snapshot FROM wrong_review_analyses').fetchone()[0]
