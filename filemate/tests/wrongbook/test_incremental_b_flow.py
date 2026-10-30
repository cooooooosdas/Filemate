# ruff: noqa: F811
"""One registered synthetic learner, real HTTP/SQLite and a controlled server clock."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from filemate.llm_client import LLMClient
from filemate.tests.test_accounts import HEADERS, account_server, login, register  # noqa: F401
from filemate.wrongbook.engine import parse_time
from filemate.wrongbook.repository import ReviewRepository


def test_registered_learner_full_incremental_b_lifecycle(account_server, monkeypatch):
    module = account_server
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    now = [datetime(2026, 10, 30, 8, tzinfo=timezone.utc)]
    monkeypatch.setattr(ReviewRepository, 'now', lambda self: now[0])

    def no_model(*args, **kwargs):
        raise AssertionError('B级排序、预览和规则作答不得调用模型')

    monkeypatch.setattr(LLMClient, 'call_structured', no_model)
    with TestClient(module.app) as learner, TestClient(module.app) as another:
        registered = register(learner)
        assert registered.status_code == 200
        user = registered.json()['data']['user']
        workspace = module._local_storage._conn().execute(
            'SELECT workspace_id FROM accounts WHERE account_id=?', (user['account_id'],)).fetchone()[0]
        store = module._tenant_storage(workspace)
        sid = store.save_source(original_name='原创合成栈课程', source_path='synthetic-stack.txt')
        question = {'question_type': 'choice', 'stem': '栈遵循什么顺序？',
                    'options': ['后进先出', '先进先出'], 'answer': 'A', 'analysis': '原创合成：栈后进先出'}
        aid = store.save_artifact(source_id=sid, artifact_type='questions', content=[question])
        headers = {'Origin': module.CORS_ORIGINS[0], 'X-FileMate-Action': 'state'}

        def answer(text, key):
            response = learner.post('/wrongbook/v2/attempts', headers=headers, json={
                'artifact_id': aid, 'question_index': 0, 'expected_question': question,
                'user_answer': text, 'request_key': key})
            assert response.status_code == 200, response.text
            return response.json()['data']

        first = answer('B', 'incremental-b-first-wrong')
        assert first['is_correct'] is False and first['judgement_status'] == 'verified'
        wid = first['wrong_id']
        annotated = learner.patch(f'/wrongbook/v2/{wid}/diagnosis', headers=headers, json={
            'request_key': 'incremental-b-human-cause', 'expected_revision': first['after']['revision'],
            'error_causes': ['concept_gap'], 'primary_cause': 'concept_gap', 'note': '混淆栈与队列的出入顺序'})
        assert annotated.status_code == 200, annotated.text
        now[0] = parse_time(first['after']['next_review_at']) + timedelta(days=1)
        params = {'available_minutes': 12, 'sort': 'recommended', 'source_id': sid}
        preview_response = learner.get('/wrongbook/v2/session-preview', params=params)
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()['data']
        assert preview['selected_count'] == preview['eligible_count'] == 1
        assert '本人标注' in preview['items'][0]['priority']['reason']
        refs = [item['ref'] for item in preview['items']]
        before = tuple(store._conn().iterdump())
        for _ in range(2):
            checked = learner.post('/wrongbook/v2/session-check', headers=headers,
                                   json={'refs': refs, 'filters': preview['filters']})
            assert checked.status_code == 200 and checked.json()['data']['status'] == 'ready'
        assert tuple(store._conn().iterdump()) == before

        correct = answer('A', 'incremental-b-correct-once')
        replay = answer('A', 'incremental-b-correct-once')
        assert replay['attempt_id'] == correct['attempt_id']
        assert correct['is_correct'] is True and correct['eligible'] is False
        assert correct['reason'] == 'initial_correction'
        assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 2
        assert correct['after']['mastered'] == 0
        today = learner.get('/review/today').json()['data']
        assert today['pending_wrong_count'] == 0
        now[0] = parse_time(correct['after']['next_review_at']) + timedelta(minutes=1)
        delayed = answer('A', 'incremental-b-delayed-correct')
        assert delayed['eligible'] is True and delayed['is_correct'] is True
        assert answer('A', 'incremental-b-delayed-correct')['attempt_id'] == delayed['attempt_id']
        assert store._conn().execute('SELECT COUNT(*) FROM quiz_attempts').fetchone()[0] == 3
        now[0] = parse_time(delayed['after']['next_review_at']) + timedelta(minutes=1)
        today = learner.get('/review/today').json()['data']
        assert today['pending_wrong_count'] == 1
        assert any(item.get('wrong_id') == wid and item['route'].endswith(wid) for item in today['items'])
        wrong_again = answer('B', 'incremental-b-wrong-again')
        assert wrong_again['is_correct'] is False and wrong_again['after']['correct_streak'] == 0
        attempts = learner.get(f'/wrongbook/v2/{wid}/attempts').json()['data']
        assert attempts['total'] == 4
        assert {row['user_answer'] for row in attempts['items']} == {'A', 'B'}
        assert {row['question_digest'] for row in attempts['items']} == {refs[0]['question_digest']}

        now[0] = parse_time(wrong_again['after']['next_review_at']) + timedelta(minutes=1)
        fresh = learner.get('/wrongbook/v2/session-preview', params=params).json()['data']
        fresh_body = {'refs': [item['ref'] for item in fresh['items']], 'filters': fresh['filters']}
        assert learner.post('/wrongbook/v2/session-check', headers=headers, json=fresh_body).status_code == 200
        assert register(another, email='another-b@example.invalid').status_code == 200
        assert another.get('/wrongbook/v2/page', params={'sort': 'recommended', 'source_id': sid}).json()['data']['total'] == 0
        assert another.get(f'/wrongbook/v2/{wid}').status_code == 404
        assert another.post('/wrongbook/v2/session-check', headers=headers, json=fresh_body).status_code == 409

        assert learner.post('/api/auth/logout', headers=HEADERS, json={}).status_code == 200
        assert login(learner).status_code == 200
        with TestClient(module.app) as refreshed:
            assert login(refreshed).status_code == 200
            detail = refreshed.get(f'/wrongbook/v2/{wid}').json()['data']
            assert detail['wrong_id'] == wid and detail['error_cause_source'] == 'user'
            assert detail['error_count'] == 2 and detail['mastered'] == 0
            assert refreshed.get(f'/wrongbook/v2/{wid}/attempts').json()['data']['total'] == 4
