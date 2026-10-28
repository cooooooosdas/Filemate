"""Read actual review evidence without calling models or inventing mappings."""
# ruff: noqa: F811

import importlib
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from filemate.execution.data_actions import digest
from filemate.llm_client import LLMClient
from filemate.tests.course_graph.conftest import course_context, course_store  # noqa: F401
from filemate.tests.course_graph.test_learning_links import confirm, learning_context  # noqa: F401
from filemate.tests.test_server_persistence import server_module  # noqa: F401
from filemate.tests.wrongbook.conftest import answer_payload, review_store  # noqa: F401
from filemate.tests.wrongbook.test_api import seed
from filemate.wrongbook.repository import ReviewRepository


def service(store, clock):
    assert importlib.util.find_spec('filemate.wrongbook.learning_context'), '缺少真实复盘上下文'
    return importlib.import_module('filemate.wrongbook.learning_context').ReviewLearningContext(store, clock)


def test_context_binds_real_attempt_and_bounds_history(review_store):
    store, sid, aid, questions, clock = review_store
    repo = ReviewRepository(store, clock=lambda: clock[0])
    first = repo.submit(answer_payload(review_store))
    for i in range(8):
        repo.submit(answer_payload(review_store, key=f'context-history-key-{i:04}'))
    context = service(store, lambda: clock[0]).build(first['wrong_id'], first['attempt_id'])
    assert context['ref'] == {'wrong_id': first['wrong_id'], 'artifact_id': aid,
        'question_index': 0, 'question_digest': digest(questions[0])}
    assert context['attempt']['user_answer'] == 'B'
    assert len(context['related_attempts']) == 5
    assert first['attempt_id'] not in {a['attempt_id'] for a in context['related_attempts']}
    assert context['coverage']['total_attempts'] == 9
    assert context['coverage']['related_attempts_omitted'] == 3
    assert context['confirmed_diagnosis']['error_causes'] == []
    assert context['next_actions'] == []
    assert {s['source_id'] for s in context['_source_dependencies']} == {sid}
    other = repo.submit(answer_payload(review_store, index=2, answer='错误', key='context-foreign-attempt-key'))
    with pytest.raises(LookupError):
        service(store, lambda: clock[0]).build(first['wrong_id'], other['attempt_id'])
    with pytest.raises(LookupError):
        service(store, lambda: clock[0]).build(first['wrong_id'], 'missing')
    again = service(store, lambda: clock[0] + timedelta(seconds=1)).build(first['wrong_id'], first['attempt_id'])
    assert context['input_digest'] == again['input_digest']
    assert context['as_of'] != again['as_of']


def test_connections_revalidate_both_digest_algorithms(learning_context):
    store, cid, sid, nid, aid, question = learning_context
    confirm(learning_context)
    result = ReviewRepository(store).submit({'artifact_id': aid, 'question_index': 0,
        'expected_question': question, 'user_answer': '先进先出', 'request_key': 'context-graph-answer-key'})
    context = service(store, ReviewRepository(store).now)
    page = context.connections(result['wrong_id'])
    assert page['total'] == 1
    link = page['items'][0]
    assert link['concept_id'] == nid and link['course_id'] == cid
    assert link['route'] == f'/knowledge-graph?graph_scope=course&course={cid}&node={nid}&view=evidence'
    assert link['question_digest'] != digest(question)
    body = context.build(result['wrong_id'], result['attempt_id'], cid)
    assert body['source_evidence'] and body['graph_links'][0]['concept_id'] == nid
    for evidence in body['source_evidence']:
        assert store.get_source(evidence['source_id'])['raw_text'][evidence['char_start']:evidence['char_end']] == evidence['quote']
    store._conn().execute("UPDATE kg_question_links SET question_digest='stale'")
    store._conn().commit()
    assert context.connections(result['wrong_id'])['total'] == 0
    with pytest.raises(ValueError, match='course_scope_unavailable'):
        context.build(result['wrong_id'], result['attempt_id'], cid)
    store._conn().execute('UPDATE kg_question_links SET question_digest=?', (link['question_digest'],))
    store._conn().execute('UPDATE kg_course_sources SET active=0 WHERE source_id=?', (sid,))
    store._conn().commit()
    assert context.connections(result['wrong_id'])['total'] == 0


def test_quotes_have_global_literal_offsets_and_never_trust_old_chunk_coordinates(review_store):
    store, sid, *_ = review_store
    raw = '前言\n--- 第 2 页 ---\n栈遵循后进先出的次序。\n--- 第 3 页 ---\n队列遵循先进先出的次序。'
    store._conn().execute('UPDATE sources SET raw_text=? WHERE source_id=?', (raw, sid))
    store._conn().commit()
    store.replace_source_chunks(sid, [{'chunk_index': 0, 'content': '栈遵循后进先出的次序。',
        'page_number': 2, 'metadata': {'char_start': 0, 'char_end': 13}}])
    repo = ReviewRepository(store)
    result = repo.submit(answer_payload(review_store))
    context = service(store, repo.now).build(result['wrong_id'], result['attempt_id'])
    assert 1 <= len(context['source_evidence']) <= 3
    assert sum(len(s['quote']) for s in context['source_evidence']) <= 6000
    ref = context['source_evidence'][0]
    assert ref['relation_kind'] == 'retrieval_candidate'
    assert raw[ref['char_start']:ref['char_end']] == ref['quote']
    assert ref['char_start'] > 0 and ref['page'] == 2
    old = context['input_digest']
    store._conn().execute('UPDATE sources SET raw_text=? WHERE source_id=?', ('前言'+raw+raw, sid))
    store._conn().commit()
    ambiguous = service(store, repo.now).build(result['wrong_id'], result['attempt_id'])
    assert ambiguous['source_evidence'] == []
    assert ambiguous['input_digest'] != old


def test_context_reports_no_source_without_inventing_references(review_store):
    store, *_ = review_store
    result = ReviewRepository(store).submit(answer_payload(review_store))
    context = service(store, ReviewRepository(store).now).build(result['wrong_id'], result['attempt_id'])
    assert not context['source_evidence'] and not context['graph_links']
    assert context['coverage']['source_evidence_status'] == 'not_found'
    assert store._conn().execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 1


def test_http_context_and_reverse_link_are_readonly_and_strict(server_module, monkeypatch):
    module, store = server_module
    body = seed(store)
    result = ReviewRepository(store).submit(body)
    wid, attempt = result['wrong_id'], result['attempt_id']
    monkeypatch.setattr(LLMClient, 'call_structured', lambda *a, **k: pytest.fail('GET不得调用模型'))
    with TestClient(module.app) as client:
        url = f'/wrongbook/v2/{wid}/learning-context?attempt_id={attempt}'
        response = client.get(url)
        assert response.status_code == 200, response.text
        data = response.json()['data']
        assert data['ref']['wrong_id'] == wid and not any(k.startswith('_') for k in data)
        for suffix in ('&unknown=x', '&attempt_id=another'):
            assert client.get(url+suffix).status_code == 422
        assert client.get(f'/wrongbook/v2/{wid}/learning-context').status_code == 422
        assert client.get(f'/wrongbook/v2/{wid}/connections?limit=0').status_code == 422
        assert client.get(f'/wrongbook/v2/{wid}/connections').json()['data']['total'] == 0
        path = f"/wrongbook/v2/question-access/{body['artifact_id']}/0"
        access = client.get(path).json()['data']
        assert access['wrong_id'] == wid and access['review_route'] == f'/wrongbook?focus={wid}'
        assert 'source_path' not in json.dumps(data)


def test_context_does_not_reuse_changed_question_or_send_excessive_body(review_store):
    store, _, aid, questions, _ = review_store
    repo = ReviewRepository(store)
    result = repo.submit(answer_payload(review_store))
    store.update_artifact(aid, title='合成修订', content=[{**questions[0], 'answer': 'B'}, *questions[1:]])
    historical = service(store, repo.now).build(result['wrong_id'], result['attempt_id'])
    assert historical['read_only_snapshot'] is True
    assert historical['graph_links'] == []


def test_reverse_links_never_point_to_mismatched_or_archived_question(server_module):
    module, store = server_module
    body = seed(store)
    result = ReviewRepository(store).submit(body)
    path = f"/wrongbook/v2/question-access/{body['artifact_id']}/0"
    with TestClient(module.app) as client:
        store._conn().execute('UPDATE wrong_questions SET question=? WHERE wrong_id=?',
            (json.dumps({**body['expected_question'], 'answer': 'changed'}), result['wrong_id']))
        store._conn().commit()
        assert client.get(path).json()['data']['wrong_id'] is None


def test_read_failure_is_bounded_and_browser_identity_contains_no_credential(server_module, monkeypatch):
    import sqlite3

    from filemate.wrongbook.learning_context import ReviewLearningContext
    module, store = server_module
    result = ReviewRepository(store).submit(seed(store))
    url = f"/wrongbook/v2/{result['wrong_id']}/learning-context?attempt_id={result['attempt_id']}"
    with TestClient(module.app) as client:
        assert client.get(url+'&credential_mode=browser').json()['data']['credential_mode'] == 'browser'
        def broken(*args, **kwargs):
            raise sqlite3.OperationalError('private database path')
        monkeypatch.setattr(ReviewLearningContext, 'build', broken)
        response = client.get(url)
        assert response.status_code == 503
        assert 'private database path' not in response.text


def test_oversized_context_is_rejected_without_truncating_original_answer(review_store):
    store, _, _aid, questions, _ = review_store
    result = ReviewRepository(store).submit(answer_payload(review_store))
    # 导入的旧资料可能超过新写入合同，读取时也必须约束外发体积。
    store._conn().execute('UPDATE wrong_questions SET question=? WHERE wrong_id=?',
        (json.dumps({**questions[0], 'stem': '很长的题目' * 30000}), result['wrong_id']))
    store._conn().execute("UPDATE quiz_attempts SET question_digest='' WHERE attempt_id=?", (result['attempt_id'],))
    store._conn().commit()
    with pytest.raises(ValueError, match='analysis_context_too_large'):
        service(store, ReviewRepository(store).now).build(result['wrong_id'], result['attempt_id'])


def test_public_byte_limit_includes_preview_timestamp(review_store, monkeypatch):
    from filemate.wrongbook import learning_context as module

    store, _, _, _, clock = review_store
    attempt = ReviewRepository(store, clock=lambda: clock[0]).submit(answer_payload(review_store))
    reader = service(store, lambda: clock[0])
    context = reader.build(attempt['wrong_id'], attempt['attempt_id'])
    size = len(json.dumps(module.public_context(context), ensure_ascii=False).encode('utf-8'))
    monkeypatch.setattr(module, 'CONTEXT_BYTES', size-1)
    with pytest.raises(ValueError, match='analysis_context_too_large'):
        reader.build(attempt['wrong_id'], attempt['attempt_id'])
