# ruff: noqa: F811
"""Read workspace contracts against isolated real databases and HTTP."""

import importlib
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from filemate.tests.course_graph.conftest import course_context, course_store  # noqa: F401
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401
from filemate.tests.test_accounts import account_server, register  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.tests.wrongbook.conftest import answer_payload
from filemate.tests.wrongbook.test_api import seed
from filemate.wrongbook.repository import ReviewRepository


def queries(store, clock=None):
    assert importlib.util.find_spec('filemate.wrongbook.queries'), '缺少工作台只读投影'
    module = importlib.import_module('filemate.wrongbook.queries')
    return module.ReviewQueries(store, clock=clock), module.ReviewFilter


def many(store, count=65):
    sid = store.save_source(original_name='原创_%资料', source_path='synthetic.txt')
    questions = [{'question_type': 'fill', 'stem': f'知识点{i:05}：顺序？', 'answer': '后进先出'} for i in range(count)]
    aid = store.save_artifact(source_id=sid, artifact_type='questions', content=questions)
    for i in range(count):
        store.record_quiz_attempt(artifact_id=aid, question_index=i, user_answer='未知', is_correct=False, score=0, feedback='合成')
    store._conn().execute("UPDATE wrong_questions SET next_review_at='2026-10-25T00:00:00+00:00'")
    store._conn().commit()
    return sid, aid


def test_full_filter_precedes_paging_and_never_returns_answers(review_store):
    store, *_, clock = review_store
    source, _ = many(store)
    read, filters = queries(store, lambda: clock[0])
    page = read.page(filters())
    assert (page['total'], len(page['items']), page['has_more']) == (65, 30, True)
    second = read.page(filters(), offset=30)
    assert not {i['wrong_id'] for i in page['items']} & {i['wrong_id'] for i in second['items']}
    last = read.page(filters(q='知识点00064'))
    assert last['total'] == 1 and last['items'][0]['question_index'] == 64
    assert read.page(filters(q='_%'))['total'] == 65
    assert read.page(filters(q='%不存在'))['total'] == 0
    item = last['items'][0]
    assert item['source_id'] == source and len(item['question_digest']) == 64
    assert not {'question', 'answer', 'latest_answer', 'explanation'} & item.keys()
    assert read.options('sources', q='_%')['items'] == [{'id': source, 'label': '原创_%资料'}]


@pytest.mark.parametrize('status,updates,expected', [
    ('all', {}, 1), ('due', {}, 1), ('overdue', {}, 1),
    ('active', {'scheduler_version': 'review-interval-v2', 'learning_status': 'provisional'}, 1),
    ('pending', {'learning_status': 'pending_check'}, 1),
    ('criterion_met', {'scheduler_version': 'review-interval-v2', 'learning_status': 'criterion_met'}, 1),
    ('legacy_completed', {'mastered': 1}, 1), ('paused', {'schedule_status': 'paused'}, 1),
    ('invalid', {'next_review_at': '2026-02-30T00:00:00Z'}, 1), ('history', {}, 1),
])
def test_statuses_and_reviewable_filter_use_real_state(review_store, status, updates, expected):
    store, _, aid, _, clock = review_store
    many(store, 1)
    if updates:
        store._conn().execute('UPDATE wrong_questions SET ' + ','.join(f'{k}=?' for k in updates), tuple(updates.values()))
    if status == 'history':
        store._conn().execute("UPDATE artifacts SET metadata=? WHERE artifact_id!=?", (json.dumps({'read_only_snapshot': True}), aid))
    store._conn().commit()
    read, filters = queries(store, lambda: clock[0])
    assert read.page(filters(status=status))['total'] == expected
    if status in {'paused', 'legacy_completed', 'invalid', 'history'}:
        assert read.page(filters(reviewable_only=True))['total'] == 0


def test_causes_dates_counts_and_reviewability_before_limit(review_store):
    store, _, _, _, clock = review_store
    many(store, 65)
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET schedule_status='paused' WHERE question_index<60")
        conn.execute("UPDATE wrong_questions SET error_causes='[\"code_error\",\"boundary_gap\"]',error_count=4 WHERE question_index=64")
    read, filters = queries(store, lambda: clock[0])
    page = read.page(filters(reviewable_only=True), limit=2)
    assert page['total'] == 5 and len(page['items']) == 2
    found = read.page(filters(cause='boundary_gap', min_errors=4, max_errors=4,
                              due_from='2026-10-25T08:00:00+08:00', due_to='2026-10-25T00:00:00Z'))
    assert found['total'] == 1 and found['items'][0]['question_index'] == 64
    assert read.page(filters(sort='errors', direction='desc'))['items'][0]['error_count'] == 4
    for invalid in ({'min_errors': 4, 'max_errors': 2}, {'due_from': 'now'}, {'due_from': '2026-02-30T00:00:00Z'}, {'due_to': '2026-01-01'}, {'q': 'x' * 161}):
        with pytest.raises((ValueError, ValidationError)):
            filters(**invalid)


@pytest.mark.parametrize('cause', ['concept_gap', 'memory_gap', 'reasoning_break', 'expression_gap',
    'option_confusion', 'careless', 'method_gap', 'condition_gap', 'calculation_error', 'code_error',
    'boundary_gap', 'time_pressure', 'other'])
def test_all_confirmed_causes_can_be_filtered(review_store, cause):
    store, *_, clock = review_store
    many(store, 1)
    with store._conn() as conn:
        conn.execute('UPDATE wrong_questions SET error_causes=?', (json.dumps([cause]),))
    read, filters = queries(store, lambda: clock[0])
    assert read.page(filters(cause=cause))['total'] == 1


def test_malformed_record_remains_readable_and_excluded_from_focus(review_store):
    store, *_, clock = review_store
    many(store, 1)
    with store._conn() as conn:
        conn.execute("UPDATE wrong_questions SET question='broken',error_causes='broken'")
    read, filters = queries(store, lambda: clock[0])
    page = read.page(filters(status='invalid'))
    assert page['total'] == 1 and page['items'][0]['data_error']
    assert read.page(filters(cause='other'))['total'] == 0
    wid = page['items'][0]['wrong_id']
    detail = ReviewRepository(store).detail(wid)
    assert detail['data_error'] is True and detail['question'] == {}
    assert read.page(filters(reviewable_only=True))['total'] == 0


def test_current_explicit_course_mapping_only(learning_context):
    store, cid, sid, _, aid, question = learning_context
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer='错误', is_correct=False, score=0, feedback='合成')
    read, filters = queries(store)
    assert read.page(filters(course_id=cid))['total'] == 0
    confirm(learning_context)
    assert read.page(filters(course_id=cid))['total'] == 1
    assert read.options('courses')['items'][0]['id'] == cid
    with store._conn() as conn:
        conn.execute("UPDATE artifacts SET content=? WHERE artifact_id=?", (json.dumps([{**question, 'answer': '已修改'}]), aid))
    assert read.page(filters(course_id=cid))['total'] == 0
    with store._conn() as conn:
        conn.execute('UPDATE artifacts SET content=? WHERE artifact_id=?', (json.dumps([question]), aid))
        conn.execute('UPDATE kg_course_sources SET active=0 WHERE course_id=? AND source_id=?', (cid, sid))
    assert read.page(filters(course_id=cid))['total'] == 0


def test_receipt_provenance_comes_from_the_actual_saved_attempt(review_store):
    from filemate.execution.data_actions import digest

    store, _, _, _, clock = review_store
    body = answer_payload(review_store)
    saved = ReviewRepository(store, clock=lambda: clock[0]).submit(body)
    read, _ = queries(store)
    receipt = read.receipt(body['request_key'])
    assert receipt['artifact_id'] == body['artifact_id']
    assert receipt['question_index'] == body['question_index']
    assert receipt['question_digest'] == digest(body['expected_question'])
    assert receipt['attempt_id'] == saved['attempt_id']


def test_summary_receipt_and_detail_keep_real_saved_evidence(review_store):
    store, _, _, _, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    assert repo.summary().get('saved_review_attempt_count') == 0
    body = answer_payload(review_store)
    result = repo.submit(body)
    repo.submit(answer_payload(review_store, 'A', key='workspace-second-answer'))
    read, _ = queries(store)
    assert {k: read.receipt(body['request_key'])[k] for k in result} == result
    assert repo.summary()['saved_review_attempt_count'] == 1
    assert len(repo.detail(result['wrong_id'])['question_digest']) == 64
    with pytest.raises(LookupError):
        read.receipt('workspace-no-such-key')


def test_http_capabilities_filters_receipts_and_no_model_calls(server_module, monkeypatch):
    module, store = server_module
    body = seed(store)
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    from filemate.llm_client import LLMClient
    monkeypatch.setattr(LLMClient, 'call_structured', lambda *a, **k: pytest.fail('只读操作不调用模型'))
    with TestClient(module.app) as client:
        assert client.get('/wrongbook/v2/capabilities').json()['data']['write_enabled'] is True
        saved = client.post('/wrongbook/v2/attempts', json=body).json()['data']
        monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '0')
        assert client.get('/wrongbook/v2/capabilities').json()['data']['write_enabled'] is False
        page = client.get('/wrongbook/v2/page?status=due')
        assert page.status_code == 200 and page.json()['data']['total'] == 1
        assert page.headers['cache-control'] == 'no-store'
        assert client.get('/wrongbook/v2/filter-options?kind=sources').json()['data']['total'] == 1
        receipt = client.get('/wrongbook/v2/receipts/' + body['request_key']).json()['data']
        assert {k: receipt[k] for k in saved} == saved
        assert receipt['artifact_id'] == body['artifact_id']
        for suffix in ('?q=a&q=b', '?owner=someone', '?status=madeup', '?limit=101', '?offset=-1', '?reviewable_only=maybe'):
            assert client.get('/wrongbook/v2/page' + suffix).status_code == 422
        assert client.get('/wrongbook/v2/receipts/short').status_code == 422
        assert client.get('/wrongbook/v2/filter-options?kind=unknown').status_code == 422


def test_http_cross_account_receipt_and_page_isolation(account_server, monkeypatch):
    module = account_server
    monkeypatch.setenv('FILEMATE_ENABLE_WRONGBOOK_V2', '1')
    with TestClient(module.app) as first, TestClient(module.app) as second:
        register(first, 'workspace-a@example.com')
        register(second, 'workspace-b@example.com')
        # Seed only generated questions locally; reads/writes retain actual HTTP identity.
        imported = first.post('/knowledge/import', files={'file': ('synthetic.txt', '原创栈资料'.encode(), 'text/plain')}).json()['data']
        store = next(s for s in module._tenant_storages.values() if s.get_source(imported['source_id']))
        body = seed(store)
        response = first.post('/wrongbook/v2/attempts', json=body)
        assert response.status_code == 200, response.text
        wid = response.json()['data']['wrong_id']
        assert second.get('/wrongbook/v2/page').json()['data']['total'] == 0
        assert second.get('/wrongbook/v2/' + wid).status_code == 404
        assert second.get('/wrongbook/v2/receipts/' + body['request_key']).status_code == 404


def test_question_access_is_scoped_and_prevents_legacy_write(review_store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from filemate.wrongbook.api import create_router
    store, _, aid, _, _ = review_store
    store.record_quiz_attempt(artifact_id=aid, question_index=0, user_answer="B", is_correct=False, score=0, feedback="合成")
    wid = store._conn().execute("SELECT wrong_id FROM wrong_questions WHERE artifact_id=?", (aid,)).fetchone()[0]
    app = FastAPI()
    app.include_router(create_router(lambda: store))
    client = TestClient(app)
    path = f'/wrongbook/v2/question-access/{aid}/0'
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()['data']['legacy_writable'] is True
    store._conn().execute("UPDATE wrong_questions SET scheduler_version='review-interval-v2' WHERE wrong_id=?", (wid,))
    store._conn().commit()
    assert client.get(path).json()['data']['legacy_writable'] is False
    assert client.get('/wrongbook/v2/question-access/missing/0').status_code == 404
    assert client.get(path + '?owner=other').status_code == 422


def test_native_search_does_not_decode_full_library_in_python(review_store, monkeypatch):
    store, *_, clock = review_store
    many(store, 120)
    module = importlib.import_module('filemate.wrongbook.queries')
    original, calls = module._object, []
    def counted(raw):
        calls.append(1)
        return original(raw)
    monkeypatch.setattr(module, '_object', counted)
    result = module.ReviewQueries(store, clock=lambda: clock[0]).page(module.ReviewFilter(q='知识点00119'))
    assert result['total'] == 1
    assert len(calls) <= 10


@pytest.mark.parametrize('fallback', [False, True])
def test_search_native_and_compatibility_paths_exclude_answers_and_bad_json(review_store, monkeypatch, fallback):
    store = review_store[0]
    many(store, 3)
    module = importlib.import_module('filemate.wrongbook.queries')
    if fallback:
        monkeypatch.setattr(module, '_stem_expression', lambda conn: 'review_stem(w.question)')
    query = module.ReviewQueries(store)
    assert query.page(module.ReviewFilter(q='后进先出'))['total'] == 0
    assert query.page(module.ReviewFilter(q='知识点00002'))['total'] == 1
    store._conn().execute("UPDATE wrong_questions SET question='invalid JSON',knowledge_label=''")
    store._conn().commit()
    assert query.page(module.ReviewFilter(q='知识点'))['total'] == 0


def test_json_extension_missing_keeps_compatible_query():
    import sqlite3
    module = importlib.import_module('filemate.wrongbook.queries')
    class WithoutJson:
        def execute(self, sql):
            raise sqlite3.OperationalError('no such function: json_extract')
    assert module._stem_expression(WithoutJson()) == 'review_stem(w.question)'
