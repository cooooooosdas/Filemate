"""Synthetic API contracts for the opt-in interview coach."""

import importlib
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from filemate.execution.storage import SQLiteStorage
from filemate.tests.test_interview_coach_analysis import ANSWER, Provider


@pytest.fixture
def api(tmp_path, monkeypatch, request):
    monkeypatch.setenv('FILEMATE_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('FILEMATE_DB_PATH', str(tmp_path / 'bootstrap.db'))
    monkeypatch.setenv('FILEMATE_INTERVIEW_LOCAL_ONLY', '1')
    monkeypatch.setenv('FILEMATE_ENABLE_INTERVIEW_COACH', '1')
    monkeypatch.setenv('FILEMATE_IDENTITY_MODE', getattr(request, 'param', 'local'))
    sys.modules.pop('server', None)
    module = importlib.import_module('server')
    store = SQLiteStorage(tmp_path / 'coach.db')
    store.init_schema()
    module._storage.close()
    module._storage = module._StorageRouter(store)
    with TestClient(module.app) as client:
        yield client, module
    store.close()
    sys.modules.pop('server', None)


def start(client, **options):
    response = client.post('/interviews', json={'target_role': '开发', 'scenario': '求职面试', **options})
    assert response.status_code == 200
    return response.json()['data']['interview_id']


def answer(client, sid):
    state = client.get(f'/interviews/{sid}/coach').json()['data']
    return client.post(f'/interviews/{sid}/coach/answers', json={'answer': ANSWER, 'question_index': 0,
                       'request_key': 'coach_answer_001', 'expected_revision': state['revision']})


def test_saved_answer_duplicate_validation_and_history(api):
    client, _ = api
    sid = start(client)
    first = answer(client, sid)
    assert first.status_code == 200
    result = first.json()['data']
    repeated = client.post(f'/interviews/{sid}/coach/answers', json={'answer': ANSWER, 'question_index': 0,
                          'request_key': 'coach_answer_001', 'expected_revision': 0})
    assert result['receipt'] == repeated.json()['data']['receipt']
    assert result['snapshot']['phase'] == 'feedback'
    attempt = result['snapshot']['current_attempt']
    assert client.get(f'/interviews/{sid}/turns/{attempt["turn_id"]}/attempts?limit=1').json()['data']['items'][0]['answer'] == ANSWER
    assert client.get(f'/interviews/{sid}/turns/{attempt["turn_id"]}/attempts?limit=101').status_code == 422
    assert client.post(f'/interviews/{sid}/coach/answers', json={'answer': ' ', 'question_index': 0,
                       'request_key': 'invalid_answer_1', 'expected_revision': 1}).status_code == 422


def test_flags_preserve_text_and_read_only_history(api, monkeypatch):
    client, _ = api
    sid = start(client)
    monkeypatch.setenv('FILEMATE_ENABLE_INTERVIEW_COACH', '0')
    assert answer(client, sid).status_code == 503
    assert client.get(f'/interviews/{sid}/coach').status_code == 200
    assert client.post(f'/interviews/{sid}/answers', json={'answer': ANSWER}).status_code == 200


def test_answer_is_readable_while_model_is_blocked(api, monkeypatch):
    import filemate.llm_client as llm

    client, _ = api
    sid = start(client)
    saved = answer(client, sid).json()['data']['snapshot']
    provider = Provider(block=True)
    monkeypatch.delenv('FILEMATE_INTERVIEW_LOCAL_ONLY')
    monkeypatch.setattr(llm, 'LLMClient', lambda _: provider)
    monkeypatch.setattr(llm.LLMConfig, 'from_env', lambda: object())
    state = client.post(f'/interviews/{sid}/coach/consent', json={'allowed': True,
                        'request_key': 'coach_consent_01', 'expected_revision': saved['revision']}).json()['data']['snapshot']
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(client.post, f'/interviews/{sid}/coach/analysis', json={
            'attempt_id': state['current_attempt']['attempt_id'], 'consent_revision': state['consent_revision'],
            'expected_revision': state['revision'], 'request_key': 'coach_analysis01'})
        assert provider.entered.wait(5)
        assert client.get(f'/interviews/{sid}/coach').json()['data']['current_attempt']['answer'] == ANSWER
        assert client.get('/api/health').status_code == 200
        provider.release.set()
        assert future.result(timeout=10).status_code == 200


def test_omitted_consent_never_creates_provider_for_start_or_answer(api, monkeypatch):
    import filemate.llm_client as llm

    client, _ = api
    monkeypatch.delenv('FILEMATE_INTERVIEW_LOCAL_ONLY')
    calls = []
    monkeypatch.setattr(llm, 'LLMClient', lambda _: calls.append('created'))
    sid = start(client)
    assert client.post(f'/interviews/{sid}/answers', json={'answer': ANSWER}).status_code == 200
    assert calls == []


@pytest.mark.parametrize('api', ['anonymous'], indirect=True)
def test_foreign_space_snapshot_and_submit_hidden(api):
    client, module = api
    sid = start(client)
    with TestClient(module.app) as foreign:
        assert foreign.get(f'/interviews/{sid}/coach').status_code == 404
        assert foreign.post(f'/interviews/{sid}/coach/answers', json={'answer': ANSWER, 'question_index': 0,
                            'request_key': 'foreign_answer01', 'expected_revision': 0}).status_code == 404


def test_focus_completed_session_preserves_original_progress_and_question(api):
    client,_=api;sid=start(client)
    while True:
        s=client.get(f'/interviews/{sid}/coach').json()['data']
        if s['phase']=='summary':break
        r=client.post(f'/interviews/{sid}/coach/answers',json={'answer':'合成原回答','question_index':s['displayed_index'],'expected_revision':s['revision'],'request_key':__import__('uuid').uuid4().hex}).json()['data']['snapshot']
        result=client.post(f'/interviews/{sid}/coach/advance',json={'from_index':r['displayed_index'],'expected_attempt_id':r['current_attempt']['attempt_id'],'expected_revision':r['revision'],'request_key':__import__('uuid').uuid4().hex})
        assert result.status_code==200
    response=client.post(f'/interviews/{sid}/coach/focus',json={'question_index':0,'expected_revision':s['revision'],'request_key':'api_focus_old001'})
    assert response.status_code==200
    focused=response.json()['data']['snapshot'];assert focused['phase']=='feedback'
    result=client.post(f'/interviews/{sid}/coach/answers',json={'answer':'合成末次修订','question_index':0,'expected_attempt_id':focused['current_attempt']['attempt_id'],'expected_revision':focused['revision'],'request_key':'api_focus_edit01'}).json()['data']
    assert result['snapshot']['session']['current_index']==len(s['session']['questions'])
    assert result['snapshot']['session']['questions']==s['session']['questions']
    assert result['snapshot']['current_attempt']['version']==2
